<#
.SYNOPSIS
  Install Sunshine (game streaming host for Moonlight) and set it up for NVENC on the RTX 2080.

.DESCRIPTION
  - Installs Sunshine with winget if it isn't installed yet.
  - Sets these lines in Sunshine's config (backed up first, other settings kept):
      encoder      = nvenc
      nvenc_preset = 1        (P1: fastest, lowest latency; raise to 3-4 for better picture)
      max_bitrate  = 4000     (Kbps cap; fits the Tailscale relay path from Tijuana)
  - Adds a firewall rule that lets only Tailscale addresses (100.64.0.0/10) reach Sunshine's ports.
  - Restarts the Sunshine service if the config changed.

  Resolution (1280x720) and FPS (30) are chosen in Moonlight on the laptop, not here:
  Moonlight > Settings > Resolution 720p, Frame rate 30, Video bitrate 4 Mbps.

  Preview by default; -Apply makes the changes. Safe to re-run. Nothing is deleted.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Install-Sunshine.ps1 -Apply
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [int]$NvencPreset = 1,
    [int]$MaxBitrateKbps = 4000,
    [string]$ConfigPath = "$env:ProgramFiles\Sunshine\config\sunshine.conf"
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\PlexOptCommon.ps1"
Write-ModeBanner $Apply.IsPresent
if ($Apply) { Assert-Admin }
Assert-SafePath $ConfigPath 'Sunshine config'

Write-Step 'Sunshine'
$installed = Install-WingetPackage -Id 'LizardByte.Sunshine' -Name 'Sunshine' -Apply $Apply.IsPresent

Write-Step 'NVIDIA GPU'
$gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'NVIDIA' } | Select-Object -First 1
if ($gpu) { Write-Ok "$($gpu.Name), driver $($gpu.DriverVersion)" }
else { Write-Warn2 'No NVIDIA GPU found. NVENC needs the NVIDIA driver; Sunshine will fall back to software encoding.' }

Write-Step 'Sunshine config'
if (-not (Test-Path -LiteralPath $ConfigPath) -and -not $installed -and -not $Apply) {
    Write-Plan "Write $ConfigPath once Sunshine is installed"
}
$values = [ordered]@{
    'encoder'      = 'nvenc'
    'nvenc_preset' = [string]$NvencPreset
    'max_bitrate'  = [string]$MaxBitrateKbps
}
$changes = @()
if ($installed -or (Test-Path -LiteralPath (Split-Path -Parent $ConfigPath))) {
    $changes = Set-ConfigValues -Path $ConfigPath -Values $values -Apply $Apply.IsPresent
    if ($changes.Count -eq 0) { Write-Ok "Config already set: nvenc, preset P$NvencPreset, max $MaxBitrateKbps Kbps" }
    foreach ($c in $changes) { if ($Apply) { Write-Ok "set $c" } else { Write-Plan "set $c" } }
}

Write-Step 'Firewall (Tailscale only)'
Ensure-TailscaleFirewallRule -Name 'Sunshine over Tailscale (TCP)' -Protocol TCP -Ports @('47984', '47989', '47990', '48010') -Apply $Apply.IsPresent
Ensure-TailscaleFirewallRule -Name 'Sunshine over Tailscale (UDP)' -Protocol UDP -Ports @('47998-48000', '48002', '48010') -Apply $Apply.IsPresent

$svc = Get-Service -Name 'SunshineService', 'sunshinesvc', 'Sunshine*' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($svc) {
    if ($Apply -and $changes.Count -gt 0) {
        Restart-Service -InputObject $svc
        Write-Ok "Restarted $($svc.Name) to load the new config"
    } elseif ($svc.Status -ne 'Running') {
        if ($Apply) { Start-Service -InputObject $svc; Write-Ok "Started $($svc.Name)" }
        else { Write-Plan "Start the $($svc.Name) service (it is $($svc.Status))" }
    } else { Write-Ok "$($svc.Name) is running" }
} elseif ($Apply -and $installed) {
    Write-Warn2 'Sunshine service not found. Reboot, then re-run this script.'
}

Write-Host ''
Write-Host 'Next, on this PC: open https://localhost:47990, create the Sunshine username/password,'
Write-Host 'then pair Moonlight on the laptop (Add host 100.102.16.5, type the PIN into Sunshine > PIN).'
Write-Host 'Pair while you are still at home; the PIN page is easiest to reach from this PC.'
if (-not $Apply) { Write-Host 'Preview only. Re-run with -Apply to make these changes.' -ForegroundColor Cyan }
