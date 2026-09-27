# Rebuilding Plex from scratch

The order matters. You clean the files first and build the new Plex server second, so Plex never re-learns the old wrong matches.

---

## 0. Before you start

- **Unplug nothing and delete nothing yet.** Every step here is reversible until you run `plexopt purge`.
- Make sure each drive has some free space. Moves on the same drive are instant renames and need almost no space. Moves *between* drives copy first, so the target drive needs room for the file.
- Get a free TMDB API key at https://www.themoviedb.org/settings/api (sign up, then choose "Developer"). Either key works: the short *API Key* or the long *Read Access Token*.

## 1. Retire the old Plex server

The old database is where the wrong matches live, so you start fresh rather than repairing it.

1. Open Plex and note anything you want to keep: users you share with, and any watch history you care about. (Watch history is kept by your plex.tv account for matched items. Plex re-applies it once the new server matches the same movie.)
2. Quit Plex Media Server (right-click the tray icon, then **Exit**).
3. Rename the old data folder so Plex starts clean. **Keep it until the new server works.**
   - Windows: `%LOCALAPPDATA%\Plex Media Server` → `Plex Media Server.OLD`
   - macOS: `~/Library/Application Support/Plex Media Server`
   - Linux: `/var/lib/plexmediaserver/Library/Application Support/Plex Media Server`
4. Windows only: the server's identity is stored in the registry at `HKEY_CURRENT_USER\Software\Plex, Inc.\Plex Media Server`. Export it to a .reg file as a backup, then delete that key. The new install then registers as a fresh server.
5. Remove the old server from your account at https://app.plex.tv. Go to **Settings > Authorized Devices**, open the **Servers** filter, and delete the old entry.

## 2. Install the tools

Windows (PowerShell):

```powershell
winget install Python.Python.3.12 Gyan.FFmpeg Plex.PlexMediaServer
# close and reopen PowerShell, then from this repo folder:
pip install -e .
```

macOS: `brew install python ffmpeg` and install Plex from plex.tv. Linux: use your package manager for python3 and ffmpeg.

Check that everything is installed: `plexopt --help` and `ffprobe -version` should both print text.

## 3. Scan every drive

```powershell
plexopt scan D:\ E:\ F:\
```

- The scan detects **broken** files: empty files, junk that isn't video, missing video streams, and truncated downloads. It checks the last one by decoding a few seconds at 5%, 50% and 95% of each file.
- It **protects** your own photos and videos. It recognizes phone and camera filenames (IMG_, VID_, PXL_, DSC, GOPR, DJI, WhatsApp...), camera and phone folders (DCIM, Camera Roll, Pictures...), and GPS or phone-model metadata.
- It is resumable. If you stop it, running it again skips files it has already checked.
- Add `--fast` to skip the decode check. That is quicker, but it misses truncated files.

`plexopt report` lists every broken or suspect file.

## 4. Identify everything

```powershell
$env:TMDB_API_KEY = "your-key"
plexopt identify
```

For every video the tool tries several guesses: the filename, the parent folder, the grandparent folder, and the title stored inside the file. It then checks each guess against TMDB. For movies it also compares the file's real runtime with TMDB's runtime, which catches files whose names point at the wrong movie.

## 5. Build the plan and review it

```powershell
plexopt plan --movies "D:\Plex\Movies" --tv "D:\Plex\TV Shows"
```

This writes `plan.csv`. Open it in Excel; rows are sorted with the ones that need attention first:

| action | meaning |
|---|---|
| `review` | Not confident about this one. Fix it (see below) or leave it. |
| `quarantine` | Broken file. Goes to `X:\_PlexOptimize\Broken\`. |
| `delete` | A lower-quality copy of a title you have in better quality, or a sample clip. Goes to `X:\_PlexOptimize\ToDelete\`. |
| `move` | Gets renamed into the new library. |
| `skip` | Left alone. This covers your personal media and files that are already named correctly. |

To fix a `review` row, find the movie on themoviedb.org. The number in its URL is the ID (for example `themoviedb.org/movie/603-the-matrix` is `603`). Then run:

```powershell
plexopt fix "E:\junk\abc123.avi" --tmdb 603
plexopt fix "E:\stuff\ep2.mkv" --tmdb 1396 --tv --season 1 --episode 2
```

Then run `plexopt plan ...` again. You can also edit a CSV row by hand and save it.

Duplicate copies of the same title keep the **best quality** by default. Add `--keep smallest` to keep the smallest file instead, which saves more space.

**Tip:** keep the library folders on the same drive as most of the files. Then `move` is an instant rename. If your files are spread over several drives, you can give Plex several folders per library (step 8), for example `D:\Plex\Movies` and `E:\Plex\Movies`.

## 6. Clean up duplicates

```powershell
plexopt dupes --min-size 500 --library "D:\Plex"
```

This finds byte-identical copies across **all** drives, for files of 500 MB and up (change `--min-size` to adjust). It keeps one copy of each, preferring a copy inside your library folders over copies in Downloads or backup folders.

**Your own photos and videos are never marked for deletion**, even when duplicated. They show up as `skip` with "PROTECTED" in the notes.

## 7. Apply the changes

```powershell
plexopt apply plan.csv            # dry run: shows what would happen
plexopt apply plan.csv --execute  # does it
plexopt apply dupes.csv --execute
```

- Nothing is ever overwritten.
- Empty leftover release folders (only .nfo/.txt junk) are removed.
- `plexopt undo` puts everything back where it was.
- Test your library for a few days. When you're happy, free the space for real:

```powershell
plexopt purge D:\ E:\ F:\            # shows how much would be freed
plexopt purge D:\ E:\ F:\ --execute  # permanently deletes _PlexOptimize\ToDelete
```

Check `_PlexOptimize\Broken\` yourself and delete it once you're sure. Those files need replacing anyway.

## 8. Set up the new Plex server

1. Start Plex Media Server and open http://127.0.0.1:32400/web. Sign in and claim the server.
2. Get your token (https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/), then:

```powershell
$env:PLEX_TOKEN = "your-token"
plexopt plex-setup --movies "D:\Plex\Movies" --tv "D:\Plex\TV Shows" --home-videos "D:\Home Videos" --music "D:\Music"
```

The `--home-videos` library is optional. It is a place to watch your own videos in Plex without Plex trying to match them to movies.

The `--music` library is optional too, and it's what **Plexamp** plays. You can give it several folders (`--music "D:\Music" "E:\iTunes"`). Plex matches music by the tags inside the files, so if artists or albums come out wrong, fix the tags with the free **MusicBrainz Picard** and rescan.

`plex-setup` skips libraries that already exist, so you can run it again later just to add one, e.g. `plexopt plex-setup --music "D:\Music"`.

`plexopt plex-tune` shows which of the settings below differ from what's recommended; `plexopt plex-tune --execute` applies them. It only touches settings your Plex version has.

Recommended settings (Plex Web > Settings):

- **Library:** turn on *Scan my library automatically* and *Run a partial scan when changes are detected*. Turn off *Empty trash automatically after every scan* until you trust your drives. Otherwise one unplugged drive wipes its metadata.
- **Library > Generate video preview thumbnails:** set to *as a scheduled task* (or *never* to save disk space). The same applies to intro and credit detection, which are Plex Pass features.
- **Transcoder:** turn on *Use hardware acceleration when available* and *Use hardware-accelerated video encoding* (Plex Pass). Set *Transcoder temporary directory* to a fast SSD.
- **Scheduled Tasks:** keep *Optimize database* and *Remove old bundles* on.

## 9. Remote access (Plex Pass)

```powershell
plexopt plex-remote --enable --port 32400
plexopt plex-check
```

`plex-check` reports whether remote access is working and, if not, what to fix. The usual fixes:

1. **Give this PC a fixed local IP.** Set a DHCP reservation in your router's admin page, usually at http://192.168.0.1 or http://192.168.1.1.
2. **Forward the port.** In the router, forward TCP external port `32400` to this PC's IP on port `32400`. If UPnP is on, Plex may do this itself, but a manual forward is more reliable.
3. **Plex settings:** go to **Settings > Remote Access > Show Advanced**, tick *Manually specify public port*, enter `32400`, then click **Apply**. The page should turn green: "Fully accessible outside your network".
4. **Windows Firewall:** allow *Plex Media Server* on both **Private and Public** networks. Also make sure Windows sees your home network as *Private*.
5. **Upload limits:** go to **Settings > Remote Access**. Set *Internet upload speed* to your real upload speed (run a speed test) and *Limit remote stream bitrate* to fit it. Remote viewers then get smooth playback instead of buffering.
6. **Still red?** Two common causes:
   - **Double NAT:** you have your own router behind the ISP's modem/router. Put the ISP box in bridge mode, or forward the port on both devices.
   - **CGNAT:** your router's WAN IP starts with `100.64.`–`100.127.`, or doesn't match what `plex-check` reports. Port forwarding cannot work in that case. Ask your ISP for a public IPv4 address, which is often free on request. Or install **Tailscale** on the server and on your devices, and add the server's Tailscale address under **Settings > Network > Custom server access URLs** as `http://100.x.y.z:32400`.
7. Don't turn on *Treat WAN IP as LAN bandwidth* or disable authentication for remote networks. Neither is needed.

Once `plex-check` says `Remote access is WORKING`, you're done. Test it from your phone over mobile data with Wi-Fi off.

## 10. Check that Plex indexed everything correctly

Wait until the first scan is done (the spinning icon in Plex Web stops), then:

```powershell
plexopt plex-index --csv plex-problems.csv
```

For every library it reports:

- whether Plex is still scanning, and any library folder it can't reach (an unplugged or renamed drive)
- whether *Scan my library automatically* is on
- for each movie and show: **verified** (Plex's match agrees with the `{tmdb-ID}` in the name), **matched WRONG** (Plex picked a different title), **unmatched** (Plex gave up), or **not verifiable** (no `{tmdb-ID}` in the name, e.g. files you added by hand)

Home Videos and other personal libraries are only counted, never checked or changed.

To fix wrong and unmatched items, have Plex re-read the `{tmdb-ID}` tag:

```powershell
plexopt plex-index --rematch            # dry run: lists what it would re-match
plexopt plex-index --rematch --execute
```

If something is still wrong after that, open it in Plex Web, click **...** > **Fix Match**, and search for `tmdb-603` (with your ID).

## 11. Make Plex more useful

### Built in with Plex Pass (turned on by `plex-tune`)

- **Skip Intro / Skip Credits** buttons, detected overnight.
- **Loudness levelling**, so quiet dialogue and loud explosions even out.
- **Sonic analysis for Plexamp.** Plex listens to every track overnight. That powers Plexamp's song, artist and album radios, *Sonic Adventure* (a playlist that drifts from one song to another), and daily mixes. It takes a few nights to get through a big collection.
- **Hardware transcoding**, so remote streams and phones play smoothly.
- **Subtitles:** in any player, choose *Subtitles > Search* to download one from OpenSubtitles. No plugin needed.
- **Downloads:** in the Plex mobile app, download movies to your phone for flights.

Plex removed its old "channel" plugins in 2018. Today, useful add-ons are separate apps that talk to Plex. `plexopt` sets these four up for you:

| app | what you get |
|---|---|
| **Tautulli** | A dashboard at http://localhost:8181 showing who's watching what, play history and stats, plus alerts (email, Discord, phone) when someone starts watching, a stream buffers, or the server goes offline. |
| **Kometa** | Automatic collections in Plex: franchises (every *Marvel*, *Star Wars*, *Harry Potter* film grouped together), IMDb Top 250, Trending, Newly Added, genres, decades and seasonal collections (Halloween, Christmas), and TV networks. Optionally it badges posters with 4K/HDR/Atmos. It only changes Plex's metadata, never your files, and it runs nightly. |
| **Plex Auto Languages** | Switch a show's audio or subtitle track once (say, Japanese audio with English subtitles) and every other episode of that show switches too. No setup. |
| **PlexTraktSync** | Backs up your watch history and ratings to a free Trakt.tv account and updates it live as you watch. If you ever rebuild Plex again, nothing is lost. Needs a one-time login (step 5 of the README it writes). |

```powershell
winget install Docker.DockerDesktop     # then start Docker Desktop once
plexopt plex-companions --tz "Pacific/Honolulu"     # your time zone
cd ~\PlexCompanions
docker compose up -d
docker compose run --rm kometa --run    # build the collections now instead of tonight
```

`plex-companions` writes its files to `~\PlexCompanions`, outside this repo, because they contain your Plex token and TMDB key (in `.env` and `kometa\config.yml`). It never gives Kometa your Home Videos library. Add `--overlays` to get the poster badges. Then open http://localhost:8181 and follow Tautulli's wizard, using Plex host `host.docker.internal` and port `32400`. `~\PlexCompanions\README.txt` has the details, including the Trakt login.

### On your phone

- **Plexamp** (free app; the best features need Plex Pass): music, with downloads for offline listening.
- **Plex Dash** (free with Plex Pass): a remote for the server. See who's watching, start a scan, and check the server's health.
- **Tautulli alerts:** in Tautulli, go to **Settings > Notification Agents** to get a push or Discord message when someone starts watching or the server goes offline.
- **Downloads** in the Plex app save movies and shows to your phone for offline viewing.

**Optional, later:** *Overseerr* adds a "request a movie" page for people you share with, and *Tdarr* converts old AVI/WMV files to MP4 so they stop transcoding. Add them once the basics have been working for a while.

## 12. Keeping it clean

When you add new downloads, run the same pipeline on just that folder:

```powershell
plexopt scan D:\Downloads
plexopt identify
plexopt plan --movies "D:\Plex\Movies" --tv "D:\Plex\TV Shows"
plexopt apply plan.csv --execute
plexopt plex-refresh
plexopt plex-index
```
