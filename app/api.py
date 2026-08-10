"""Sync API — the contract the Android app's SyncClient speaks.

Auth is a Bearer access key created on the Devices page. Merge is
newest-wins by updated_at with tombstones; completion logs are append-only.
"""
from flask import Blueprint, jsonify, request

from . import db, store
from .auth import verify_access_key

bp = Blueprint("api", __name__, url_prefix="/api")


def _authed() -> bool:
    header = request.headers.get("Authorization", "")
    return header.startswith("Bearer ") and verify_access_key(header[7:])


@bp.get("/ping")
def ping():
    if not _authed():
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "name": "chkt-server"})


@bp.post("/sync")
def sync():
    if not _authed():
        return jsonify({"ok": False}), 401
    body = request.get_json(silent=True) or {}
    since = int(body.get("since") or 0)

    # What the server will send back: everything that changed after `since`,
    # captured BEFORE applying the client's batch so the client's own records
    # don't echo straight back.
    outgoing = store.changed_since(since)

    for record in body.get("lists") or []:
        incoming = _list_from_json(record)
        if incoming is None:
            continue
        existing = _existing("lists", incoming["id"])
        if existing is None or existing["updated_at"] < incoming["updated_at"]:
            store.upsert_list(incoming)

    for record in body.get("reminders") or []:
        incoming = _reminder_from_json(record)
        if incoming is None:
            continue
        existing = _existing("reminders", incoming["id"])
        if existing is None or existing["updated_at"] < incoming["updated_at"]:
            store.upsert_reminder(incoming)

    for record in body.get("logs") or []:
        try:
            with db.connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO completion_log (id, reminder_id, due_at, action, at) "
                    "VALUES (?,?,?,?,?)",
                    (str(record["id"]), str(record["reminderId"]),
                     int(record["dueAt"]), str(record["action"]), int(record["at"])),
                )
        except (KeyError, TypeError, ValueError):
            continue

    return jsonify({
        "now": db.now_millis(),
        "lists": [_list_to_json(r) for r in outgoing["lists"]],
        "reminders": [_reminder_to_json(r) for r in outgoing["reminders"]],
        "logs": [
            {"id": r["id"], "reminderId": r["reminder_id"], "dueAt": r["due_at"],
             "action": r["action"], "at": r["at"]}
            for r in outgoing["logs"]
        ],
    })


def _existing(table, record_id):
    with db.connect() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        return dict(row) if row else None


def _list_from_json(o):
    try:
        return {
            "id": str(o["id"]), "name": str(o["name"]),
            "position": int(o.get("position") or 0),
            "updated_at": int(o["updatedAt"]),
            "deleted_at": int(o["deletedAt"]) if o.get("deletedAt") is not None else None,
        }
    except (KeyError, TypeError, ValueError):
        return None


def _list_to_json(r):
    return {"id": r["id"], "name": r["name"], "position": r["position"],
            "updatedAt": r["updated_at"], "deletedAt": r["deleted_at"]}


def _reminder_from_json(o):
    try:
        return {
            "id": str(o["id"]), "list_id": str(o["listId"]),
            "title": str(o["title"]), "notes": str(o.get("notes") or ""),
            "due_at": int(o["dueAt"]) if o.get("dueAt") is not None else None,
            "repeat_rule": str(o.get("repeatRule") or ""),
            "alert_mode": str(o.get("alertMode") or "RING_AND_SPEAK"),
            "pre_tone": 1 if o.get("preTone") else 0,
            "enabled": 1 if o.get("enabled", True) else 0,
            "snoozed_until": int(o["snoozedUntil"]) if o.get("snoozedUntil") is not None else None,
            "location_trigger": str(o.get("locationTrigger") or "NONE"),
            "latitude": float(o["latitude"]) if o.get("latitude") is not None else None,
            "longitude": float(o["longitude"]) if o.get("longitude") is not None else None,
            "radius_metres": float(o.get("radiusMetres") or 150.0),
            "created_at": int(o.get("createdAt") or db.now_millis()),
            "updated_at": int(o["updatedAt"]),
            "deleted_at": int(o["deletedAt"]) if o.get("deletedAt") is not None else None,
        }
    except (KeyError, TypeError, ValueError):
        return None


def _reminder_to_json(r):
    return {
        "id": r["id"], "listId": r["list_id"], "title": r["title"], "notes": r["notes"],
        "dueAt": r["due_at"], "repeatRule": r["repeat_rule"], "alertMode": r["alert_mode"],
        "preTone": bool(r["pre_tone"]), "enabled": bool(r["enabled"]),
        "snoozedUntil": r["snoozed_until"], "locationTrigger": r["location_trigger"],
        "latitude": r["latitude"], "longitude": r["longitude"],
        "radiusMetres": r["radius_metres"], "createdAt": r["created_at"],
        "updatedAt": r["updated_at"], "deletedAt": r["deleted_at"],
    }
