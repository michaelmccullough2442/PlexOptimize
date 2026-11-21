<#
.SYNOPSIS
  Point the Plex libraries at the I: Seagate drive through Plex's local API.

.DESCRIPTION
  For each library in the map below, the script adds the I: folder to the library and, with
  -RemoveOldPaths, takes the old D:/F:/G:/H: folders out of the library. Taking a folder out of a
  library only changes Plex's list of folders: no file on any drive is touched.

  Safe order (each step is a separate re-run):
    1. .\Set-PlexLibraryPaths.ps1                        # preview
    2. .\Set-PlexLibraryPaths.ps1 -Apply                 # add I: folders and scan
    3. Check in Plex that the movies/shows/music show up from I:.
    4. .\Set-PlexLibraryPaths.ps1 -Apply -RemoveOldPaths # drop the old drive folders
  Old folders are only dropped from a library that already has its I: folder, so step 4 can't
  leave a library empty. Re-running any step changes nothing that is already right.

  -ConfigureTailscale also sets two Plex network settings so the laptop over Tailscale counts as a
  local, direct connection (fixes remote downloads and the 2 Mbps relay cap):
    - Custom server access URLs: http://<tailscale-ip>:32400
    - LAN Networks: adds 100.64.0.0/10 (the Tailscale range), keeping what is already there

  The thesis drive (E:\MAIN) is never added to Plex. If a library already lists a folder on it,
  the script warns, and -RemoveOldPaths drops it from the library (files stay as they are).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\Set-PlexLibraryPaths.ps1 -Apply -ConfigureTailscale
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$RemoveOldPaths,
    [switch]$CreateMissing,
    [switch]$ConfigureTailscale,
    [switch]$NoScan,
    [string]$PlexUrl = 'http://127.0.0.1:32400',
    [string]$Token = $env:PLEX_TOKEN,
    [string]$TailscaleIp = '',
    [string[]]$OldDrives = @('D', 'F', 'G', 'H'),
    # Library title -> folder on I: and the Plex library type used if -CreateMissing creates it.
    [System.Collections.IDictionary]$Map = [ordered]@{
        'Movies'      = @{ Path = 'I:\Plex\Movies';      Kind = 'movie' }
        'TV Shows'    = @{ Path = 'I:\Plex\TV Shows';    Kind = 'show' }
        'Music'       = @{ Path = 'I:\Plex\Music';       Kind = 'music' }
        'Remixes'     = @{ Path = 'I:\Plex\Remixes';     Kind = 'music' }
        'Game Cinema' = @{ Path = 'I:\Plex\GameCinema';  Kind = 'homevideo' }
        'Learning'    = @{ Path = 'I:\Plex\Learning';    Kind = 'homevideo' }
    }
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\PlexOptCommon.ps1"
Write-ModeBanner $Apply.IsPresent

# ---------- token + API helpers ----------
if (-not $Token) {
    try {
        $Token = (Get-ItemProperty -Path 'HKCU:\Software\Plex, Inc.\Plex Media Server' -Name PlexOnlineToken -ErrorAction Stop).PlexOnlineToken
    } catch { }
}
if (-not $Token) {
    throw "No Plex token. Run this as the Windows user Plex runs under, or pass -Token (see https://support.plex.tv/articles/204059436)."
}

function Invoke-Plex {
    param([string]$Path, [string]$Method = 'GET', [System.Collections.IEnumerable]$Query = @())
    $pairs = @()
    foreach ($q in $Query) { $pairs += ('{0}={1}' -f [uri]::EscapeDataString($q[0]), [uri]::EscapeDataString([string]$q[1])) }
    $pairs += 'X-Plex-Token=' + [uri]::EscapeDataString($Token)
    $sep = '?'; if ($Path.Contains('?')) { $sep = '&' }
    $uri = "$PlexUrl$Path$sep" + ($pairs -join '&')
    return Invoke-RestMethod -Uri $uri -Method $Method -Headers @{ Accept = 'application/json' } -UseBasicParsing
}

function Get-Sections {
    $mc = (Invoke-Plex '/library/sections').MediaContainer
    if (-not ($mc.PSObject.Properties.Name -contains 'Directory')) { return @() }
    return @($mc.Directory)
}

function Get-Locations($section) {
    if (-not ($section.PSObject.Properties.Name -contains 'Location')) { return @() }
    return @($section.Location | ForEach-Object { $_.path })
}

function Test-OldPath([string]$p) {
    if (Test-ProtectedPath $p) { return $true }
    if ($p -match '^([A-Za-z]):') { return $OldDrives -contains $Matches[1].ToUpper() }
    return $false
}

function Normalize([string]$p) { return $p.TrimEnd('\').ToLowerInvariant() }

try { $ident = (Invoke-Plex '/identity').MediaContainer }
catch { throw "Can't reach Plex at $PlexUrl. Is Plex Media Server running? ($($_.Exception.Message))" }
Write-Ok "Plex $($ident.version) reachable at $PlexUrl"

$prefsList = @((Invoke-Plex '/:/prefs').MediaContainer.Setting)
$prefs = @{}
foreach ($s in $prefsList) { $prefs[$s.id] = [string]$s.value }
if ($RemoveOldPaths -and $prefs['autoEmptyTrash'] -in @('1', 'true')) {
    Write-Warn2 "'Empty trash automatically after every scan' is on. Items Plex can't find at the new I: folder will lose their watch history when old folders are dropped. Check step 3 first."
}

# ---------- libraries ----------
$sections = Get-Sections
$toScan = @()
foreach ($title in @($Map.Keys)) {
    $target = $Map[$title].Path
    Assert-SafePath $target "library folder for '$title'"
    $section = $sections | Where-Object { $_.title -ieq $title } | Select-Object -First 1
    $haveFolder = Test-Path -LiteralPath $target

    if (-not $section) {
        if (-not $haveFolder) { Write-Host "  - '$title': no library and no $target folder, skipping"; continue }
        if (-not $CreateMissing) { Write-Plan "'$title' library doesn't exist. Re-run with -CreateMissing to create it on $target"; continue }
        $agent, $scanner, $type = switch ($Map[$title].Kind) {
            'movie'     { 'tv.plex.agents.movie',    'Plex Movie',               'movie' }
            'show'      { 'tv.plex.agents.series',   'Plex TV Series',           'show' }
            'music'     { 'tv.plex.agents.music',    'Plex Music',               'artist' }
            'homevideo' { 'com.plexapp.agents.none', 'Plex Video Files Scanner', 'movie' }
        }
        if (-not $Apply) { Write-Plan "Create '$title' ($($Map[$title].Kind)) on $target"; continue }
        Invoke-Plex '/library/sections' 'POST' @(@('name', $title), @('type', $type), @('agent', $agent),
            @('scanner', $scanner), @('language', 'en-US'), @('location', $target)) | Out-Null
        Write-Ok "Created '$title' on $target (Plex scans a new library by itself)"
        continue
    }

    $locs = Get-Locations $section
    $hasTarget = @($locs | Where-Object { (Normalize $_) -eq (Normalize $target) }).Count -gt 0
    foreach ($l in $locs) { if (Test-ProtectedPath $l) { Write-Warn2 "'$title' lists $l on the thesis drive. -RemoveOldPaths drops it from the library (files untouched)." } }

    $new = @($locs)
    if (-not $hasTarget) {
        if (-not $haveFolder) { Write-Bad "'$title': $target doesn't exist yet. Copy the media there first; library left as is."; continue }
        $new += $target
    }
    $dropped = @()
    if ($RemoveOldPaths) {
        if ($hasTarget) {
            $dropped = @($new | Where-Object { Test-OldPath $_ })
            $new = @($new | Where-Object { -not (Test-OldPath $_) })
        } else {
            Write-Host "  - '$title': keeping old folders until $target is in the library and scanned (re-run after this one)"
        }
    }
    if (($locs -join '|') -eq ($new -join '|')) {
        Write-Ok "'$title' already right: $($locs -join '; ')"
        $old = @($locs | Where-Object { Test-OldPath $_ })
        if ($old.Count -gt 0 -and -not $RemoveOldPaths) { Write-Host "         old folders still listed: $($old -join '; ') (drop with -RemoveOldPaths)" }
        continue
    }
    if (-not $hasTarget) { Write-Plan "'$title': add $target" }
    foreach ($d in $dropped) { Write-Plan "'$title': drop old folder $d from the library (files stay on disk)" }
    if (-not $Apply) { continue }

    $q = @(, @('agent', $section.agent))
    foreach ($l in $new) { $q += , @('location', $l) }
    Invoke-Plex "/library/sections/$($section.key)" 'PUT' $q | Out-Null
    Write-Ok "'$title' now: $($new -join '; ')"
    $toScan += $section
}

$unmapped = @($sections | Where-Object { -not (@($Map.Keys) -icontains $_.title) })
foreach ($s in $unmapped) {
    Write-Host "  - '$($s.title)' isn't in the map, left alone: $((Get-Locations $s) -join '; ')"
}
Write-Host "  Note: ROMs (I:\Games\...) are not a Plex library type. Use RetroArch / Moonlight for games."

if ($toScan.Count -gt 0 -and -not $NoScan) {
    foreach ($s in $toScan) { Invoke-Plex "/library/sections/$($s.key)/refresh" | Out-Null; Write-Ok "Scan started: $($s.title)" }
}

# ---------- Tailscale network settings ----------
if ($ConfigureTailscale) {
    Write-Step 'Plex network settings for Tailscale'
    if (-not $TailscaleIp) {
        $ts = Get-Command tailscale -ErrorAction SilentlyContinue
        if (-not $ts -and (Test-Path "$env:ProgramFiles\Tailscale\tailscale.exe")) { $ts = "$env:ProgramFiles\Tailscale\tailscale.exe" }
        if ($ts) { $TailscaleIp = (& $ts ip -4 2>$null | Select-Object -First 1) }
    }
    if (-not $TailscaleIp) { $TailscaleIp = '100.102.16.5'; Write-Warn2 "Couldn't ask Tailscale for this PC's IP, using $TailscaleIp" }
    $TailscaleIp = $TailscaleIp.Trim()

    $want = @{}
    $custom = @(([string]$prefs['customConnections']).Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $url = "http://${TailscaleIp}:32400"
    if ($custom -notcontains $url) { $want['customConnections'] = (@($custom) + $url) -join ',' }
    $lan = @(([string]$prefs['LanNetworksBandwidth']).Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if ($lan -notcontains '100.64.0.0/10') { $want['LanNetworksBandwidth'] = (@($lan) + '100.64.0.0/10') -join ',' }

    if ($want.Count -eq 0) { Write-Ok "Already set: custom URL $url, LAN networks include 100.64.0.0/10" }
    foreach ($k in $want.Keys) {
        if ($Apply) { Invoke-Plex '/:/prefs' 'PUT' @(, @($k, $want[$k])) | Out-Null; Write-Ok "$k = $($want[$k])" }
        else { Write-Plan "Set $k = $($want[$k]) (was '$($prefs[$k])')" }
    }
}

Write-Host ''
if (-not $Apply) { Write-Host 'Preview only. Re-run with -Apply to make these changes.' -ForegroundColor Cyan }
