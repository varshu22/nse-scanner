"""
read_excel.py -- load the generated scanner Excel into a DataFrame.
This is the DATA SOURCE (your script builds the Excel; we just read it).
Strategies consume the returned df directly (column names must match, e.g.
Symbol, LTP, Last_Month_Candle, PM_Open/High/Low/Close, PM_Fib50, PM_Fib618).
"""
import glob
import os
import pandas as pd


def latest_excel(pattern='all_nse_scanner_*.xlsx', explicit=None):
    if explicit and os.path.exists(explicit):
        return explicit
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"no Excel matching {pattern}")
    return files[-1]  # newest by name (date-stamped)


def load(path=None):
    xls = latest_excel(explicit=path)
    df = pd.read_excel(xls, sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]
    print(f"loaded {xls}: {len(df)} rows, {len(df.columns)} cols")
    return df


if __name__ == '__main__':
    import sys
    df = load(sys.argv[1] if len(sys.argv) > 1 else None)
    print(df.head(3).to_string())
