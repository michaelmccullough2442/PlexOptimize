<#
.SYNOPSIS
  Install RetroArch (desktop version) and point its file browser at the ROMs on I:.

.DESCRIPTION
  - Installs RetroArch with winget if it isn't installed yet.
  - Creates I:\Games\Emulators\RetroArch\roms if it is missing (never removes anything).
  - Sets rgui_browser_directory in retroarch.cfg (backed up first, other settings kept), so
    Load Content opens in the ROM folder.

  Close RetroArch before -Apply: it rewrites retroarch.cfg when it exits.
  Preview by default; -Apply makes the changes. Safe to re-run.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Install-RetroArch.ps1 -Apply
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$RomPath = 'I:\Games\Emulators\RetroArch\roms',
    [string]$InstallDir = ''
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\PlexOptCommon.ps1"
Write-ModeBanner $Apply.IsPresent
Assert-SafePath $RomPath 'ROM folder'

Write-Step 'RetroArch'
$installed = Install-WingetPackage -Id 'Libretro.RetroArch' -Name 'RetroArch' -Apply $Apply.IsPresent

function Find-RetroArchDir {
    $candidates = @()
    if ($InstallDir) { $candidates += $InstallDir }
    $candidates += 'C:\RetroArch-Win64', "$env:ProgramFiles\RetroArch", "${env:ProgramFiles(x86)}\RetroArch", "$env:APPDATA\RetroArch"
    $uninstall = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
                 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
                 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    foreach ($k in Get-ItemProperty $uninstall -ErrorAction SilentlyContinue) {
        if ($k.PSObject.Properties.Name -contains 'DisplayName' -and $k.DisplayName -match 'RetroArch' -and
            $k.PSObject.Properties.Name -contains 'InstallLocation' -and $k.InstallLocation) { $candidates += $k.InstallLocation }
    }
    foreach ($c in $candidates) { if ($c -and (Test-Path -LiteralPath (Join-Path $c 'retroarch.exe'))) { return $c } }
    return $null
}

$dir = Find-RetroArchDir
if ($dir) { Write-Ok "RetroArch found in $dir"; Assert-SafePath $dir 'RetroArch folder' }
elseif ($Apply -and $installed) { Write-Warn2 "RetroArch installed but retroarch.exe wasn't found. Pass -InstallDir <folder> and re-run." }

Write-Step 'ROM folder'
if (Test-Path -LiteralPath $RomPath) {
    $count = @(Get-ChildItem -LiteralPath $RomPath -File -Recurse -ErrorAction SilentlyContinue).Count
    Write-Ok "$RomPath exists ($count files)"
} elseif ($Apply) {
    New-Item -ItemType Directory -Path $RomPath -Force | Out-Null
    Write-Ok "Created $RomPath"
} else { Write-Plan "Create $RomPath" }

if ($dir) {
    Write-Step 'retroarch.cfg'
    if (Get-Process retroarch -ErrorAction SilentlyContinue) {
        Write-Warn2 'RetroArch is running. Close it first, or it will overwrite this change when it exits.'
        if ($Apply) { throw 'Close RetroArch and re-run.' }
    }
    $cfg = Join-Path $dir 'retroarch.cfg'
    $changes = Set-ConfigValues -Path $cfg -Values ([ordered]@{ 'rgui_browser_directory' = $RomPath }) -Quote -Apply $Apply.IsPresent
    if ($changes.Count -eq 0) { Write-Ok "Load Content already opens in $RomPath" }
    foreach ($c in $changes) { if ($Apply) { Write-Ok "set $c" } else { Write-Plan "set $c" } }
}

Write-Host ''
Write-Host 'Next: open RetroArch > Main Menu > Online Updater > Core Downloader and get the cores you need'
Write-Host '(Dolphin for Wii/GameCube, PCSX2 / LRPS2 for PS2, SwanStation or Beetle PSX for PS1, FinalBurn Neo for Arcade).'
Write-Host 'PS1/PS2 also need their BIOS files in the RetroArch "system" folder. Play one game to check.'
if (-not $Apply) { Write-Host 'Preview only. Re-run with -Apply to make these changes.' -ForegroundColor Cyan }
