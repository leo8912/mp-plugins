# Sync Upstream Repositories Script
# Automatically sync MoviePilot and MoviePilot-Plugins repositories

Write-Host "Starting to sync upstream repositories..." -ForegroundColor Green

# Sync MoviePilot repository
Write-Host "Syncing MoviePilot repository..." -ForegroundColor Yellow
Set-Location -Path "origin\MoviePilot"
git fetch origin
git reset --hard origin/v2
git clean -f

# Sync MoviePilot-Plugins repository
Write-Host "Syncing MoviePilot-Plugins repository..." -ForegroundColor Yellow
Set-Location -Path "..\MoviePilot-Plugins"
git fetch origin
git reset --hard origin/main
git clean -f

# Return to root directory
Set-Location -Path "..\.."

Write-Host "Upstream repositories sync completed!" -ForegroundColor Green