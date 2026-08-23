# Register Windows scheduled task: runs via uv (Python 3.12 venv in project dir)
# Usage: run in admin PowerShell  .\install_task.ps1
# Uninstall: Unregister-ScheduledTask -TaskName "stock_radar" -Confirm:$false

$dir = "D:\work\AIproject\stock_radar"
$action = New-ScheduledTaskAction -Execute "uv.exe" -Argument "run python main.py" -WorkingDirectory $dir
$trigger1 = New-ScheduledTaskTrigger -Daily -At 8:30am   # pre-market
$trigger2 = New-ScheduledTaskTrigger -Daily -At 6:30pm   # post-market
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName "stock_radar" `
    -Action $action -Trigger $trigger1, $trigger2 `
    -Settings $settings `
    -Description "Stock notice radar (daily 8:30 / 18:30)" -Force

Write-Host "Scheduled task 'stock_radar' registered. Test run:" -ForegroundColor Green
Write-Host "  Start-ScheduledTask -TaskName stock_radar"
