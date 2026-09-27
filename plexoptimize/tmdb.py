"""Match parsed names against The Movie Database (free API key: themoviedb.org/settings/api).

Confidence (0-100) blends title similarity, year agreement, and - for movies - how
closely TMDB's runtime matches the file's real duration. The runtime check is
what rescues files whose names are wrong or meaningless.
"""
import difflib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.themoviedb.org/3"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    s = re.sub(r"\b(the|a|an)\b", " ", s)
    return " ".join(s.split())


class TMDB:
    def __init__(self, key, inv):
        self.key = key
        self.inv = inv

    def _get(self, path, **params):
        headers = {"Accept": "application/json"}
        if len(self.key) > 40:  # v4 "API Read Access Token"
            headers["Authorization"] = f"Bearer {self.key}"
        else:
            params["api_key"] = self.key
        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        cache_key = re.sub(r"api_key=[^&]+&?", "", url)
        cached = self.inv.cache_get(cache_key)
        if cached is not None:
            return cached
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
                    body = json.loads(r.read())
                self.inv.cache_put(cache_key, body)
                return body
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self.inv.cache_put(cache_key, {})
                    return {}
                if e.code == 401:
                    raise SystemExit("TMDB rejected the API key. Check --tmdb-key / TMDB_API_KEY.")
                time.sleep(2 ** attempt)
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** attempt)
        return {}

    def search(self, kind, title, year=None):
        if kind == "movie":
            params = {"query": title, "include_adult": "false"}
            if year:
                params["year"] = year
            res = self._get("/search/movie", **params).get("results", [])
            if not res and year:
                res = self._get("/search/movie", query=title, include_adult="false").get("results", [])
        else:
            params = {"query": title}
            if year:
                params["first_air_date_year"] = year
            res = self._get("/search/tv", **params).get("results", [])
            if not res and year:
                res = self._get("/search/tv", query=title).get("results", [])
        return res[:8]

    def movie(self, tmdb_id):
        return self._get(f"/movie/{tmdb_id}")

    def show(self, tmdb_id):
        return self._get(f"/tv/{tmdb_id}")

    def episode_title(self, show_id, season, episode):
        data = self._get(f"/tv/{show_id}/season/{season}")
        for ep in data.get("episodes", []):
            if ep.get("episode_number") == episode:
                return ep.get("name")
        return None

    def match(self, g, probe):
        kind = "movie" if g["kind"] != "episode" else "tv"
        duration_min = (probe or {}).get("duration", 0) / 60 if probe else 0
        best = None
        for cand in g["candidates"]:
            for r in self.search(kind, cand["title"], cand["year"]):
                name = r.get("title") or r.get("name") or ""
                orig = r.get("original_title") or r.get("original_name") or ""
                date = r.get("release_date") or r.get("first_air_date") or ""
                ryear = int(date[:4]) if date[:4].isdigit() else None
                sim = max(difflib.SequenceMatcher(None, norm(cand["title"]), norm(name)).ratio(),
                          difflib.SequenceMatcher(None, norm(cand["title"]), norm(orig)).ratio())
                score = sim * 70
                if cand["year"] and ryear:
                    score += {0: 20, 1: 12}.get(abs(cand["year"] - ryear), -15)
                elif not cand["year"]:
                    score += 5
                score += min(r.get("popularity", 0), 50) / 10  # tiny tiebreak toward well-known titles
                if cand["source"] not in ("path", "filename"):
                    score -= 3
                best = max(best or (score, None, None, None), (score, r, cand, ryear), key=lambda x: x[0])
        if not best or best[1] is None:
            return None
        score, r, cand, ryear = best
        result = {
            "type": kind,
            "tmdb_id": r["id"],
            "title": r.get("title") or r.get("name"),
            "year": ryear,
            "from": cand["source"],
        }
        if kind == "movie" and duration_min > 20:
            runtime = self.movie(r["id"]).get("runtime") or 0
            if runtime:
                diff = abs(runtime - duration_min)
                result["runtime"] = runtime
                score += 10 if diff <= 5 else (0 if diff <= 15 else -20)
        result["confidence"] = int(max(0, min(100, score)))
        return result
