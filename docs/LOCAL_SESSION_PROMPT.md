Paste everything below the line into a Claude session running on the Plex PC.

---

Help me rebuild my Plex server on this PC. My old Plex library was a mess: files named wrong, matched to the wrong movies, and some broken. I also have lots of duplicate files across my hard drives. I want the big duplicates removed, but **never** my own photos or videos (phone, camera, GoPro and so on). I have Plex Pass and want remote access working.

A toolkit for this already exists: https://github.com/michaelmccullough2442/PlexOptimize on branch `claude/plex-server-rebuild-cex2fa`. Read its `CLAUDE.md`, `README.md` and `docs/REBUILD_GUIDE.md` first, and follow the guide.

Work through this in order. Check in with me at each **STOP**.

1. **Set up.** Clone the repo (or pull, if it's already here) and check out the branch. Check for Python 3.9+, ffmpeg/ffprobe, git and Plex Media Server. Install whatever is missing (on Windows use `winget`), then run `pip install -e .`. Confirm `plexopt --help` and `ffprobe -version` both work. Run `pytest` to make sure the tools work on this machine.

2. **Look at my drives.** List all my drives with their size, free space, and top-level folders. Find the old Plex server: whether it's running, where its data folder is, and which folders its libraries point to. **STOP:** show me what you found. Ask which drives to scan and where the new `Movies` and `TV Shows` folders should go. Suggest the drive that already holds most of the media, so moves are instant renames.

3. **Keys.** Ask me for my free TMDB API key (walk me through getting one at themoviedb.org/settings/api if I don't have it). Also help me get my Plex token. Put both in environment variables for this session. Don't write them into any file in the repo.

4. **Scan.** Run `plexopt scan` on the drives I picked. It can take a long time on big drives, so run it in the background and give me progress updates. When it's done, run `plexopt report` and summarize it:
   - how many videos there are
   - which are broken or suspect
   - how many personal files are protected

   Spot-check a few files it marked personal and a few it didn't, to make sure my own videos are recognized. If anything of mine was missed, fix the detection in `scanner.py` (err toward protecting files) and rescan.

5. **Identify and plan.** Run `plexopt identify`, then `plexopt plan` with my chosen folders, then `plexopt dupes --min-size 500 --library <my new Plex folder>`. Summarize both CSVs: counts and GB per action, the biggest space savings, and the broken files.

6. **Fix the unknowns with me.** For every `review` row, investigate before asking me. Use ffprobe metadata, the runtime, folder context, nearby files and TMDB searches, and pull a frame with ffmpeg and look at it if that helps. Propose a match for each one with your reasoning. Apply the ones I confirm with `plexopt fix`, then re-run `plan`. Batch these so I'm not answering one at a time.

7. **STOP before changing anything.** Show me the dry runs: `plexopt apply plan.csv` and `plexopt apply dupes.csv`. List every file marked `delete` over 1 GB, and confirm that no personal file appears in any delete or move row. Only run `--execute` after I say yes.

8. **Retire the old Plex server.** Follow step 1 of the guide:
   - back up and rename the old data folder
   - export the registry key before removing it
   - remove the old server from my account

   **STOP** before each destructive step.

9. **New Plex server.** Help me claim the fresh server. Run `plexopt plex-setup` (ask whether I want a Home Videos library for my own videos). Apply the recommended settings from the guide, including hardware transcoding.

10. **Remote access.** Run `plexopt plex-remote --enable` and `plexopt plex-check`. If it isn't working, diagnose it on this PC:
    - my local IP and gateway
    - the router's WAN IP versus my public IP (to check for CGNAT or double NAT)
    - Windows Firewall rules for Plex
    - whether the network is set to Private

    Give me exact router steps for the router brand you detect. Keep going until `plex-check` says remote access is WORKING. Then have me test from my phone on mobile data.

11. **Plex indexing and extras.** Run `plexopt plex-tune` and show me the dry run; apply with `--execute` after I say yes. Once Plex has finished its first scan, run `plexopt plex-index --csv plex-problems.csv` and summarize it. For wrong or unmatched items, show me `plexopt plex-index --rematch`, run it with `--execute` after I say yes, then run `plex-index` again. Walk me through anything that's still wrong in Plex Web (Fix Match). Then set up Tautulli and Kometa (guide section 11). I've already said yes to them and to installing Docker Desktop. My time zone is Hawaii, so run `plexopt plex-companions --tz Pacific/Honolulu`, start them, run Kometa once, and help me through Tautulli's setup wizard.

12. **Finish up.** Run `plexopt plex-refresh`. After I confirm the library looks right, show me what `plexopt purge` would free. Only run it with `--execute` when I say so. Commit any code fixes you made to the branch and push.

Ground rules:
- Never permanently delete anything without my explicit OK for that specific step.
- Never touch my personal photos or videos.
- Explain things in plain language. I'm not super technical.
