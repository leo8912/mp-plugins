# Sync Upstream Repositories Script
# Automatically sync MoviePilot and related repositories

Write-Host "Starting to sync upstream repositories..." -ForegroundColor Green

# Create origin directory if it doesn't exist
if (!(Test-Path -Path "origin")) {
    New-Item -ItemType Directory -Path "origin" | Out-Null
}
Set-Location -Path "origin"

# Sync MoviePilot repository
Write-Host "Syncing MoviePilot repository..." -ForegroundColor Yellow
if (!(Test-Path -Path "MoviePilot")) {
    git clone https://github.com/jxxghp/MoviePilot.git
}
Set-Location -Path "MoviePilot"
git fetch origin
git reset --hard origin/main
git clean -f

# Sync MoviePilot-Frontend repository
Write-Host "Syncing MoviePilot-Frontend repository..." -ForegroundColor Yellow
Set-Location -Path ".."
if (!(Test-Path -Path "MoviePilot-Frontend")) {
    git clone https://github.com/jxxghp/MoviePilot-Frontend.git
}
Set-Location -Path "MoviePilot-Frontend"
git fetch origin
git reset --hard origin/main
git clean -f

# Sync MoviePilot-Plugins repository
Write-Host "Syncing MoviePilot-Plugins repository..." -ForegroundColor Yellow
Set-Location -Path ".."
if (!(Test-Path -Path "MoviePilot-Plugins")) {
    git clone https://github.com/jxxghp/MoviePilot-Plugins.git
}
Set-Location -Path "MoviePilot-Plugins"
git fetch origin
git reset --hard origin/main
git clean -f

# Sync MoviePilot-Resources repository
Write-Host "Syncing MoviePilot-Resources repository..." -ForegroundColor Yellow
Set-Location -Path ".."
if (!(Test-Path -Path "MoviePilot-Resources")) {
    git clone https://github.com/jxxghp/MoviePilot-Resources.git
}
Set-Location -Path "MoviePilot-Resources"
git fetch origin
git reset --hard origin/main
git clean -f

# Return to root directory
Set-Location -Path "..\.."

Write-Host "Upstream repositories sync completed!" -ForegroundColor Green