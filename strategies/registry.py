"""
registry.py -- all frozen strategies in one place (mirrors the dashboard).
Each entry: {name, style, run(df)->DataFrame of flagged stocks}.

Positional  : Prev Month/Week/Day Doji Breakout  (Above High / Above Close / Golden Zone)
Swing       : 23-Month / 21-Week / 21-Day Rectangle Breakout
              (Upper Breakout / Near Upper / Lower Breakdown / Near Lower)
"""
import pandas as pd


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def doji_run(prefix, candle_field, name, style):
    def run(df):
        out = []
        for _, r in df.iterrows():
            if str(r.get(candle_field)) != 'Doji':
                continue
            ltp = _num(r.get('LTP'))
            cl = _num(r.get(prefix + '_Close'))
            if cl is None and prefix == 'PM':
                cl = _num(r.get('M23'))
            if ltp is None or cl is None:
                continue
            hi = _num(r.get(prefix + '_High'))
            f50 = _num(r.get(prefix + '_Fib50')); f618 = _num(r.get(prefix + '_Fib618'))
            if hi is not None and ltp >= hi:
                sig, ref = 'Above High', hi
            elif ltp >= cl:
                sig, ref = 'Above Close', cl
            elif f50 is not None and f618 is not None and f50 <= ltp <= f618:
                sig, ref = 'Golden Zone', f50
            else:
                continue
            out.append({'Symbol': r['Symbol'], 'LTP': ltp, 'Strategy': name,
                        'Signal': sig, 'Level': ref,
                        'Gap%': round((ltp - cl) / cl * 100, 2) if cl else None,
                        'RSI_Monthly': r.get('RSI_Monthly'), 'RSI_Daily': r.get('RSI_Daily')})
        return pd.DataFrame(out)
    return {'name': name, 'style': style, 'run': run}


def rect_run(maxc, minc, gmm, gmax, gmin, name, style):
    def run(df):
        out = []
        for _, r in df.iterrows():
            gu = _num(r.get(gmax)); gl = _num(r.get(gmin))
            if gu is None or gl is None:
                continue
            mx = _num(r.get(maxc)); mn = _num(r.get(minc)); rng = _num(r.get(gmm))
            if 0 < gu <= 5:
                sig, ref, gap = 'Upper Breakout', mx, gu
            elif -2 <= gu <= 0:
                sig, ref, gap = 'Near Upper', mx, gu
            elif -5 <= gl < 0:
                sig, ref, gap = 'Lower Breakdown', mn, gl
            elif 0 <= gl <= 2:
                sig, ref, gap = 'Near Lower', mn, gl
            else:
                continue
            out.append({'Symbol': r['Symbol'], 'LTP': _num(r.get('LTP')), 'Strategy': name,
                        'Signal': sig, 'Level': ref, 'Gap%': gap, 'Range%': rng,
                        'RSI_Monthly': r.get('RSI_Monthly'), 'RSI_Daily': r.get('RSI_Daily')})
        return pd.DataFrame(out)
    return {'name': name, 'style': style, 'run': run}


STRATEGIES = [
    doji_run('PM', 'Last_Month_Candle', 'Prev Month Doji Breakout', 'Positional'),
    doji_run('PW', 'Last_Week_Candle',  'Prev Week Doji Breakout',  'Positional'),
    doji_run('PD', 'Last_Day_Candle',   'Prev Day Doji Breakout',   'Positional'),
    rect_run('M_Max_23', 'M_Min_23', 'M_Gap_Min_Max_%', 'M_Gap_Max_LTP_%', 'M_Gap_Min_LTP_%', '23-Month Rect Breakout', 'Swing'),
    rect_run('W_Max_21', 'W_Min_21', 'W_Gap_Min_Max_%', 'W_Gap_Max_LTP_%', 'W_Gap_Min_LTP_%', '21-Week Rect Breakout', 'Swing'),
    rect_run('D_Max_21', 'D_Min_21', 'D_Gap_Min_Max_%', 'D_Gap_Max_LTP_%', 'D_Gap_Min_LTP_%', '21-Day Rect Breakout', 'Swing'),
    rect_run('H4_Max_13', 'H4_Min_13', 'H4_Gap_Min_Max_%', 'H4_Gap_Max_LTP_%', 'H4_Gap_Min_LTP_%', '4H Rect Breakout (13)', 'Intraday'),
    rect_run('M30_Max_8', 'M30_Min_8', 'M30_Gap_Min_Max_%', 'M30_Gap_Max_LTP_%', 'M30_Gap_Min_LTP_%', '30min Rect Breakout (8)', 'Intraday'),
    rect_run('M5_Max_5', 'M5_Min_5', 'M5_Gap_Min_Max_%', 'M5_Gap_Max_LTP_%', 'M5_Gap_Min_LTP_%', '5min Rect Breakout (5)', 'Scalping'),
]
