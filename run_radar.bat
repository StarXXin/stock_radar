@echo off
rem stock_radar 启动脚本(计划任务/手动运行都走这里)
rem 用法:
rem   run_radar.bat              正常运行(采集->摘要->推送)
rem   run_radar.bat --dry-run    只采集+摘要+控制台打印,不推送不标记
cd /d "%~dp0"
py -3.11 main.py %*
