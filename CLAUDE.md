# PlexOptimize

Python CLI (`plexopt`) that rebuilds the owner's Plex server from messy drives. Workflow and user-facing
docs: README.md and docs/REBUILD_GUIDE.md.

Owner's goals: fix obscure, mis-named and broken files from the old Plex server; delete large duplicates
but NEVER their own photos/videos; working remote access (they have Plex Pass).

When run locally on the owner's PC:
- Everything destructive is a dry run until `--execute`; deletes stage in `<drive>/_PlexOptimize/ToDelete`
  and are only removed by `plexopt purge --execute`. Keep it that way. Confirm with the owner before any
  `--execute`, `purge`, or Plex settings change.
- Personal-media detection lives in `plexoptimize/scanner.py` (`looks_personal`). If you tune it, err
  toward protecting files.
- Tests: `pytest` (needs ffmpeg; TMDB is faked).
