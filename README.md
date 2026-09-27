# PlexOptimize

Rebuild a clean Plex server from messy drives.

- **Finds every video** on every drive and checks whether it actually plays. It catches empty files, junk files, and truncated downloads.
- **Identifies badly named files** from the filename, folder names, embedded title and real runtime, then checks them against TMDB.
- **Renames into Plex's exact format** with `{tmdb-ID}` tags, so Plex can't mis-match them again.
- **Consolidates music:** keeps one copy of every song, preferring lossless and then the higher bitrate, and puts it in one `Artist/Album/NN - Title` folder tree. Identical copies are removed. Live versions and remixes are kept.
- **Organizes your photos** (and phone/camera videos) by date taken into `Pictures\2019\2019-07\`. It removes identical copies and shrunken copies (WhatsApp/Facebook re-saves), and keeps burst shots, edits and RAW+JPEG pairs.
- **Removes duplicates**, both identical copies across drives and lower-quality copies of the same movie. It **never touches your own photos or videos**.
- **Sets up Plex:** creates the libraries, turns on remote access, and diagnoses port forwarding, CGNAT and firewall problems.
- **Safe by default:** every command is a dry run until you add `--execute`. Deletions go to a `_PlexOptimize\ToDelete` folder first, and `plexopt undo` reverses everything.

## Quick start (Windows)

```powershell
winget install Python.Python.3.12 Gyan.FFmpeg Plex.PlexMediaServer
pip install -e .

plexopt scan D:\ E:\ F:\
$env:TMDB_API_KEY = "..."      # free: themoviedb.org/settings/api
plexopt identify
plexopt plan --movies "D:\Plex\Movies" --tv "D:\Plex\TV Shows"   # -> plan.csv, review in Excel
plexopt dupes --min-size 500 --library "D:\Plex"                  # -> dupes.csv
plexopt apply plan.csv --execute
plexopt apply dupes.csv --execute
plexopt music --music "D:\Plex\Music"                             # -> music.csv
plexopt apply music.csv --execute
plexopt photos --photos "D:\Pictures"                             # -> photos.csv
plexopt apply photos.csv --execute

$env:PLEX_TOKEN = "..."
plexopt plex-setup --movies "D:\Plex\Movies" --tv "D:\Plex\TV Shows"
plexopt plex-remote --enable
plexopt plex-check
```

Read **[docs/REBUILD_GUIDE.md](docs/REBUILD_GUIDE.md)** for the full walkthrough. It covers retiring the old server, settings, remote access troubleshooting and ongoing upkeep.

## Commands

| command | what it does |
|---|---|
| `scan DRIVES...` | inventory + health check + personal-media detection (resumable) |
| `report` | list broken, suspect and unidentified files |
| `identify` | match videos to TMDB |
| `fix PATH --tmdb ID [--tv --season N --episode N]` | manually identify one file |
| `plan --movies DIR --tv DIR` | write `plan.csv` |
| `dupes [--min-size MB]` | write `dupes.csv` of identical copies |
| `music --music DIR [--keep best\|smallest]` | one copy of every song, consolidated into one folder -> `music.csv` |
| `photos --photos DIR [--no-videos]` | photos + phone videos into `YYYY/YYYY-MM` folders, duplicate pictures removed -> `photos.csv` |
| `apply CSV [--execute] [--mode move\|copy\|hardlink]` | carry out a plan |
| `undo` | reverse all applied changes |
| `purge DRIVES... [--execute]` | permanently empty `_PlexOptimize\ToDelete` |
| `plex-check` / `plex-setup` / `plex-remote` / `plex-refresh` | manage the Plex server |

## Tests

```
pip install pytest && pytest
```

These tests need ffmpeg. TMDB is faked, so they don't use the network.
