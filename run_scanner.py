"""
run_scanner.py -- orchestrator (Excel-as-source)
read latest generated Excel -> run every frozen strategy (registry) -> Telegram.
"""
import os, sys
import datetime as dt
import pandas as pd

import read_excel
import telegram_alert
from strategies.registry import STRATEGIES


def main():
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    ts = dt.datetime.now(ist).strftime('%Y-%m-%d %H:%M IST')
    print(f"=== scan {ts} ===")
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('DATA_FILE')
    df = read_excel.load(path)

    results = {}
    for st in STRATEGIES:
        try:
            res = st['run'](df)
        except Exception as e:
            print(f"strategy {st['name']} failed: {e}")
            res = pd.DataFrame()
        results[st['name']] = res
        if res is not None and not res.empty:
            print(f"  {st['name']}: {len(res)} matches")

    msg = telegram_alert.format_results(results, ts)
    telegram_alert.send(msg)
    print("done.")


if __name__ == '__main__':
    main()
