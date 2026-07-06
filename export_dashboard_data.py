"""
export_dashboard_data.py
Reads the newest all_nse_scanner_<date>.xlsx and writes docs/data.json
(columnar, timestamped) for the GitHub-Pages dashboard to fetch.
"""
import json, os, glob
import datetime as dt
import pandas as pd

COLS = ['Symbol','FnO','LTP','M23','Last_Month_Candle','Last_Week_Candle','Last_Day_Candle','Live Candle','Last_30min_Candle',
'PM_Open','PM_High','PM_Low','PM_Close','PM_Fib50','PM_Fib618',
'PW_High','PW_Close','PW_Fib50','PW_Fib618','PD_High','PD_Close','PD_Fib50','PD_Fib618',
'M_Max_23','M_Min_23','M_Gap_Min_Max_%','M_Gap_Max_LTP_%','M_Gap_Min_LTP_%',
'W_Max_21','W_Min_21','W_Gap_Min_Max_%','W_Gap_Max_LTP_%','W_Gap_Min_LTP_%',
'D_Max_21','D_Min_21','D_Gap_Min_Max_%','D_Gap_Max_LTP_%','D_Gap_Min_LTP_%',
'H4_Max_13','H4_Min_13','H4_Gap_Min_Max_%','H4_Gap_Max_LTP_%','H4_Gap_Min_LTP_%',
'M30_Max_8','M30_Min_8','M30_Gap_Min_Max_%','M30_Gap_Max_LTP_%','M30_Gap_Min_LTP_%',
'M5_Max_5','M5_Min_5','M5_Gap_Min_Max_%','M5_Gap_Max_LTP_%','M5_Gap_Min_LTP_%',
'RSI_Monthly','RSI_Weekly','RSI_Daily','RSI_4H','RSI_30m','RSI_5m',
'EMA_9','EMA_21','EMA_50','EMA_200','VWAP_Daily',
'M_LTP_Position','W_LTP_Position','D_LTP_Position','H4_LTP_Position','M30_LTP_Position','M5_LTP_Position',
'Open_High','Open_Low','Avg_7D_Vol','Last_Day_Vol']


def latest():
    files = sorted(glob.glob('all_nse_scanner_*.xlsx'))
    if not files:
        raise FileNotFoundError('no all_nse_scanner_*.xlsx found')
    return files[-1]


def main():
    xls = latest()
    df = pd.read_excel(xls, sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]
    # keep first occurrence of duplicated names (e.g. repeated LTP)
    df = df.loc[:, ~df.columns.duplicated()]
    use = [c for c in COLS if c in df.columns]
    sub = df[use].copy()
    # round floats, JSON-safe
    data = [[None if pd.isna(v) else (round(v, 2) if isinstance(v, float) else v)
             for v in row] for row in sub.itertuples(index=False, name=None)]
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    payload = {
        'generated': dt.datetime.now(ist).strftime('%Y-%m-%d %H:%M IST'),
        'source': xls,
        'columns': use,
        'data': data,
    }
    os.makedirs('docs', exist_ok=True)
    with open('docs/data.json', 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    print(f"wrote docs/data.json: {len(data)} rows, {len(use)} cols, from {xls}")


if __name__ == '__main__':
    main()
