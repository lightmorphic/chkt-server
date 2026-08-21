"""Version check against the project's GitHub releases. Cached for a day,
never blocks a page for more than a few seconds, and failing quietly means
"no banner", never a broken page."""
import json
import threading
import time
import urllib.request

VERSION = "1.1.18"
RELEASES_URL = "https://api.github.com/repos/lightmorphic/chkt-server/releases/latest"

_cache = {"checked_at": 0.0, "latest": None}
_lock = threading.Lock()


def _is_newer(candidate: str, current: str) -> bool:
    def parts(v):
        out = []
        for piece in v.strip().lstrip("v").replace("-", ".").split(".")[:3]:
            try:
                out.append(int(piece))
            except ValueError:
                out.append(0)
        return out
    a, b = parts(candidate), parts(current)
    length = max(len(a), len(b))
    a += [0] * (length - len(a))
    b += [0] * (length - len(b))
    return a > b


def available_update():
    """Returns the newer version string, or None. Checked at most daily."""
    with _lock:
        if time.time() - _cache["checked_at"] < 86400:
            latest = _cache["latest"]
            return latest if latest and _is_newer(latest, VERSION) else None
        _cache["checked_at"] = time.time()
    try:
        req = urllib.request.Request(RELEASES_URL, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            latest = json.load(resp).get("tag_name", "").lstrip("v")
        with _lock:
            _cache["latest"] = latest or None
        return latest if latest and _is_newer(latest, VERSION) else None
    except Exception:
        return None
