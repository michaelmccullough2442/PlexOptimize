"""Talk to your Plex Media Server: check remote access, create libraries, rescan, clean up.

Needs your X-Plex-Token. How to find it:
https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/
"""
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class Plex:
    def __init__(self, url="http://127.0.0.1:32400", token=None):
        self.url = url.rstrip("/")
        self.token = token

    def _req(self, path, method="GET", **params):
        if self.token:
            params["X-Plex-Token"] = self.token
        url = f"{self.url}{path}"
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method=method, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        return json.loads(body) if body.strip().startswith(b"{") else {}

    def identity(self):
        return self._req("/identity").get("MediaContainer", {})

    def account(self):
        return self._req("/myplex/account").get("MyPlex", {})

    def prefs(self):
        items = self._req("/:/prefs").get("MediaContainer", {}).get("Setting", [])
        return {s["id"]: s.get("value") for s in items}

    def set_pref(self, **kv):
        self._req("/:/prefs", method="PUT", **kv)

    def sections(self):
        return self._req("/library/sections").get("MediaContainer", {}).get("Directory", [])

    def create_section(self, name, kind, locations):
        agent, scanner = {
            "movie": ("tv.plex.agents.movie", "Plex Movie"),
            "show": ("tv.plex.agents.series", "Plex TV Series"),
            "homevideo": ("com.plexapp.agents.none", "Plex Video Files Scanner"),
            "photo": ("com.plexapp.agents.none", "Plex Photo Scanner"),
        }[kind]
        params = [("name", name), ("type", "movie" if kind == "homevideo" else kind),
                  ("agent", agent), ("scanner", scanner), ("language", "en-US")]
        params += [("location", loc) for loc in locations]
        if self.token:
            params.append(("X-Plex-Token", self.token))
        url = f"{self.url}/library/sections?{urllib.parse.urlencode(params)}"
        urllib.request.urlopen(urllib.request.Request(url, method="POST"), timeout=60).read()

    def items(self, section_id):
        return self._req(f"/library/sections/{section_id}/all", includeGuids=1) \
            .get("MediaContainer", {}).get("Metadata", [])

    def count(self, section_id):
        mc = self._req(f"/library/sections/{section_id}/all", **{
            "X-Plex-Container-Start": 0, "X-Plex-Container-Size": 0}).get("MediaContainer", {})
        return mc.get("totalSize", mc.get("size", 0))

    def metadata(self, rating_key):
        md = self._req(f"/library/metadata/{rating_key}").get("MediaContainer", {}).get("Metadata", [])
        return md[0] if md else {}

    def activities(self):
        return self._req("/activities").get("MediaContainer", {}).get("Activity", [])

    def refresh(self, section_id=None):
        if section_id:
            self._req(f"/library/sections/{section_id}/refresh")
        else:
            for s in self.sections():
                self._req(f"/library/sections/{s['key']}/refresh")

    def cleanup(self):
        for s in self.sections():
            self._req(f"/library/sections/{s['key']}/emptyTrash", method="PUT")
        self._req("/library/clean/bundles", method="PUT")
        self._req("/library/optimize", method="PUT")


def check(plex, log=print):
    try:
        ident = plex.identity()
    except (urllib.error.URLError, OSError) as e:
        log(f"[X] Can't reach Plex at {plex.url}: {e}\n    Is Plex Media Server running on this PC?")
        return
    log(f"[ok] Plex Media Server {ident.get('version')} is running at {plex.url}")
    if not plex.token:
        log("[!] No --token given, so remote access can't be checked. See README for how to get one.")
        return
    try:
        acct = plex.account()
        prefs = plex.prefs()
    except urllib.error.HTTPError as e:
        log(f"[X] Plex rejected the token ({e.code}). Grab a fresh X-Plex-Token.")
        return

    log(f"[{'ok' if acct.get('signInState') == 'ok' else 'X'}] Signed in to Plex as "
        f"{acct.get('username', '?')}")
    log(f"[{'ok' if acct.get('subscriptionActive') else '!'}] Plex Pass active: "
        f"{bool(acct.get('subscriptionActive'))}")

    state = acct.get("mappingState")
    public_ip = acct.get("publicAddress")
    port = acct.get("publicPort") or prefs.get("ManualPortMappingPort") or 32400
    if state == "mapped":
        log(f"[ok] Remote access is WORKING: reachable from the internet at {public_ip}:{port}")
    else:
        log(f"[X] Remote access is NOT working (state: {state}, error: {acct.get('mappingError') or 'none'})")
        log(f"    Public IP Plex sees: {public_ip}")
        if prefs.get("PublishServerOnPlexOnlineKey") in (False, "false", "0", 0):
            log("    -> Remote access is turned OFF. Fix: `plexopt plex-remote --enable --token ...`")
        log("    Fix checklist (details in docs/REBUILD_GUIDE.md, 'Remote access'):")
        log("     1. Give this PC a reserved/static IP in your router (DHCP reservation).")
        log(f"     2. Router: forward TCP port {port} -> this PC's IP, port 32400.")
        log("     3. Plex > Settings > Remote Access: tick 'Manually specify public port' and enter "
            f"{port}, then Apply.")
        log("     4. Windows Firewall: allow 'Plex Media Server' on Private AND Public networks.")
        log("     5. If your router's WAN IP differs from the public IP above, or starts with 100.64-100.127,"
            " your ISP uses CGNAT: ask them for a public IP, or use Tailscale (see guide).")
        try:
            if public_ip and ipaddress.ip_address(public_ip) in ipaddress.ip_network("100.64.0.0/10"):
                log("    !! Your public address is in the CGNAT range - port forwarding will not work.")
        except ValueError:
            pass

    hw = prefs.get("HardwareAcceleratedCodecs")
    log(f"[{'ok' if hw in (True, 'true', '1', 1) else '!'}] Hardware transcoding (Plex Pass): "
        f"{'on' if hw in (True, 'true', '1', 1) else 'OFF - turn on in Settings > Transcoder'}")
    upload = prefs.get("WanPerStreamMaxUploadRate") or prefs.get("WanTotalMaxUploadRate")
    log(f"[i] Remote stream upload limit: {upload or 'not set'} kbps "
        "(set to ~80% of your internet upload speed)")

    secs = plex.sections()
    log(f"[i] Libraries: " + (", ".join(f"{s['title']} ({s['type']})" for s in secs) or "none yet"))


# ---------------------------------------------------------------------------
# Is Plex indexing correctly?

TMDB_TAG = re.compile(r"\{tmdb-(\d+)\}")


def _truthy(v):
    return v in (True, "true", "1", 1)


def _is_local(plex):
    return urllib.parse.urlparse(plex.url).hostname in ("127.0.0.1", "localhost", "::1")


def _item_path(plex, sec, item):
    """The path that carries the {tmdb-ID} tag: the movie file, or the show folder."""
    if sec["type"] == "movie":
        for m in item.get("Media", []):
            for p in m.get("Part", []):
                if p.get("file"):
                    return p["file"]
        return ""
    meta = plex.metadata(item["ratingKey"])
    locs = meta.get("Location", [])
    return locs[0].get("path", "") if locs else ""


def classify(plex, sec, item):
    """-> (status, path, note). status: ok | unmatched | mismatch | untagged."""
    path = _item_path(plex, sec, item)
    guid = item.get("guid", "")
    tmdb_ids = [g["id"].split("://", 1)[1] for g in item.get("Guid", []) if g.get("id", "").startswith("tmdb://")]
    tag = TMDB_TAG.findall(path)
    want = tag[-1] if tag else None
    if guid.startswith(("local://", "com.plexapp.agents.none")) or not guid:
        return "unmatched", path, f"Plex couldn't match this (file says tmdb-{want})" if want else "no match"
    if want and tmdb_ids and want not in tmdb_ids:
        return "mismatch", path, f"file says tmdb-{want}, Plex matched tmdb-{tmdb_ids[0]}"
    if not want:
        return "untagged", path, "no {tmdb-ID} in the name, so the match can't be verified"
    return "ok", path, ""


def index_report(plex, log=print):
    """Check every library: still scanning? folders reachable? items matched to the right title?

    Returns a list of problem rows (dicts) for movie/show libraries.
    """
    problems = []
    acts = plex.activities()
    for a in acts:
        log(f"[..] Plex is busy: {a.get('title')} {a.get('subtitle') or ''} ({int(a.get('progress') or 0)}%)")

    prefs = plex.prefs()
    if not _truthy(prefs.get("FSEventLibraryUpdatesEnabled")):
        log("[!] 'Scan my library automatically' is OFF - new files won't show up on their own. "
            "Fix: plexopt plex-tune")
    if _truthy(prefs.get("autoEmptyTrash")):
        log("[!] 'Empty trash automatically after every scan' is ON - an unplugged drive will wipe its "
            "metadata. Fix: plexopt plex-tune")

    secs = plex.sections()
    if not secs:
        log("[X] No libraries yet. Run: plexopt plex-setup --movies ... --tv ...")
    for sec in secs:
        name, kind = sec["title"], sec["type"]
        state = "scanning now" if _truthy(sec.get("refreshing")) else "idle"
        log(f"\n== {name} ({kind}, {state})")
        for loc in sec.get("Location", []):
            p = loc.get("path", "")
            if _is_local(plex) and p and not Path(p).exists():
                log(f"  [X] Folder not found: {p}  (drive unplugged or renamed? Plex will show items as unavailable)")
            else:
                log(f"  folder: {p}")
        agent = sec.get("agent", "")
        if kind in ("movie", "show") and agent.startswith("com.plexapp.agents.") and agent != "com.plexapp.agents.none":
            log(f"  [!] Uses the old '{agent}' agent. Edit the library > Advanced and switch to the new "
                "Plex Movie / Plex TV Series agent for reliable {tmdb-ID} matching.")
        if kind not in ("movie", "show") or agent == "com.plexapp.agents.none":
            log(f"  [i] {plex.count(sec['key'])} items (personal/other library - not checked against TMDB)")
            continue

        counts = {"ok": 0, "unmatched": 0, "mismatch": 0, "untagged": 0}
        for item in plex.items(sec["key"]):
            status, path, note = classify(plex, sec, item)
            counts[status] += 1
            if status != "ok":
                problems.append({"library": name, "status": status, "title": item.get("title"),
                                 "year": item.get("year") or "", "rating_key": item["ratingKey"],
                                 "path": path, "note": note})
        total = sum(counts.values())
        log(f"  [{'ok' if counts['unmatched'] + counts['mismatch'] == 0 else '!'}] {total} items: "
            f"{counts['ok']} verified, {counts['mismatch']} matched WRONG, {counts['unmatched']} unmatched, "
            f"{counts['untagged']} not verifiable")
        for r in problems:
            if r["library"] == name and r["status"] in ("mismatch", "unmatched"):
                log(f"    [{r['status']}] {r['title']} ({r['year']}) - {r['note']}\n        {r['path']}")
    if any(r["status"] in ("mismatch", "unmatched") for r in problems):
        log("\nTo re-match the flagged items from their {tmdb-ID} tag: plexopt plex-index --rematch --execute")
    return problems


def rematch(plex, problems, execute=False, log=print):
    """Unmatch + refresh items so Plex re-reads the {tmdb-ID} tag. Dry run unless execute."""
    todo = [r for r in problems if r["status"] in ("mismatch", "unmatched") and TMDB_TAG.search(r["path"])]
    for r in todo:
        log(f"{'rematch' if execute else 'would rematch'}: {r['title']} -> {TMDB_TAG.findall(r['path'])[-1]}")
        if execute:
            if r["status"] == "mismatch":
                plex._req(f"/library/metadata/{r['rating_key']}/unmatch", method="PUT")
            plex._req(f"/library/metadata/{r['rating_key']}/refresh", method="PUT", force=1)
    if not todo:
        log("Nothing to rematch.")
    elif not execute:
        log(f"\nDry run: {len(todo)} items. Add --execute to do it. Anything still wrong afterwards: "
            "Plex Web > item > ... > Fix Match.")
    return todo


# ---------------------------------------------------------------------------
# Recommended server settings. Only prefs this server actually has are touched.

RECOMMENDED = [
    ("FSEventLibraryUpdatesEnabled", "1", "Scan my library automatically"),
    ("FSEventLibraryPartialScanEnabled", "1", "Run a partial scan when changes are detected"),
    ("ScheduledLibraryUpdatesEnabled", "1", "Scan my library periodically (catches anything missed)"),
    ("autoEmptyTrash", "0", "Don't empty trash after every scan (protects against an unplugged drive)"),
    ("HardwareAcceleratedCodecs", "1", "Hardware transcoding (Plex Pass)"),
    ("HardwareAcceleratedEncoders", "1", "Hardware-accelerated video encoding (Plex Pass)"),
    ("GenerateIntroMarkerBehavior", "scheduled", "Skip Intro detection (Plex Pass), overnight"),
    ("GenerateCreditsMarkerBehavior", "scheduled", "Skip Credits detection (Plex Pass), overnight"),
    ("GenerateBIFBehavior", "scheduled", "Scrubbing preview thumbnails, overnight"),
    ("LoudnessAnalysisBehavior", "scheduled", "Loudness levelling (Plex Pass), overnight"),
]


def _norm(v):
    if v in (True, "true"):
        return "1"
    if v in (False, "false"):
        return "0"
    return str(v)


def tune(plex, execute=False, log=print):
    prefs = plex.prefs()
    changes = {}
    for key, want, why in RECOMMENDED:
        if key not in prefs:
            log(f"  [skip] {why}: this Plex version has no '{key}' setting")
        elif _norm(prefs[key]) == want:
            log(f"  [ok]   {why}")
        else:
            log(f"  [{'set' if execute else 'would set'}] {why}: {prefs[key]!r} -> {want!r}")
            changes[key] = want
    if changes and execute:
        plex.set_pref(**changes)
        log(f"Applied {len(changes)} settings.")
    elif changes:
        log(f"Dry run: {len(changes)} settings to change. Add --execute to apply.")
    else:
        log("All recommended settings already in place.")
    return changes
