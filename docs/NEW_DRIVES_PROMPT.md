Paste everything below the line into a Claude session running on the Plex PC. Plug in the old backup drives first.

---

I've plugged two old backup hard drives into this PC. I want everything worth keeping on them added to my collection on my big USB Seagate (F:), without duplicates:
- movies, TV, videos
- music and audiobooks
- books and PDFs
- PC games (Steam, and standalone games that run without an installer)

The PlexOptimize toolkit is in `C:\PlexOptimize` (https://github.com/michaelmccullough2442/PlexOptimize). Pull branch `claude/wizardly-newton-ni7wh8` and run `pip install -e .`. Then read `CLAUDE.md`, `README.md` and `docs/REBUILD_GUIDE.md` before you start. Its rules apply: dry run first, nothing deleted without my OK, and **never** touch my own photos, videos or recordings except to copy them.

**What's already on F:**
- `F:\Plex\Movies`, `F:\Plex\TV Shows`, `F:\Plex\Learning`, `F:\Plex\Game Cinematics`, `F:\Plex\Music` and `F:\Plex\Remixes`, all already in Plex.
- The existing inventory (`library.db`) and `C:\PlexOptimize\reports\missing_from_old_server.csv`, which lists about 7,800 files from my old Plex server that were on drives I didn't have connected. These backup drives may hold some of them.

**The main rule: these backup drives are read-only.** Copy from them; never move, rename or delete anything on them.
- `plexopt apply` moves by default. Use `--mode copy` for everything from these drives.
- Even in copy mode, `delete` and `quarantine` rows move files into a staging folder on their own drive. Before every `apply`, filter the CSV to just the rows you mean to apply. Never apply a delete or quarantine row whose source is on a backup drive.
- After copying, check each file on F: matches its source by size, and by hash for anything under 1 GB.

Work through this in order. Check in with me at each **STOP**.

1. **Find the drives.**
   - List every drive: letter, label, size, free space and top-level folders.
   - Work out which two are the new backup drives, and confirm F: is the Seagate.
   - Check whether either drive is one of the old letters from my missing-files list (L, F, Y or G on the old PC).

   **STOP:** show me, and confirm F: has room for what you expect to copy.

2. **Survey everything, read-only.**
   - Run `plexopt scan <backup drives>` (in the background, with progress updates), then `plexopt audit <backup drives>`.
   - For anything the toolkit doesn't handle, list it yourself by type, with counts and GB:
     - books (`.pdf`, `.epub`, `.mobi`, `.azw3`, `.cbz`, `.cbr`)
     - audiobooks (`.m4b`, `.aax`, and folders of numbered mp3 chapters)
     - Steam libraries (`steamapps` folders with `appmanifest_*.acf`)
     - standalone or portable games: folders with a game `.exe` and its data
     - game installers and disc images
   - Keep my personal and work files separate: thesis, work, school, scans, receipts, tax documents, SWAT/ArcGIS/MATLAB. Those aren't "books". List them for me; don't file them.

   **STOP:** give me a summary table of type, count, GB, how much is new, and how much is already on F:.

3. **Find duplicates against what I already have.** A file counts as already-have if the same file is on F: (same size plus a matching hash), or if it's the same title in the Plex library.
   - **Video:** `plexopt identify`, then `plexopt plan --movies F:\Plex\Movies --tv "F:\Plex\TV Shows"`. If the backup has a better copy of something already in Plex, show it to me as an upgrade. Don't swap it automatically.
   - **Music:** `plexopt music --music F:\Plex\Music`.
   - **Photos and home videos:** `plexopt photos --photos <my Pictures folder; ask me>`.
   - **Books, audiobooks and games:** write your own read-only comparison (size first, then hash) and save it as a CSV in `C:\PlexOptimize\reports`.

   **STOP:** show me what's new and what's already there.

4. **Dry run, then copy.** Proposed layout on F::

   | type | goes to |
   |---|---|
   | movies, TV | the existing Plex folders |
   | music | `F:\Plex\Music` |
   | audiobooks | `F:\Plex\Audiobooks\<Author>\<Book>\` |
   | books and PDFs | `F:\Books\<Author> - <Title>.<ext>` |
   | game cinematics | `F:\Plex\Game Cinematics` |
   | Steam games | `F:\SteamLibrary` |
   | standalone games | `F:\Games\<Game name>\` |
   | game installers and ISOs | `F:\Games\_Installers` |

   - Show me the dry run, with totals per folder and every item over 5 GB.
   - **STOP**, then copy only after I say yes.
   - For Steam, copy `steamapps\common\<game>` together with its matching `appmanifest_*.acf` into `F:\SteamLibrary\steamapps`. Then walk me through Steam → Settings → Storage → Add Drive so Steam picks them up without re-downloading.

5. **Plex.**
   - **STOP** before changing any Plex setting.
   - Then offer to add an **Audiobooks** library: a Music-type library on `F:\Plex\Audiobooks`, with the settings Plex recommends for audiobooks so progress is remembered.
   - Run `plexopt plex-refresh` and confirm the new items show up.
   - Plex can't show books or PDFs. Tell me my options (e.g. Kavita or Calibre-Web), but don't install anything without asking.

6. **Wrap up.** Give me one short list:
   - what was copied, per type, with GB
   - what was skipped as already on F:
   - anything you couldn't identify
   - anything that looked broken or incomplete

   Leave the backup drives exactly as they were. If you think duplicates should be cleaned off them, ask me first and treat it as a separate job. Commit any toolkit fixes to the branch and push.

Ground rules:
- Never delete anything without my OK for that specific step, and never anything on the backup drives.
- Never touch my personal photos, videos, recordings or work/thesis files, except to copy them where I say.
- Don't run two writing `plexopt` commands at once.
- Explain things in plain language. I'm not super technical.
