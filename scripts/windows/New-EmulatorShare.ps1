<#
.SYNOPSIS
  Share I:\Games\Emulators over SMB to your own Windows account only, reachable over Tailscale.

.DESCRIPTION
  - Creates the share "Emulators" -> I:\Games\Emulators with Full access for your account only
    (not Everyone). From the laptop: \\100.102.16.5\Emulators
  - If the share already exists on that folder, it only makes sure your account has Full access.
    An existing "Everyone" entry is reported; -RevokeEveryone takes it off the share.
  - Adds a firewall rule for SMB (TCP 445) from Tailscale addresses (100.64.0.0/10) only, so the
    share isn't opened to other networks the PC joins.
  Files and folders are never removed. Preview by default; -Apply makes the changes. Safe to re-run.

  When the laptop asks for a login, use this PC's account: for a Microsoft account that's the
  email and password (not the PIN); for a local account it's PCNAME\username and its password.
  Windows won't share to an account with a blank password.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\New-EmulatorShare.ps1 -Apply
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$RevokeEveryone,
    [string]$Path = 'I:\Games\Emulators',
    [string]$ShareName = 'Emulators',
    [string]$Account = "$env:USERDOMAIN\$env:USERNAME"
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\PlexOptCommon.ps1"
Write-ModeBanner $Apply.IsPresent
Assert-Admin
Assert-SafePath $Path 'share folder'

if (-not (Test-Path -LiteralPath $Path)) { throw "$Path doesn't exist. Is the Seagate drive plugged in as I:?" }

Write-Step "SMB share '$ShareName'"
$share = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($share -and ($share.Path.TrimEnd('\') -ine $Path.TrimEnd('\'))) {
    throw "A share named '$ShareName' already points at $($share.Path). Pass -ShareName <other name>; the existing share is left alone."
}
if (-not $share) {
    $other = Get-SmbShare -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.TrimEnd('\') -ieq $Path.TrimEnd('\') }
    foreach ($o in $other) { Write-Warn2 "$Path is also shared as '$($o.Name)' (left as is)." }
    if ($Apply) {
        New-SmbShare -Name $ShareName -Path $Path -FullAccess $Account -Description 'PlexOptimize: ROMs and emulator configs' | Out-Null
        Write-Ok "Shared $Path as \\$env:COMPUTERNAME\$ShareName (Full access: $Account)"
    } else { Write-Plan "Share $Path as '$ShareName' with Full access for $Account only" }
} else {
    $access = @(Get-SmbShareAccess -Name $ShareName)
    $mine = $access | Where-Object { $_.AccountName -ieq $Account -and $_.AccessRight -eq 'Full' -and $_.AccessControlType -eq 'Allow' }
    if ($mine) { Write-Ok "'$ShareName' already gives $Account Full access" }
    elseif ($Apply) { Grant-SmbShareAccess -Name $ShareName -AccountName $Account -AccessRight Full -Force | Out-Null; Write-Ok "Gave $Account Full access to '$ShareName'" }
    else { Write-Plan "Give $Account Full access to '$ShareName'" }

    $everyone = $access | Where-Object { $_.AccountName -match '^(Everyone|Jeder|Todos|Tout le monde)$' }
    if ($everyone) {
        if ($RevokeEveryone -and $Apply) { Revoke-SmbShareAccess -Name $ShareName -AccountName 'Everyone' -Force | Out-Null; Write-Ok "Took Everyone off '$ShareName'" }
        elseif ($RevokeEveryone) { Write-Plan "Take Everyone off '$ShareName' (your account keeps Full access)" }
        else { Write-Warn2 "'$ShareName' also allows Everyone. Re-run with -RevokeEveryone to limit it to $Account." }
    }
}

Write-Step 'Folder permissions'
$acl = Get-Acl -LiteralPath $Path
$user = $Account.Split('\')[-1]
$hasRight = $acl.Access | Where-Object {
    $_.AccessControlType -eq 'Allow' -and ($_.IdentityReference.Value -ieq $Account -or $_.IdentityReference.Value -match "\\$([regex]::Escape($user))$" -or
    $_.IdentityReference.Value -match 'Administrators$|Authenticated Users$|\\Users$|^Everyone$') -and
    ($_.FileSystemRights.ToString() -match 'FullControl|Modify')
}
if ($hasRight) { Write-Ok "NTFS permissions on $Path let $Account read and write" }
else { Write-Warn2 "Couldn't confirm $Account can write to $Path. If edits fail from the laptop, add Modify for $Account under Properties > Security." }

Write-Step 'Firewall (Tailscale only)'
Ensure-TailscaleFirewallRule -Name 'SMB over Tailscale' -Protocol TCP -Ports @('445') -Apply $Apply.IsPresent

Write-Host ''
Write-Host "Test here:        explorer \\localhost\$ShareName"
Write-Host "Test from laptop: \\100.102.16.5\$ShareName  (Tailscale on, sign in as $Account)"
if (-not $Apply) { Write-Host 'Preview only. Re-run with -Apply to make these changes.' -ForegroundColor Cyan }
