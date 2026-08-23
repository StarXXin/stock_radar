# 注册 Windows 计划任务:每个交易日盘前/盘后各跑一次
# 用法: 管理员 PowerShell 里执行  .\install_task.ps1
# 卸载: Unregister-ScheduledTask -TaskName "stock_radar" -Confirm:$false

$dir = "D:\work\AIproject\stock_radar"
$action = New-ScheduledTaskAction -Execute "$dir\run_radar.bat" -WorkingDirectory $dir
$trigger1 = New-ScheduledTaskTrigger -Daily -At 8:30am   # 盘前
$trigger2 = New-ScheduledTaskTrigger -Daily -At 6:30pm   # 盘后
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName "stock_radar" `
    -Action $action -Trigger $trigger1, $trigger2 `
    -Settings $settings `
    -Description "自选股公告雷达(每天 8:30 / 18:30)" -Force

Write-Host "已注册计划任务 stock_radar。手动试跑一次确认:" -ForegroundColor Green
Write-Host "  Start-ScheduledTask -TaskName stock_radar"
