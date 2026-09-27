"""Talk to your Plex Media Server: check remote access, create libraries, rescan, clean up.

Needs your X-Plex-Token. How to find it:
https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/
"""
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request


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
            "music": ("tv.plex.agents.music", "Plex Music"),
        }[kind]
        params = [("name", name), ("type", {"homevideo": "movie", "music": "artist"}.get(kind, kind)),
                  ("agent", agent), ("scanner", scanner), ("language", "en-US")]
        params += [("location", loc) for loc in locations]
        if self.token:
            params.append(("X-Plex-Token", self.token))
        url = f"{self.url}/library/sections?{urllib.parse.urlencode(params)}"
        urllib.request.urlopen(urllib.request.Request(url, method="POST"), timeout=60).read()

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
