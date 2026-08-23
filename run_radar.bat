@echo off
rem stock_radar launcher (scheduled task / manual run)
rem Usage:
rem   run_radar.bat              normal run (fetch -> summarize -> push)
rem   run_radar.bat --dry-run    fetch + summarize + console only, no push/mark
cd /d "%~dp0"
py -3.11 main.py %*
