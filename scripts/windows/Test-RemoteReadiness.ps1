<#
.SYNOPSIS
  Read-only check that Plex, Sunshine, the SMB share and Tailscale are ready for remote use.

.DESCRIPTION
  Changes nothing. Run it on the home PC before the trip, and on the laptop with -FromLaptop
  (at home first, then again from Tijuana).

.EXAMPLE
  .\Test-RemoteReadiness.ps1                 # on the home PC
  .\Test-RemoteReadiness.ps1 -FromLaptop     # on the Acer laptop
#>
[CmdletBinding()]
param(
    [switch]$FromLaptop,
    [string]$HomeIp = '100.102.16.5',
    [string]$ShareName = 'Emulators'
)

$ErrorActionPreference = 'Continue'
. "$PSScriptRoot\PlexOptCommon.ps1"
$fails = 0
function Check([string]$name, [bool]$ok, [string]$hint = '') {
    if ($ok) { Write-Ok $name } else { Write-Bad "$name  $hint"; $script:fails++ }
}

Write-Step 'Tailscale'
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts -and (Test-Path "$env:ProgramFiles\Tailscale\tailscale.exe")) { $ts = "$env:ProgramFiles\Tailscale\tailscale.exe" }
Check 'Tailscale installed' ([bool]$ts) '(https://tailscale.com/download)'
if ($ts) {
    $myIp = (& $ts ip -4 2>$null | Select-Object -First 1)
    Check "Tailscale connected (this device: $myIp)" ([bool]$myIp) '(open Tailscale and sign in)'
    if ($FromLaptop) {
        $ping = (& $ts ping --c 3 $HomeIp 2>&1 | Out-String)
        Write-Host ($ping.Trim() -replace '(?m)^', '         ')
        if ($ping -match 'via DERP') { Write-Warn2 'Traffic is relayed (DERP). Expect ~5-10 Mbps: use 720p / 2-4 Mbps in Plex and Moonlight.' }
        elseif ($ping -match 'pong') { Write-Ok 'Direct connection (fastest)' }
        else { Check "Home PC $HomeIp answers" $false '(is the home PC on and signed in to Tailscale?)' }
        $nc = (& $ts netcheck 2>&1 | Out-String)
        if ($nc -match 'MappingVariesByDestIP:\s*true') { Write-Warn2 'This network has strict NAT; relayed (DERP) connections are expected here.' }
    }
}

if ($FromLaptop) {
    Write-Step "Home PC services at $HomeIp"
    foreach ($p in @(@(32400, 'Plex'), @(47989, 'Sunshine (Moonlight pairing)'), @(47984, 'Sunshine (stream setup)'), @(445, 'SMB share'))) {
        $r = Test-NetConnection -ComputerName $HomeIp -Port $p[0] -WarningAction SilentlyContinue
        Check "$($p[1]) port $($p[0])" ([bool]$r.TcpTestSucceeded)
    }
    if (Test-Path "\\$HomeIp\$ShareName") { Write-Ok "\\$HomeIp\$ShareName opens" }
    else { Write-Warn2 "\\$HomeIp\$ShareName didn't open without a login. Open it in File Explorer and sign in with the home PC account." }
} else {
    Write-Step 'Plex'
    $token = $env:PLEX_TOKEN
    if (-not $token) { try { $token = (Get-ItemProperty 'HKCU:\Software\Plex, Inc.\Plex Media Server' -Name PlexOnlineToken -ErrorAction Stop).PlexOnlineToken } catch { } }
    try {
        $h = @{ Accept = 'application/json' }
        $id = (Invoke-RestMethod "http://127.0.0.1:32400/identity" -Headers $h -UseBasicParsing).MediaContainer
        Check "Plex $($id.version) running" $true
        if ($token) {
            $secs = @((Invoke-RestMethod "http://127.0.0.1:32400/library/sections?X-Plex-Token=$token" -Headers $h -UseBasicParsing).MediaContainer.Directory)
            foreach ($s in $secs) {
                $locs = @($s.Location | ForEach-Object { $_.path })
                $onI = @($locs | Where-Object { $_ -like 'I:*' }).Count -gt 0
                $old = @($locs | Where-Object { $_ -match '^[DFGH]:' })
                $thesis = @($locs | Where-Object { Test-ProtectedPath $_ })
                Check "Library '$($s.title)' uses I:" $onI "(folders: $($locs -join '; '))"
                if ($old.Count) { Write-Warn2 "  '$($s.title)' still lists old drive folders: $($old -join '; ')" }
                Check "Library '$($s.title)' doesn't use the thesis drive" ($thesis.Count -eq 0)
            }
            $prefs = @{}
            foreach ($p in @((Invoke-RestMethod "http://127.0.0.1:32400/:/prefs?X-Plex-Token=$token" -Headers $h -UseBasicParsing).MediaContainer.Setting)) { $prefs[$p.id] = [string]$p.value }
            Check 'Plex custom URL includes the Tailscale IP' ($prefs['customConnections'] -match [regex]::Escape($HomeIp)) '(Set-PlexLibraryPaths.ps1 -Apply -ConfigureTailscale)'
            Check 'Plex treats Tailscale (100.64.0.0/10) as LAN' ($prefs['LanNetworksBandwidth'] -match '100\.64\.0\.0/10') '(Set-PlexLibraryPaths.ps1 -Apply -ConfigureTailscale)'
        } else { Write-Warn2 'No Plex token found, skipped the library checks' }
        try {
            $null = Invoke-RestMethod "http://${HomeIp}:32400/identity" -Headers $h -UseBasicParsing -TimeoutSec 5
            Check "Plex answers on the Tailscale IP $HomeIp" $true
        } catch { Check "Plex answers on the Tailscale IP $HomeIp" $false '(is Tailscale up on this PC?)' }
    } catch { Check 'Plex running' $false '(start Plex Media Server)' }

    Write-Step 'Sunshine'
    $svc = Get-Service -Name 'SunshineService', 'sunshinesvc', 'Sunshine*' -ErrorAction SilentlyContinue | Select-Object -First 1
    Check 'Sunshine service running' ([bool]($svc -and $svc.Status -eq 'Running')) '(Install-Sunshine.ps1 -Apply)'
    $listen = Get-NetTCPConnection -LocalPort 47989 -State Listen -ErrorAction SilentlyContinue
    Check 'Sunshine listening on 47989' ([bool]$listen)

    Write-Step 'SMB share'
    $share = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
    Check "Share '$ShareName' exists" ([bool]$share) '(New-EmulatorShare.ps1 -Apply)'
    if ($share) {
        $every = @(Get-SmbShareAccess -Name $ShareName | Where-Object { $_.AccountName -eq 'Everyone' })
        if ($every.Count) { Write-Warn2 "'$ShareName' allows Everyone (New-EmulatorShare.ps1 -Apply -RevokeEveryone)" }
    }

    Write-Step 'Firewall rules (Tailscale only)'
    foreach ($n in 'Sunshine over Tailscale (TCP)', 'Sunshine over Tailscale (UDP)', 'SMB over Tailscale') {
        Check "Rule '$n'" ([bool](Get-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue))
    }

    Write-Step 'Power (the PC must stay awake while you are away)'
    $sleep = (powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null | Out-String)
    if ($sleep -match 'Current AC Power Setting Index:\s*0x0+\s') { Write-Ok 'Sleep on AC power is off' }
    else { Write-Warn2 'The PC may go to sleep. Run: powercfg /change standby-timeout-ac 0' }
}

Write-Host ''
if ($fails -eq 0) { Write-Host 'All checks passed.' -ForegroundColor Green }
else { Write-Host "$fails check(s) failed. See docs\TIJUANA_CHECKLIST.md for fixes." -ForegroundColor Red }
