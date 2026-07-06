@echo off
REM ============================================================
REM  run_local.bat  -  full-universe scan on your home PC,
REM  then push data.json to GitHub so the dashboard updates.
REM
REM  EDIT the REPO path below to where you cloned the repo.
REM  Runs UNIVERSE=all (all ~2059 NSE stocks) on your home IP.
REM ============================================================

REM GitHub Desktop default clone path is Documents\GitHub\<repo>.
REM In GitHub Desktop: Repository menu -> "Show in Explorer" to confirm the exact path.
set REPO=C:\Users\Varsha Singh\Documents\GitHub\nse-scanner
set UNIVERSE=all
set WORKERS=4

cd /d "%REPO%" || (echo Repo folder not found: %REPO% & pause & exit /b 1)

echo === %date% %time%  starting full scan ===

REM 0) make sure dependencies are installed for THIS python (fast if already there)
python -m pip install -r requirements.txt --quiet --disable-pip-version-check

REM 1) sync to the latest cloud version (discard local generated files)
git fetch origin
git reset --hard origin/main

REM 2) generate full Excel on your home connection
python generate_scanner.py || (echo generate failed & pause & exit /b 1)

REM 3) build data.json for the dashboard
python export_dashboard_data.py || (echo export failed & pause & exit /b 1)

REM 4) publish to GitHub (dashboard auto-refreshes within ~10 min)
git add docs/data.json
git commit -m "local full-universe update %date% %time%"
git push origin main

echo === done ===
