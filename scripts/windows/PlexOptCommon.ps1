# Shared helpers for the PlexOptimize Windows setup scripts.
# Dot-source it:  . "$PSScriptRoot\PlexOptCommon.ps1"
#
# Two rules every script follows:
#   1. Nothing on the thesis drive (E:\MAIN, the volume labelled MAIN) is read, changed or added anywhere.
#   2. Nothing is deleted. Config files are backed up to a timestamped copy before they change.
# Every script previews by default and only changes things with -Apply, so it is safe to re-run.

# Drive letters that are always off limits. The volume labelled MAIN is added at run time,
# so the thesis drive stays protected even if Windows gives it another letter.
$script:ProtectedDriveLetters = @('E')
$script:ProtectedRoots = @('E:\MAIN')

function Get-ProtectedDriveLetters {
    $letters = @($script:ProtectedDriveLetters)
    try {
        $main = Get-Volume -ErrorAction Stop | Where-Object { $_.FileSystemLabel -eq 'MAIN' -and $_.DriveLetter }
        foreach ($v in $main) { $letters += [string]$v.DriveLetter }
    } catch { }
    return @($letters | ForEach-Object { $_.ToUpper() } | Select-Object -Unique)
}

function Test-ProtectedPath {
    param([Parameter(Mandatory)][string]$Path)
    $p = $Path.Trim().Trim('"')
    if ($p -match '^\\\\\?\\') { $p = $p.Substring(4) }
    foreach ($root in $script:ProtectedRoots) {
        if ($p.TrimEnd('\') -ieq $root -or $p -like "$root\*") { return $true }
    }
    if ($p -match '^([A-Za-z]):') {
        return (Get-ProtectedDriveLetters) -contains $Matches[1].ToUpper()
    }
    return $false
}

function Assert-SafePath {
    param([Parameter(Mandatory)][string]$Path, [string]$What = 'path')
    if (Test-ProtectedPath $Path) {
        throw "Refusing to use $What '$Path': it is on the protected thesis drive (E:\MAIN). Nothing on that drive is touched."
    }
}

function Write-Step  { param([string]$Msg) Write-Host "==> $Msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "[OK]   $Msg" -ForegroundColor Green }
function Write-Plan  { param([string]$Msg) Write-Host "[PLAN] $Msg" -ForegroundColor Yellow }
function Write-Warn2 { param([string]$Msg) Write-Host "[WARN] $Msg" -ForegroundColor Magenta }
function Write-Bad   { param([string]$Msg) Write-Host "[X]    $Msg" -ForegroundColor Red }

function Write-ModeBanner {
    param([bool]$Apply)
    if ($Apply) { Write-Host "Mode: APPLY (changes will be made, nothing is deleted)" -ForegroundColor Yellow }
    else        { Write-Host "Mode: PREVIEW (nothing changes; re-run with -Apply to make the changes)" -ForegroundColor Cyan }
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-Admin {
    if (-not (Test-IsAdmin)) { throw "Run this from a PowerShell window opened with 'Run as administrator'." }
}

# Copy a file next to itself as <name>.bak-<timestamp> before changing it. Never removes anything.
function Backup-File {
    param([Parameter(Mandatory)][string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $dest = "$Path.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item -LiteralPath $Path -Destination $dest
        Write-Ok "Backed up $Path -> $dest"
    }
}

# Set "key = value" lines in a simple key=value config (sunshine.conf, retroarch.cfg).
# Existing keys are replaced in place, missing ones are appended, everything else is kept.
# Returns the list of keys that changed; writes only if -Apply and something changed.
function Set-ConfigValues {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][System.Collections.IDictionary]$Values,
        [switch]$Quote,
        [bool]$Apply = $false
    )
    $lines = @()
    if (Test-Path -LiteralPath $Path) { $lines = @(Get-Content -LiteralPath $Path) }
    $changed = @()
    $seen = @{}
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        $replaced = $false
        foreach ($k in $Values.Keys) {
            if ($line -match "^\s*$([regex]::Escape($k))\s*=\s*(.*)$") {
                $seen[$k] = $true
                $current = $Matches[1].Trim().Trim('"')
                $want = [string]$Values[$k]
                if ($current -ne $want) {
                    $changed += "$k : '$current' -> '$want'"
                    if ($Quote) { $out.Add("$k = `"$want`"") } else { $out.Add("$k = $want") }
                    $replaced = $true
                }
                break
            }
        }
        if (-not $replaced) { $out.Add($line) }
    }
    foreach ($k in $Values.Keys) {
        if (-not $seen.ContainsKey($k)) {
            $want = [string]$Values[$k]
            $changed += "$k : (not set) -> '$want'"
            if ($Quote) { $out.Add("$k = `"$want`"") } else { $out.Add("$k = $want") }
        }
    }
    if ($changed.Count -gt 0 -and $Apply) {
        Backup-File $Path
        $dir = Split-Path -Parent $Path
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
        # UTF-8 without a BOM: both Sunshine and RetroArch read it.
        [IO.File]::WriteAllLines($Path, $out.ToArray(), (New-Object Text.UTF8Encoding $false))
    }
    return ,$changed
}

function Test-WingetPackage {
    param([Parameter(Mandatory)][string]$Id)
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }
    $res = winget list --id $Id --exact --accept-source-agreements 2>$null | Out-String
    return ($res -match [regex]::Escape($Id))
}

function Install-WingetPackage {
    param([Parameter(Mandatory)][string]$Id, [string]$Name = $Id, [bool]$Apply = $false)
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Bad "winget is not available. Install '$Name' by hand, then re-run this script."
        return $false
    }
    if (Test-WingetPackage $Id) { Write-Ok "$Name is already installed"; return $true }
    if (-not $Apply) { Write-Plan "Install $Name (winget id $Id)"; return $false }
    Write-Step "Installing $Name"
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements | Out-Host
    if (Test-WingetPackage $Id) { Write-Ok "$Name installed"; return $true }
    Write-Bad "$Name did not install. Check the winget output above."
    return $false
}

# Inbound firewall rule that only accepts Tailscale addresses (100.64.0.0/10). Created once, by name.
function Ensure-TailscaleFirewallRule {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][ValidateSet('TCP', 'UDP')][string]$Protocol,
        [Parameter(Mandatory)][string[]]$Ports,
        [bool]$Apply = $false
    )
    if (Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue) {
        Write-Ok "Firewall rule '$Name' already exists"
        return
    }
    if (-not $Apply) { Write-Plan "Add firewall rule '$Name' ($Protocol $($Ports -join ',') from Tailscale 100.64.0.0/10 only)"; return }
    New-NetFirewallRule -DisplayName $Name -Direction Inbound -Action Allow -Protocol $Protocol `
        -LocalPort $Ports -RemoteAddress '100.64.0.0/10' -Profile Any | Out-Null
    Write-Ok "Added firewall rule '$Name'"
}
