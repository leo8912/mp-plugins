# Schedule Upstream Sync Task
# This script sets up a scheduled task to automatically sync upstream repositories

# Define the path to the sync script
$ScriptPath = "D:\code\mp-plugins\sync_upstream.ps1"

# Define the action to run
$Action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`""

# Define the trigger (daily at 3 AM)
$Trigger = New-ScheduledTaskTrigger -Daily -At 3am

# Define settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register the scheduled task
$TaskName = "MoviePilot Upstream Sync"
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Automatically sync MoviePilot upstream repositories"

Write-Host "Scheduled task '$TaskName' has been created successfully!" -ForegroundColor Green
Write-Host "The task will run daily at 3 AM to sync upstream repositories." -ForegroundColor Yellow