# NSE Strategy Scanner — auto-updating live dashboard

A stock screener that filters your NSE universe by trading strategies.
GitHub Actions rebuilds the data every 30 minutes during market hours and
publishes it; a GitHub-Pages dashboard auto-fetches it, so opening the page on
your phone always shows near-live results. **No server, no manual runs.**

## How it flows
```
GitHub Actions (every 30 min, market hours)
  1. generate_scanner.py      -> all_nse_scanner_<date>.xlsx   (your generator)
  2. run_scanner.py           -> runs frozen strategies (Telegram optional)
  3. export_dashboard_data.py -> docs/data.json  (timestamped)
  4. git commit docs/data.json
        |
        v
GitHub Pages serves docs/index.html  (the dashboard)
        |
        v
Dashboard fetches docs/data.json on load + every 10 min  ->  you, on any device
```

## Files
| File | Role |
|---|---|
| `generate_scanner.py` | Your generator — builds `all_nse_scanner_<date>.xlsx` |
| `run_scanner.py` + `strategies/` | Runs frozen strategies (S1 Doji now) |
| `export_dashboard_data.py` | Writes `docs/data.json` for the dashboard |
| `docs/index.html` | The dashboard (served by GitHub Pages) |
| `.github/workflows/scan.yml` | 30-min schedule + build + commit |
| `symbols.txt` | Fallback NSE universe if NSE blocks the runner |

## Setup — do these once (~15 min)

### 1. Create the repo
Free GitHub account → new repo (public is simplest for Pages; private works on
paid plans). Upload every file, keeping the folder structure
(`docs/`, `strategies/`, `.github/workflows/`).

### 2. Allow the Action to commit data back
Repo → **Settings → Actions → General → Workflow permissions** →
select **Read and write permissions** → Save.
(The workflow also declares `permissions: contents: write`.)

### 3. Turn on GitHub Pages
Repo → **Settings → Pages** → Source = **Deploy from a branch** →
Branch = **main**, Folder = **/docs** → Save.
Your dashboard URL will be: `https://<your-username>.github.io/<repo-name>/`

### 4. First run (creates the first data.json)
Repo → **Actions** → enable workflows → open **NSE Scanner** →
**Run workflow**. For a fast first test, set the `limit` input to `50`.
When it finishes, it commits `docs/data.json`.

### 5. Open the dashboard
Visit your Pages URL. It loads the sample instantly, then swaps in the live
`data.json`. On your phone, use the browser's **Add to Home Screen** so it opens
like an app.

### 6. (Optional, later) Telegram alerts
Add repo secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` and step 2 will
also message you. Skip for now — the dashboard works without it.

## The dashboard
- Trading-style pills (All / Scalping / Intraday / Swing / Positional).
- Strategy chips (S1 Doji Breakout now; more drop in as you freeze them).
- Filters: signal type, RSI (daily/monthly), last-day candle, price vs EMA,
  min volume, symbol search. Sortable results table + summary cards.
- "Refresh" button + auto-refresh every 10 min. "Load Excel" lets you open a
  local file manually too.

## Timing note
Your generator fetches ~2,000 symbols × 6 timeframes. Do a full manual run once
and check the Actions log duration. If it approaches 30 min, raise `WORKERS`,
trim timeframes for the 30-min job, or widen the cron interval. Knobs:
`WORKERS` and `LIMIT` env vars.

## Strategies (6 frozen)
**Positional — Doji Breakout** (prev candle = Doji, LTP crosses):
- Prev Month Doji Breakout, Prev Week Doji Breakout, Prev Day Doji Breakout
- Signals: Above High, Above Close, Golden Zone (0.5-0.618)

**Swing — Rectangle Breakout** (rectangle from last N closes; Max=upper, Min=lower):
- 23-Month, 21-Week, 21-Day Rectangle Breakout
- Signals: Upper Breakout (0-5% above Max), Near Upper (within 2% below Max),
  Lower Breakdown (0-5% below Min), Near Lower (within 2% above Min)
- Range-width filter: Very narrow <=10%, Narrow <=25%, Medium <=50%, Wide >50%

All 6 run from the single generated Excel (no second file needed). Extra filters
(RSI, candle, EMA, volume, symbol) stack on top of any strategy.

## Add a future strategy
1. `strategies/strategyN_xxx.py` with `run(df)` returning a DataFrame.
2. Add it to `STRATEGIES` in `run_scanner.py`.
3. Add a matching entry to the `STRATEGIES` array in `docs/index.html` so it
   appears as a filter chip. Same schedule, same dashboard.
