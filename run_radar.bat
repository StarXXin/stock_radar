@echo off
rem stock_radar launcher (scheduled task / manual run), runs via uv (Python 3.12 venv)
rem Usage:
rem   run_radar.bat              normal run (fetch -> summarize -> push)
rem   run_radar.bat --dry-run    fetch + summarize + console only, no push/mark
cd /d "%~dp0"
uv run python main.py %*
