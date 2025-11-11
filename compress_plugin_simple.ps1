<#
.SYNOPSIS
    Simple PowerShell script to compress MoviePilot plugins

.DESCRIPTION
    This script compresses a MoviePilot plugin directory into a zip file.
    It checks if the plugin directory exists, removes any existing zip file,
    and creates a new compressed archive.

.PARAMETER PluginName
    The name of the plugin to compress (default: "tmdbstoryliner")

.EXAMPLE
    .\compress_plugin_simple.ps1
    .\compress_plugin_simple.ps1 -PluginName "myplugin"

.NOTES
    Author: leo
    Date: 2024
#>

param(
    [string]$PluginName = "tmdbstoryliner"
)

# Set plugin path and zip file name
$PluginPath = ".\plugins\$PluginName"
$ZipFileName = "${PluginName}.zip"

# Check if plugin directory exists
if (-not (Test-Path $PluginPath)) {
    Write-Error "Plugin directory not found: $PluginPath"
    exit 1
}

# Remove existing zip file if it exists
if (Test-Path $ZipFileName) {
    Remove-Item $ZipFileName -Force
    Write-Host "Removed existing zip file: $ZipFileName"
}

# Compress plugin directory
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $PluginPath, 
        $ZipFileName, 
        [System.IO.Compression.CompressionLevel]::Optimal, 
        $false
    )
    
    # Get file size in KB
    $fileSize = (Get-Item $ZipFileName).Length / 1KB
    
    Write-Host "Plugin compressed successfully: $ZipFileName" -ForegroundColor Green
    Write-Host "File size: $([math]::Round($fileSize, 2)) KB" -ForegroundColor Green
    Write-Host "Compression completed!" -ForegroundColor Green
    
} catch {
    Write-Error "Failed to compress plugin: $($_.Exception.Message)"
    exit 1
}