# Windows setup scripts (home PC)

PowerShell scripts for the remote-access setup: Plex on the I: Seagate drive, Sunshine for
Moonlight game streaming, RetroArch, and an SMB share for ROMs and emulator configs, all reached
from the laptop over Tailscale.

Every script follows the same rules:

- **Preview first.** Without `-Apply` a script only prints what it would change.
- **Nothing is deleted.** Config files are copied to `<name>.bak-<timestamp>` before they change.
- **The thesis drive is off limits.** Any path on `E:\MAIN` (drive E:, or whatever letter the
  volume labelled `MAIN` gets) is refused, and nothing on it is added to Plex.
- **Safe to re-run.** A second run finds everything already set and changes nothing.

Open PowerShell with **Run as administrator**, then:

```powershell
cd <repo>\scripts\windows
Set-ExecutionPolicy -Scope Process Bypass    # only for this window

.\Set-PlexLibraryPaths.ps1                                  # preview
.\Set-PlexLibraryPaths.ps1 -Apply -ConfigureTailscale       # add I: folders, scan, Tailscale settings
#   ...check the libraries in Plex, then:
.\Set-PlexLibraryPaths.ps1 -Apply -RemoveOldPaths           # drop D:/F:/G:/H: folders from the libraries

.\Install-Sunshine.ps1 -Apply
.\Install-RetroArch.ps1 -Apply
.\New-EmulatorShare.ps1 -Apply

.\Test-RemoteReadiness.ps1                  # read-only check, on this PC
```

On the laptop, copy this folder over (or open it from the share) and run
`.\Test-RemoteReadiness.ps1 -FromLaptop`.

| script | what it does |
|---|---|
| `Set-PlexLibraryPaths.ps1` | Adds `I:\Plex\...` folders to Movies, TV Shows, Music, Remixes, Game Cinema and Learning through Plex's local API, then scans. `-RemoveOldPaths` takes old D:/F:/G:/H: folders out of a library only once its I: folder is in it (files stay on disk). `-CreateMissing` creates a library that doesn't exist yet. `-ConfigureTailscale` adds `http://<tailscale-ip>:32400` as a custom server URL and `100.64.0.0/10` to LAN networks so the laptop gets direct, unthrottled streams and downloads. |
| `Install-Sunshine.ps1` | Installs Sunshine (winget), sets `encoder = nvenc`, `nvenc_preset = 1` and `max_bitrate = 4000`, adds Tailscale-only firewall rules, restarts the service. 720p / 30 FPS are set in Moonlight on the laptop. |
| `Install-RetroArch.ps1` | Installs RetroArch (winget), creates `I:\Games\Emulators\RetroArch\roms` if missing, and points Load Content there. |
| `New-EmulatorShare.ps1` | Shares `I:\Games\Emulators` as `\\<pc>\Emulators` to your own account only (not Everyone) and opens SMB to Tailscale addresses only. `-RevokeEveryone` takes an existing Everyone entry off. |
| `Test-RemoteReadiness.ps1` | Changes nothing. Checks Tailscale, Plex libraries and settings, Sunshine, the share, firewall rules and sleep settings; `-FromLaptop` checks the ports and connection type from the laptop. |

The share is `\\100.102.16.5\Emulators` (one share for the `Emulators` folder), not
`\\100.102.16.5\Games\Emulators`.

Troubleshooting from the road: [docs/TIJUANA_CHECKLIST.md](../../docs/TIJUANA_CHECKLIST.md).
