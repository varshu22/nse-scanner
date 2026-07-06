import yfinance as yf
import pandas as pd
import numpy as np
import time
import random
import logging
import requests
from datetime import datetime
from tqdm.auto import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed


# ===============================
# SUPPRESS YFINANCE NOISE
# ===============================
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


# ===============================
# LOAD NSE STOCKS + LISTING DATE
# ===============================
nse_all_url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_resp = requests.get(nse_all_url, headers=_headers, timeout=30)
_resp.raise_for_status()
symbols_df = pd.read_csv(pd.io.common.StringIO(_resp.text))

symbols_df.columns = symbols_df.columns.str.strip()
symbols_df = symbols_df[symbols_df["SERIES"] == "EQ"]

listing_date_map = dict(zip(symbols_df["SYMBOL"], symbols_df["DATE OF LISTING"]))
symbols = [s + ".NS" for s in symbols_df["SYMBOL"].tolist()]



# ===============================
# HELPERS
# ===============================
def _clean(val, ndigits=2):
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if pd.isna(f) or np.isinf(f):
        return None
    return round(f, ndigits)


def _pct(numer, denom, ndigits=2):
    if denom is None or numer is None:
        return None
    try:
        denom = float(denom)
        numer = float(numer)
    except (TypeError, ValueError):
        return None
    if denom == 0 or pd.isna(denom) or pd.isna(numer) or np.isinf(denom):
        return None
    val = (numer / denom) * 100.0
    if pd.isna(val) or np.isinf(val):
        return None
    return round(val, ndigits)


def safe_metrics(hist, ltp, prefix, n_label, price_round=2):
    hist = pd.Series(hist).dropna()
    if len(hist) == 0 or ltp is None or pd.isna(ltp):
        return {}
    avg = float(hist.mean())
    mx  = float(hist.max())
    mn  = float(hist.min())
    ltp = float(ltp)
    if pd.isna(mx) or pd.isna(mn):
        return {}
    return {
        f"Avg_{n_label}{prefix}":  _clean(avg, price_round),
        f"{prefix}_Max_{n_label}": _clean(mx, price_round),
        f"{prefix}_Min_{n_label}": _clean(mn, price_round),
        f"{prefix}_LTP_Position":  "Above Max" if ltp > mx else "Below Min" if ltp < mn else "Between",
        f"{prefix}_Gap_Min_Max_%": _pct(mx - mn, mn),
        f"{prefix}_Gap_Max_LTP_%": _pct(ltp - mx, mx),
        f"{prefix}_Gap_Min_LTP_%": _pct(ltp - mn, mn),
        f"{prefix}_Avg_vs_LTP_%":  _pct(ltp - avg, avg),
    }


def closes_block(close_series, n_completed, prefix, price_round=2):
    out = {}
    cs = pd.Series(close_series).dropna()
    if len(cs) >= n_completed + 1:
        hist = cs.tail(n_completed + 1).iloc[:-1]
        ltp  = cs.iloc[-1]
        for i in range(n_completed):
            out[f"{prefix}{i+1}"] = _clean(hist.iloc[i], price_round) if i < len(hist) else None
        out[f"{prefix}LTP_VAL"] = _clean(ltp, price_round)
        return out, hist, float(ltp)
    else:
        for i in range(n_completed):
            out[f"{prefix}{i+1}"] = None
        out[f"{prefix}LTP_VAL"] = None
        return out, pd.Series(dtype=float), None


def calc_vwap(df_full, window=20, price_round=2):
    if df_full.empty:
        return None
    df = df_full.tail(window).dropna(subset=["High", "Low", "Close", "Volume"])
    vol = df["Volume"]
    if vol.sum() == 0:
        return None
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return _clean((tp * vol).sum() / vol.sum(), price_round)


def calc_ema(close_series, period, price_round=2):
    cs = pd.Series(close_series).dropna()
    if len(cs) < period:
        return None
    return _clean(cs.ewm(span=period, adjust=False).mean().iloc[-1], price_round)


def last_rsi(close, period=14):
    close = pd.Series(close).dropna()
    if len(close) < period + 1:
        return None
    d = close.diff()
    gain = d.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rsi = 100 - (100 / (1 + gain / loss))
    return _clean(rsi.iloc[-1], 2)


# ===============================
# CANDLE PATTERN
# ===============================
def candle_pattern(o, h, l, c):
    body = abs(c - o)
    total = h - l

    if total == 0:
        return "Flat"

    if body / total > 0.8:
        return "Bullish Marubozu" if c > o else "Bearish Marubozu"
    if body / total <= 0.1:
        return "Doji"
    return "Bullish" if c > o else "Bearish"


# ===============================
# FETCH DATA
# ===============================
def fetch_data(symbol, retries=3):
    base_symbol = symbol.replace(".NS", "")

    for _ in range(retries + 1):
        try:
            time.sleep(random.uniform(0.2, 0.6))

            ticker = yf.Ticker(symbol)

            daily_full   = ticker.history(period="2y",  interval="1d")
            weekly_full  = ticker.history(period="8mo", interval="1wk")
            monthly_full = ticker.history(period="3y",  interval="1mo")
            hourly_full  = ticker.history(period="60d", interval="1h")   # step 3
            m30_full     = ticker.history(period="5d",  interval="30m")  # step 4
            m5_full      = ticker.history(period="5d",  interval="5m")   # step 5
            if daily_full.empty or weekly_full.empty or monthly_full.empty:
                raise ValueError("No data")

            # ---- resample hourly -> 4H (step 3) ----
            if not hourly_full.empty:
                h4_full = hourly_full.resample("4h").agg({
                    "Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum"
                }).dropna()
            else:
                h4_full = pd.DataFrame()

            # ===============================
            # HIST + LTP
            # ===============================
            daily_hist = daily_full["Close"].tail(22).iloc[:-1]
            daily_ltp  = daily_full["Close"].iloc[-1]

            weekly_hist = weekly_full["Close"].tail(22).iloc[:-1]
            weekly_ltp  = weekly_full["Close"].iloc[-1]

            monthly_hist = monthly_full["Close"].tail(24).iloc[:-1]
            monthly_ltp  = monthly_full["Close"].iloc[-1]

            row = {
                "Symbol":          symbol,
                "Date of Listing": listing_date_map.get(base_symbol, None)
            }

            # ===============================
            # CLOSE DATA — M, W, D
            # ===============================
            for i in range(23):
                row[f"M{i+1}"] = round(monthly_hist.iloc[i], 2) if i < len(monthly_hist) else None
            row["M_LTP"] = round(monthly_ltp, 2)

            for i in range(21):
                row[f"W{i+1}"] = round(weekly_hist.iloc[i], 2) if i < len(weekly_hist) else None
            row["W_LTP"] = round(weekly_ltp, 2)

            for i in range(21):
                row[f"D{i+1}"] = round(daily_hist.iloc[i], 2) if i < len(daily_hist) else None
            row["LTP"] = round(daily_ltp, 2)

            # ---- 4H: 13 completed + LTP (step 3) ----
            h4_close = h4_full["Close"] if not h4_full.empty else pd.Series(dtype=float)
            h4_cols, h4_hist, h4_ltp = closes_block(h4_close, 13, "H4_")
            for i in range(13):
                row[f"H4_{i+1}"] = h4_cols[f"H4_{i+1}"]
            row["H4_LTP"] = h4_cols["H4_LTP_VAL"]

            # ---- 30-MIN: 8 completed + LTP (step 4) ----
            m30_close = m30_full["Close"] if not m30_full.empty else pd.Series(dtype=float)
            m30_cols, m30_hist, m30_ltp = closes_block(m30_close, 8, "M30_")
            for i in range(8):
                row[f"M30_{i+1}"] = m30_cols[f"M30_{i+1}"]
            row["M30_LTP"] = m30_cols["M30_LTP_VAL"]

            # ---- 5-MIN: 5 completed + LTP (step 5) ----
            m5_close = m5_full["Close"] if not m5_full.empty else pd.Series(dtype=float)
            m5_cols, m5_hist, m5_ltp = closes_block(m5_close, 5, "M5_")
            for i in range(5):
                row[f"M5_{i+1}"] = m5_cols[f"M5_{i+1}"]
            row["M5_LTP"] = m5_cols["M5_LTP_VAL"]

            # ===============================
            # CANDLES
            # ===============================
            last_5      = daily_full.tail(5)
            completed_4 = last_5.iloc[:-1]
            live_candle = last_5.iloc[-1]

            for idx, (dt, candle) in enumerate(completed_4.iterrows(), start=1):
                row[f"C{idx}_{dt.strftime('%Y-%m-%d')}"] = candle_pattern(
                    candle["Open"], candle["High"], candle["Low"], candle["Close"]
                )

            row["Live Candle"] = candle_pattern(
                live_candle["Open"], live_candle["High"], live_candle["Low"], live_candle["Close"]
            )

            # ===============================
            # OPEN HIGH / OPEN LOW + PREV DAY OHLC + FIB
            # ===============================
            if len(daily_full) >= 2:
                last = daily_full.iloc[-1]
                prev = daily_full.iloc[-2]
                if last.name.date() == datetime.now().date():
                    use_candle = prev
                else:
                    use_candle = last
            else:
                use_candle = daily_full.iloc[-1]

            o, h, l = use_candle["Open"], use_candle["High"], use_candle["Low"]
            row["Open_High"] = "Yes" if abs(o - h) <= 0.001 * o else "No"
            row["Open_Low"]  = "Yes" if abs(o - l) <= 0.001 * o else "No"

            row["Last_Day_Candle"] = candle_pattern(o, h, l, use_candle["Close"])

            row["PD_Open"]   = _clean(o)
            row["PD_High"]   = _clean(h)
            row["PD_Low"]    = _clean(l)
            row["PD_Close"]  = _clean(use_candle["Close"])
            row["PD_Fib50"]  = _clean(l + 0.5   * (h - l))
            row["PD_Fib618"] = _clean(l + 0.618 * (h - l))

            if len(weekly_full) >= 2:
                lw = weekly_full.iloc[-2]
                row["Last_Week_Candle"] = candle_pattern(lw["Open"], lw["High"], lw["Low"], lw["Close"])
                row["PW_Open"]   = _clean(lw["Open"])
                row["PW_High"]   = _clean(lw["High"])
                row["PW_Low"]    = _clean(lw["Low"])
                row["PW_Close"]  = _clean(lw["Close"])
                row["PW_Fib50"]  = _clean(lw["Low"] + 0.5   * (lw["High"] - lw["Low"]))
                row["PW_Fib618"] = _clean(lw["Low"] + 0.618 * (lw["High"] - lw["Low"]))
            else:
                row["Last_Week_Candle"] = None
                row["PW_Open"] = row["PW_High"] = row["PW_Low"] = row["PW_Close"] = None
                row["PW_Fib50"] = row["PW_Fib618"] = None

            if len(monthly_full) >= 2:
                lm = monthly_full.iloc[-2]
                row["Last_Month_Candle"] = candle_pattern(lm["Open"], lm["High"], lm["Low"], lm["Close"])
                row["PM_Open"]   = _clean(lm["Open"])
                row["PM_High"]   = _clean(lm["High"])
                row["PM_Low"]    = _clean(lm["Low"])
                row["PM_Close"]  = _clean(lm["Close"])
                row["PM_Fib50"]  = _clean(lm["Low"] + 0.5   * (lm["High"] - lm["Low"]))
                row["PM_Fib618"] = _clean(lm["Low"] + 0.618 * (lm["High"] - lm["Low"]))
            else:
                row["Last_Month_Candle"] = None
                row["PM_Open"] = row["PM_High"] = row["PM_Low"] = row["PM_Close"] = None
                row["PM_Fib50"] = row["PM_Fib618"] = None

            # ===============================
            # RSI — Daily / Weekly / Monthly / 4H / 30m / 5m (step 6)
            # ===============================
            d = daily_full["Close"].diff()
            row["RSI_Daily"] = _clean((100 - (100 / (1 + d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean() / (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()))).iloc[-1], 2)

            d = weekly_full["Close"].diff()
            row["RSI_Weekly"] = _clean((100 - (100 / (1 + d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean() / (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()))).iloc[-1], 2)

            row["RSI_Monthly"] = last_rsi(monthly_full["Close"])
            row["RSI_4H"]      = last_rsi(h4_close)
            row["RSI_30m"]     = last_rsi(m30_close)
            row["RSI_5m"]      = last_rsi(m5_close)

            # ===============================
            # LAST COMPLETED 30-MIN CANDLE (step 4)
            # ===============================
            if not m30_full.empty and len(m30_full) >= 2:
                last30 = m30_full.iloc[-2]
                if last30["Close"] > last30["Open"]:
                    row["Last_30min_Candle"] = "Bullish"
                elif last30["Close"] < last30["Open"]:
                    row["Last_30min_Candle"] = "Bearish"
                else:
                    row["Last_30min_Candle"] = "Doji"
            else:
                row["Last_30min_Candle"] = None

            # ===============================
            # METRICS — M, W, D
            # ===============================
            m_avg, m_max, m_min = monthly_hist.mean(), monthly_hist.max(), monthly_hist.min()
            w_avg, w_max, w_min = weekly_hist.mean(), weekly_hist.max(), weekly_hist.min()
            d_avg, d_max, d_min = daily_hist.mean(), daily_hist.max(), daily_hist.min()

            row.update({
                "Avg_23M":         round(m_avg, 2),
                "M_Max_23":        round(m_max, 2),
                "M_Min_23":        round(m_min, 2),
                "M_LTP_Position":  "Above Max" if monthly_ltp > m_max else "Below Min" if monthly_ltp < m_min else "Between",
                "M_Gap_Min_Max_%": round(((m_max - m_min) / m_min) * 100, 2),
                "M_Gap_Max_LTP_%": round(((monthly_ltp - m_max) / m_max) * 100, 2),
                "M_Gap_Min_LTP_%": round(((monthly_ltp - m_min) / m_min) * 100, 2),

                "Avg_21W":         round(w_avg, 2),
                "W_Avg_vs_LTP_%":  round(((weekly_ltp - w_avg) / w_avg) * 100, 2),
                "W_Max_21":        round(w_max, 2),
                "W_Min_21":        round(w_min, 2),
                "W_LTP_Position":  "Above Max" if weekly_ltp > w_max else "Below Min" if weekly_ltp < w_min else "Between",
                "W_Gap_Min_Max_%": round(((w_max - w_min) / w_min) * 100, 2),
                "W_Gap_Max_LTP_%": round(((weekly_ltp - w_max) / w_max) * 100, 2),
                "W_Gap_Min_LTP_%": round(((weekly_ltp - w_min) / w_min) * 100, 2),

                "Avg_21D":         round(d_avg, 2),
                "D_Avg_vs_LTP_%":  round(((daily_ltp - d_avg) / d_avg) * 100, 2),
                "D_Max_21":        round(d_max, 2),
                "D_Min_21":        round(d_min, 2),
                "D_LTP_Position":  "Above Max" if daily_ltp > d_max else "Below Min" if daily_ltp < d_min else "Between",
                "D_Gap_Min_Max_%": round(((d_max - d_min) / d_min) * 100, 2),
                "D_Gap_Max_LTP_%": round(((daily_ltp - d_max) / d_max) * 100, 2),
                "D_Gap_Min_LTP_%": round(((daily_ltp - d_min) / d_min) * 100, 2),
            })

            # ---- H4 / M30 / M5 metrics (step 3, 4, 5) ----
            row.update(safe_metrics(h4_hist,  h4_ltp,  "H4",  "13"))
            row.update(safe_metrics(m30_hist, m30_ltp, "M30", "8"))
            row.update(safe_metrics(m5_hist,  m5_ltp,  "M5",  "5"))

            # ===============================
            # VWAP
            # ===============================
            row["VWAP_Daily"] = calc_vwap(daily_full)

            # ===============================
            # EMA (step 8)
            # ===============================
            ema_close = daily_full["Close"]
            row["EMA_9"]   = calc_ema(ema_close, 9)
            row["EMA_21"]  = calc_ema(ema_close, 21)
            row["EMA_50"]  = calc_ema(ema_close, 50)
            row["EMA_200"] = calc_ema(ema_close, 200)

            # ===============================
            # VOLUME (step 9)
            # ===============================
            vol = daily_full["Volume"]
            if len(daily_full) >= 1 and daily_full.index[-1].date() == datetime.now().date():
                live_day_vol  = vol.iloc[-1]
                completed_vol = vol.iloc[:-1].dropna()
            else:
                live_day_vol  = None
                completed_vol = vol.dropna()

            row["Avg_7D_Vol"]   = _clean(completed_vol.tail(7).mean() if len(completed_vol) else None, 2)
            row["Last_Day_Vol"] = _clean(completed_vol.iloc[-1] if len(completed_vol) else None, 2)
            row["Live_Day_Vol"] = _clean(live_day_vol, 2)

            return row

        except Exception:
            return {"Symbol": symbol}


# ===============================
# EXECUTION
# ===============================
final_data = []

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(fetch_data, sym) for sym in symbols]

    for future in tqdm(as_completed(futures), total=len(futures)):
        final_data.append(future.result())


# ===============================
# DATAFRAME + COLUMN ORDER
# ===============================
df = pd.DataFrame(final_data)
df = df.sort_values("Symbol").reset_index(drop=True)

# Consolidate duplicate date-stamped candle columns into a single column using the latest date.
for n in range(1, 5):
    prefix = f"C{n}_"
    c_cols = sorted(
        [c for c in df.columns if c.startswith(prefix) and len(c) == len(prefix) + 10],
        reverse=True,
    )
    if len(c_cols) > 1:
        for older in c_cols[1:]:
            df[c_cols[0]] = df[c_cols[0]].combine_first(df[older])
        df.drop(columns=c_cols[1:], inplace=True)

candle_cols = sorted([c for c in df.columns if c.startswith("C") and c[1:2].isdigit()])

ordered_cols = (
    ["Symbol", "Date of Listing"]

    # ---- close blocks ----
    + [f"M{i}"    for i in range(1, 24)] + ["M_LTP"]
    + [f"W{i}"    for i in range(1, 22)] + ["W_LTP"]
    + [f"D{i}"    for i in range(1, 22)] + ["LTP"]
    + [f"H4_{i}"  for i in range(1, 14)] + ["H4_LTP"]
    + [f"M30_{i}" for i in range(1, 9)]  + ["M30_LTP"]
    + [f"M5_{i}"  for i in range(1, 6)]  + ["M5_LTP"]

    # ---- metric blocks ----
    + [ "M_Max_23", "M_Min_23","LTP","Avg_23M", "M_LTP_Position",
       "M_Gap_Min_Max_%", "M_Gap_Max_LTP_%", "M_Gap_Min_LTP_%"]

    + ["W_Max_21", "W_Min_21", "LTP", "Avg_21W", "W_LTP_Position",
       "W_Gap_Min_Max_%", "W_Gap_Max_LTP_%", "W_Gap_Min_LTP_%"]

    + ["D_Max_21", "D_Min_21", "LTP", "Avg_21D", "D_LTP_Position",
       "D_Gap_Min_Max_%", "D_Gap_Max_LTP_%", "D_Gap_Min_LTP_%"]

    + ["H4_Max_13", "H4_Min_13", "LTP", "Avg_13H4", "H4_LTP_Position",
       "H4_Gap_Min_Max_%", "H4_Gap_Max_LTP_%", "H4_Gap_Min_LTP_%"]

    + ["M30_Max_8", "M30_Min_8", "LTP", "Avg_8M30", "M30_LTP_Position",
       "M30_Gap_Min_Max_%", "M30_Gap_Max_LTP_%", "M30_Gap_Min_LTP_%"]

    + ["M5_Max_5", "M5_Min_5", "LTP", "Avg_5M5", "M5_LTP_Position",
       "M5_Gap_Min_Max_%", "M5_Gap_Max_LTP_%", "M5_Gap_Min_LTP_%"]

    # ---- previous OHLC + fib zone ----
    + ["PM_Open", "PM_High", "PM_Low", "PM_Close", "PM_Fib50", "PM_Fib618"]
    + ["PW_Open", "PW_High", "PW_Low", "PW_Close", "PW_Fib50", "PW_Fib618"]
    + ["PD_Open", "PD_High", "PD_Low", "PD_Close", "PD_Fib50", "PD_Fib618"]

    # ---- candles + signals ----
    + ["Last_Month_Candle", "Last_Week_Candle", "Last_Day_Candle", "Live Candle", "Last_30min_Candle"]
    + candle_cols
    + ["Open_High", "Open_Low"]
    + ["RSI_Monthly", "RSI_Weekly", "RSI_Daily", "RSI_4H", "RSI_30m", "RSI_5m"]
    + ["VWAP_Daily"]
    + ["EMA_9", "EMA_21", "EMA_50", "EMA_200"]
    

    # ---- volume ----
    + ["Avg_7D_Vol", "Last_Day_Vol", "Live_Day_Vol"]
)

ordered_cols = [c for c in ordered_cols if c in df.columns]
df = df[ordered_cols]


# ===============================
# SAVE
# ===============================
file_name = f"all_nse_scanner_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
df.to_excel(file_name, index=False)

print(f"✅ Saved: {file_name}")
