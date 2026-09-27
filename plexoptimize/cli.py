import argparse
import os
import sys
from pathlib import Path

from . import apply, dupes, planner, scanner
from .db import Inventory


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plexopt", description="Rebuild a clean Plex library from messy drives.")
    ap.add_argument("--db", default="library.db", help="inventory database (default: library.db)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="scan drives: find media, check health, spot personal media")
    s.add_argument("roots", nargs="+", help=r"drives/folders to scan, e.g. D:\ E:\ F:\Media")
    s.add_argument("--exclude", nargs="*", default=[], help="folders to skip")
    s.add_argument("--fast", action="store_true", help="skip the spot-decode check (faster, misses truncated files)")
    s.add_argument("--rescan", action="store_true", help="re-probe files even if unchanged")

    s = sub.add_parser("identify", help="look up every video on TMDB")
    s.add_argument("--tmdb-key", default=os.environ.get("TMDB_API_KEY"))
    s.add_argument("--all", action="store_true", help="re-identify files that already have a match")

    s = sub.add_parser("fix", help="manually tell the tool what a file is")
    s.add_argument("path")
    s.add_argument("--tmdb", type=int, required=True, help="TMDB id (the number in the themoviedb.org URL)")
    s.add_argument("--tv", action="store_true", help="it's a TV episode")
    s.add_argument("--season", type=int)
    s.add_argument("--episode", type=int)
    s.add_argument("--tmdb-key", default=os.environ.get("TMDB_API_KEY"))

    s = sub.add_parser("plan", help="write plan.csv: how every file gets renamed/moved")
    s.add_argument("--movies", required=True, help=r"new Movies folder, e.g. D:\Plex\Movies")
    s.add_argument("--tv", required=True, help=r"new TV folder, e.g. D:\Plex\TV Shows")
    s.add_argument("--min-confidence", type=int, default=75)
    s.add_argument("--keep", choices=["best", "smallest"], default="best",
                   help="when you have several copies of a title, keep the best quality or the smallest file")
    s.add_argument("-o", "--out", default="plan.csv")

    s = sub.add_parser("dupes", help="find byte-identical duplicate files across drives -> dupes.csv")
    s.add_argument("--min-size", type=float, default=100, help="only files at least this many MB (default 100)")
    s.add_argument("--full", action="store_true", help="confirm with a full-file hash (slow, paranoid)")
    s.add_argument("--library", nargs="*", default=[], help="prefer keeping copies inside these folders")
    s.add_argument("-o", "--out", default="dupes.csv")

    s = sub.add_parser("report", help="list broken, personal and unidentified files")

    s = sub.add_parser("apply", help="carry out a plan/dupes CSV (dry run unless --execute)")
    s.add_argument("csv")
    s.add_argument("--execute", action="store_true")
    s.add_argument("--mode", choices=["move", "copy", "hardlink"], default="move")

    sub.add_parser("undo", help="reverse everything done by apply --execute")

    s = sub.add_parser("purge", help="permanently empty _PlexOptimize/ToDelete on the given drives")
    s.add_argument("roots", nargs="+")
    s.add_argument("--execute", action="store_true")

    for name, text in [("plex-check", "check Plex server, Plex Pass, and remote access"),
                       ("plex-setup", "create Movies / TV / Home Videos libraries"),
                       ("plex-remote", "turn remote access on and pin the port"),
                       ("plex-refresh", "rescan all libraries and clean up old metadata"),
                       ("plex-index", "check every library is indexed and matched to the right title"),
                       ("plex-tune", "apply recommended scan/transcode/Plex Pass settings (dry run unless --execute)"),
                       ("plex-companions", "generate Tautulli + Kometa (auto collections) setup")]:
        s = sub.add_parser(name, help=text)
        s.add_argument("--url", default=os.environ.get("PLEX_URL", "http://127.0.0.1:32400"))
        s.add_argument("--token", default=os.environ.get("PLEX_TOKEN"))
        if name == "plex-setup":
            s.add_argument("--movies")
            s.add_argument("--tv")
            s.add_argument("--home-videos", help="optional folder for your own videos")
            s.add_argument("--music", nargs="*", default=[],
                           help="optional music folder(s) -> Music library for Plexamp")
        if name == "plex-remote":
            s.add_argument("--enable", action="store_true")
            s.add_argument("--port", type=int, default=32400)
        if name == "plex-index":
            s.add_argument("--csv", help="also write the problem items to this CSV")
            s.add_argument("--rematch", action="store_true",
                           help="re-match wrong/unmatched items from their {tmdb-ID} tag")
            s.add_argument("--execute", action="store_true")
        if name == "plex-tune":
            s.add_argument("--execute", action="store_true")
        if name == "plex-companions":
            s.add_argument("--out", default=str(Path.home() / "PlexCompanions"),
                           help="where to write docker-compose.yml etc. (default: ~/PlexCompanions)")
            s.add_argument("--tmdb-key", default=os.environ.get("TMDB_API_KEY"))
            s.add_argument("--tz", default=os.environ.get("TZ", "Etc/UTC"),
                           help="your time zone, e.g. America/Chicago")
            s.add_argument("--overlays", action="store_true", help="badge posters with 4K/HDR/audio")
            s.add_argument("--tdarr", action="store_true", help="convert old AVI/WMV to MP4 overnight")
            s.add_argument("--overseerr", action="store_true", help="let people request movies/shows")
            s.add_argument("--force", action="store_true", help="overwrite an existing config")

    a = ap.parse_args(argv)
    inv = Inventory(a.db)

    if a.cmd == "scan":
        scanner.scan(inv, [str(Path(r).resolve()) for r in a.roots], a.exclude,
                     deep=not a.fast, rescan=a.rescan)
        _report(inv)

    elif a.cmd == "identify":
        from .tmdb import TMDB
        if not a.tmdb_key:
            sys.exit("Need a free TMDB key: --tmdb-key KEY or set TMDB_API_KEY (themoviedb.org/settings/api)")
        planner.identify(inv, TMDB(a.tmdb_key, inv), only_missing=not a.all)

    elif a.cmd == "fix":
        from .tmdb import TMDB
        if not a.tmdb_key:
            sys.exit("Need --tmdb-key or TMDB_API_KEY")
        t = TMDB(a.tmdb_key, inv)
        info = t.show(a.tmdb) if a.tv else t.movie(a.tmdb)
        if not info:
            sys.exit(f"TMDB id {a.tmdb} not found")
        date = info.get("first_air_date") if a.tv else info.get("release_date")
        o = {"type": "tv" if a.tv else "movie", "tmdb_id": a.tmdb,
             "title": info.get("name") if a.tv else info.get("title"),
             "year": int(date[:4]) if date else None, "confidence": 100}
        if a.tv:
            if a.season is None or a.episode is None:
                sys.exit("TV fixes need --season and --episode")
            o.update(season=a.season, episode=a.episode,
                     episode_title=t.episode_title(a.tmdb, a.season, a.episode))
        path = str(Path(a.path).resolve())
        if not inv.get(path):
            sys.exit("That file isn't in the inventory - run scan first.")
        inv.upsert(path, override=o)
        inv.commit()
        print(f"Set: {path}\n  -> {o['title']} ({o['year']})" +
              (f" S{a.season:02d}E{a.episode:02d}" if a.tv else ""))

    elif a.cmd == "plan":
        rows = planner.build(inv, a.movies, a.tv, a.min_confidence, a.keep)
        planner.write_csv(rows, a.out)
        print(f"Wrote {a.out}\n{planner.summary(rows)}")
        print("\nOpen it in Excel. Fix 'review' rows (edit destination + set action to move, "
              "or use `plexopt fix`), then: plexopt apply", a.out)

    elif a.cmd == "dupes":
        groups = dupes.find_exact(inv, a.min_size, a.full, a.library)
        rows = dupes.exact_rows(groups)
        planner.write_csv(rows, a.out)
        print(f"{len(groups)} duplicate groups. Wrote {a.out}\n{planner.summary(rows)}")

    elif a.cmd == "report":
        _report(inv, full=True)

    elif a.cmd == "apply":
        apply.run(planner.read_csv(a.csv), a.execute, a.mode)

    elif a.cmd == "undo":
        apply.undo()

    elif a.cmd == "purge":
        apply.purge(a.roots, execute=a.execute)

    elif a.cmd.startswith("plex-"):
        from .plex import Plex, check
        p = Plex(a.url, a.token)
        if a.cmd == "plex-check":
            check(p)
        elif a.cmd == "plex-setup":
            existing = {sec["title"] for sec in p.sections()}
            for title, kind, locs in [("Movies", "movie", [a.movies] if a.movies else []),
                                      ("TV Shows", "show", [a.tv] if a.tv else []),
                                      ("Home Videos", "homevideo", [a.home_videos] if a.home_videos else []),
                                      ("Music", "music", a.music)]:
                if not locs:
                    continue
                if title in existing:
                    print(f"[keep] {title} library already exists")
                else:
                    p.create_section(title, kind, locs)
                    print(f"[new] {title}: {', '.join(locs)} - Plex is scanning it now")
        elif a.cmd == "plex-remote":
            if a.enable:
                p.set_pref(ManualPortMappingMode=1, ManualPortMappingPort=a.port)
                p.set_pref(PublishServerOnPlexOnlineKey=1)
                print(f"Remote access enabled on public port {a.port}. Forward that port on your router.")
            check(p)
        elif a.cmd == "plex-refresh":
            p.refresh()
            p.cleanup()
            print("Rescan started; emptied trash, cleaned bundles, optimized database.")
        elif a.cmd == "plex-index":
            from .plex import index_report, rematch
            if not a.token:
                sys.exit("Need --token or PLEX_TOKEN")
            problems = index_report(p)
            if a.csv:
                import csv
                with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.DictWriter(f, fieldnames=["library", "status", "title", "year", "note",
                                                      "path", "rating_key"])
                    w.writeheader()
                    w.writerows(problems)
                print(f"Wrote {a.csv}")
            if a.rematch:
                print()
                rematch(p, problems, execute=a.execute)
        elif a.cmd == "plex-tune":
            from .plex import tune
            if not a.token:
                sys.exit("Need --token or PLEX_TOKEN")
            tune(p, execute=a.execute)
        elif a.cmd == "plex-companions":
            from . import companions
            if not (a.token and a.tmdb_key):
                sys.exit("Need your Plex token (PLEX_TOKEN) and TMDB key (TMDB_API_KEY)")
            companions.write(a.out, p.sections(), a.token, a.tmdb_key, tz=a.tz,
                             overlays=a.overlays, tdarr=a.tdarr, overseerr=a.overseerr, force=a.force)
            print(f"\nNext: read {Path(a.out, 'README.txt')} (install Docker, then `docker compose up -d`)")


def _report(inv, full=False):
    vids = inv.all("video")
    by = {}
    for r in vids:
        by.setdefault(r["health"], []).append(r)
    personal = [r for r in inv.all() if r["personal"]]
    print(f"\nVideos: {len(vids)}  ok: {len(by.get('ok', []))}  suspect: {len(by.get('suspect', []))}  "
          f"broken: {len(by.get('broken', []))}   personal photos/videos (protected): {len(personal)}")
    if full:
        for h in ("broken", "suspect"):
            for r in by.get(h, []):
                print(f"  [{h}] {r['path']}  -- {r['health_note']}")
        unmatched = [r for r in vids if r["match"] is not None and not r["match"].get("tmdb_id")]
        for r in unmatched:
            print(f"  [unidentified] {r['path']}")


if __name__ == "__main__":
    main()
