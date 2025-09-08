# Simple PowerShell script to compress MoviePilot plugins
$PluginName = "ShowSubscriber"
$PluginPath = ".\plugins\$PluginName"

# Check if plugin directory exists
if (-not (Test-Path $PluginPath)) {
    Write-Error "Plugin directory not found: $PluginPath"
    exit 1
}

# Create zip file name without version
$ZipFileName = "${PluginName}.zip"

# Remove existing zip file
if (Test-Path $ZipFileName) {
    Remove-Item $ZipFileName -Force
}

# Compress plugin directory directly
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($PluginPath, $ZipFileName, [System.IO.Compression.CompressionLevel]::Optimal, $false)
    Write-Host "Plugin compressed successfully: $ZipFileName" -ForegroundColor Green
    Write-Host "File size: $((Get-Item $ZipFileName).Length / 1KB) KB" -ForegroundColor Green
} catch {
    Write-Error "Failed to compress plugin: $($_.Exception.Message)"
    exit 1
}