"""Backups: daily JSON snapshots kept locally, optional offsite copy pushed
to a private GitHub repo, zip-everything download, and restore.

The GitHub copy uses the contents API over HTTPS (no git binary needed).
"""
import base64
import io
import json
import os
import threading
import time
import urllib.request
import zipfile
from datetime import date, datetime

from . import db, store
from .settings_store import get as setting

KEEP = 30


def backup_dir():
    return os.environ.get(
        "CHKT_BACKUP_DIR",
        os.path.join(os.path.dirname(os.path.abspath(db.db_path())), "backups"),
    )
_started = False


def export_json() -> str:
    data = store.changed_since(0)
    return json.dumps({
        "app": "chkt",
        "version": 1,
        "exportedAt": datetime.now().astimezone().isoformat(),
        "lists": [
            {"id": r["id"], "name": r["name"], "position": r["position"],
             "updatedAt": r["updated_at"], "deletedAt": r["deleted_at"]}
            for r in data["lists"]
        ],
        "reminders": [
            {"id": r["id"], "listId": r["list_id"], "title": r["title"], "notes": r["notes"],
             "dueAt": r["due_at"], "repeatRule": r["repeat_rule"], "alertMode": r["alert_mode"],
             "preTone": bool(r["pre_tone"]), "enabled": bool(r["enabled"]),
             "vibrate": bool(r["vibrate"]), "respectDnd": bool(r["respect_dnd"]),
             "nagIntervalMinutes": r["nag_interval_minutes"],
             "nagStopAfterMinutes": r["nag_stop_after_minutes"],
             "deleteAfterDismissed": bool(r["delete_after_dismissed"]),
             "locationTrigger": r["location_trigger"], "latitude": r["latitude"],
             "longitude": r["longitude"], "radiusMetres": r["radius_metres"],
             "createdAt": r["created_at"], "updatedAt": r["updated_at"],
             "deletedAt": r["deleted_at"]}
            for r in data["reminders"]
        ],
        "logs": [
            {"id": r["id"], "reminderId": r["reminder_id"], "dueAt": r["due_at"],
             "action": r["action"], "at": r["at"]}
            for r in data["logs"]
        ],
    }, indent=2)


def import_json(raw: str, replace: bool = False) -> int:
    """Merge (or replace) from a Chkt JSON export. Returns reminders imported, -1 on bad file."""
    try:
        data = json.loads(raw)
        if data.get("app") != "chkt":
            return -1
        if replace:
            with db.connect() as conn:
                conn.execute("DELETE FROM reminders")
                conn.execute("DELETE FROM lists")
        for o in data.get("lists", []):
            store.upsert_list({
                "id": str(o["id"]), "name": str(o["name"]),
                "position": int(o.get("position") or 0),
                "updated_at": int(o.get("updatedAt") or db.now_millis()),
                "deleted_at": o.get("deletedAt"),
            })
        count = 0
        for o in data.get("reminders", []):
            store.upsert_reminder({
                "id": str(o["id"]), "list_id": str(o["listId"]),
                "title": str(o["title"]), "notes": str(o.get("notes") or ""),
                "due_at": o.get("dueAt"), "repeat_rule": str(o.get("repeatRule") or ""),
                "alert_mode": str(o.get("alertMode") or "RING_AND_SPEAK"),
                "pre_tone": 1 if o.get("preTone") else 0,
                "enabled": 1 if o.get("enabled", True) else 0,
                "vibrate": 1 if o.get("vibrate", True) else 0,
                "respect_dnd": 1 if o.get("respectDnd") else 0,
                "nag_interval_minutes": int(o.get("nagIntervalMinutes") or 0),
                "nag_stop_after_minutes": int(o.get("nagStopAfterMinutes") or 60),
                "nag_started_at": None,
                "delete_after_dismissed": 1 if o.get("deleteAfterDismissed") else 0,
                "snoozed_until": o.get("snoozedUntil"),
                "location_trigger": str(o.get("locationTrigger") or "NONE"),
                "latitude": o.get("latitude"), "longitude": o.get("longitude"),
                "radius_metres": float(o.get("radiusMetres") or 150.0),
                "created_at": int(o.get("createdAt") or db.now_millis()),
                "updated_at": int(o.get("updatedAt") or db.now_millis()),
                "deleted_at": o.get("deletedAt"),
            })
            count += 1
        return count
    except (ValueError, KeyError, TypeError):
        return -1


def write_daily_backup() -> str:
    os.makedirs(backup_dir(), exist_ok=True)
    name = f"chkt-backup-{date.today().isoformat()}.json"
    path = os.path.join(backup_dir(), name)
    with open(path, "w") as f:
        f.write(export_json())
    _prune()
    _github_push(name, path)
    return path


def _prune():
    files = sorted(
        f for f in os.listdir(backup_dir()) if f.startswith("chkt-backup-")
    )
    for old in files[:-KEEP]:
        os.remove(os.path.join(backup_dir(), old))


def _github_push(name: str, path: str):
    """Offsite copy via the GitHub contents API. Quietly skipped when not set up."""
    repo = setting("github_repo")     # e.g. "lightmorphic/chkt-data"
    token = setting("github_token")
    if not repo or not token:
        return
    with open(path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    url = f"https://api.github.com/repos/{repo}/contents/backups/{name}"

    def _request(method, body):
        req = urllib.request.Request(url, method=method,
                                     data=json.dumps(body).encode() if body else None)
        req.add_header("Authorization", "Bearer " + token)
        req.add_header("Accept", "application/vnd.github+json")
        return urllib.request.urlopen(req, timeout=20)

    try:
        # Need the existing file's sha to overwrite same-day backups.
        sha = None
        try:
            with _request("GET", None) as resp:
                sha = json.load(resp).get("sha")
        except Exception:
            pass
        body = {"message": f"Chkt backup {name}", "content": content}
        if sha:
            body["sha"] = sha
        _request("PUT", body).close()
    except Exception:
        # Offsite copy failing must never break the local backup.
        pass


def github_test() -> str:
    repo = setting("github_repo")
    token = setting("github_token")
    if not repo or not token:
        return "Set the repository and token first."
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}")
        req.add_header("Authorization", "Bearer " + token)
        req.add_header("Accept", "application/vnd.github+json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            info = json.load(resp)
        if info.get("private") is False:
            return "Connected, but that repository is PUBLIC. Use a private one for backups."
        return "Connected. Repository reachable and private."
    except Exception as e:
        return f"Couldn't reach the repository: {e}"


def zip_everything() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("chkt-export.json", export_json())
        if os.path.isdir(backup_dir()):
            for f in sorted(os.listdir(backup_dir())):
                z.write(os.path.join(backup_dir(), f), "backups/" + f)
    return buf.getvalue()


def _loop():
    while True:
        try:
            write_daily_backup()
        except Exception:
            pass
        time.sleep(24 * 3600)


def start_daily_backups():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="chkt-backup").start()
