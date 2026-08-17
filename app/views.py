"""Web UI routes. Server-rendered pages, no framework, house style."""
import io
import json
from datetime import datetime

import pyotp
from flask import (Blueprint, Response, abort, jsonify, redirect, render_template,
                   request, send_file, session, url_for)

from . import backup, db, pushsvc, store
from .auth import (check_csrf, csrf_token, list_access_keys, login_required,
                   new_access_key, revoke_access_key)
from .emailer import outbox, send as send_email
from .settings_store import SECRET_KEYS, get as setting, put as setting_put, save_form

bp = Blueprint("views", __name__)

ALERT_MODES = [
    ("NOTIFY_AND_SPEAK", "Notification + voice"),
    ("SPEAK_ONLY", "Voice only"),
    ("NOTIFY_ONLY", "Notification only"),
]
SNOOZES = [(10, "10 min"), (30, "30 min"), (60, "1 hr"), (180, "3 hrs"), (720, "12 hrs"), (1440, "1 day")]


def _csrf_or_400():
    if not check_csrf():
        abort(400, "The form has expired, reload the page and try again.")


@bp.get("/healthz")
def healthz():
    with db.connect() as conn:
        conn.execute("SELECT 1")
    return jsonify({"ok": True})


@bp.get("/")
@login_required
def home():
    tag = (request.args.get("tag") or "").strip() or None
    everything = store.reminders()
    shown = [r for r in everything if tag is None or tag in store.tag_list(r)]
    return render_template(
        "home.html", reminders=shown, tags=store.all_tags(), active_tag=tag,
        describe=_describe, tag_list=store.tag_list, csrf=csrf_token(),
    )


@bp.route("/reminder/new", methods=["GET", "POST"])
@bp.route("/reminder/<reminder_id>/edit", methods=["GET", "POST"])
@login_required
def reminder_edit(reminder_id=None):
    reminder = store.get_reminder(reminder_id) if reminder_id else None
    if request.method == "POST":
        _csrf_or_400()
        saved = _reminder_from_form(request.form, reminder)
        if saved:
            store.upsert_reminder(saved)
            return redirect(url_for("views.home"))
    # One screen with every field for both creating and editing, matching the app.
    return render_template(
        "edit_reminder.html",
        reminder=reminder, known_tags=store.all_tags(),
        alert_modes=ALERT_MODES, csrf=csrf_token(),
        preset_tag=request.args.get("tag", ""),
        due_local=_millis_to_local(reminder["due_at"]) if reminder and reminder["due_at"] else "",
    )


@bp.post("/reminder/<reminder_id>/delete")
@login_required
def reminder_delete(reminder_id):
    _csrf_or_400()
    store.soft_delete("reminders", reminder_id)
    return redirect(url_for("views.home"))


@bp.post("/reminder/<reminder_id>/done")
@login_required
def reminder_done(reminder_id):
    _csrf_or_400()
    r = store.get_reminder(reminder_id)
    if r:
        store.acknowledge(reminder_id, r.get("due_at") or db.now_millis(), "DONE")
    return redirect(request.referrer or url_for("views.home"))


@bp.post("/reminder/<reminder_id>/snooze")
@login_required
def reminder_snooze(reminder_id):
    _csrf_or_400()
    minutes = int(request.form.get("minutes") or 10)
    r = store.get_reminder(reminder_id)
    if r and 1 <= minutes <= 1440:
        store.add_log(reminder_id, r.get("due_at") or db.now_millis(), "SNOOZED")
        r["snoozed_until"] = db.now_millis() + minutes * 60_000
        r["nag_started_at"] = None
        r["updated_at"] = db.now_millis()
        store.upsert_reminder(r)
    return redirect(request.referrer or url_for("views.home"))


@bp.get("/stats")
@login_required
def stats():
    thirty_days = db.now_millis() - 30 * 24 * 3600 * 1000
    return render_template("stats.html", stats=store.log_counts(thirty_days), csrf=csrf_token())


# ---- Settings ----

@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    message = ""
    if request.method == "POST":
        _csrf_or_400()
        section = request.form.get("section")
        if section == "email":
            save_form(request.form, ["alert_email", "smtp_host", "smtp_port",
                                     "smtp_from", "smtp_username", "smtp_password"])
            message = "Email settings saved."
        elif section == "github":
            save_form(request.form, ["github_repo", "github_token"])
            message = "GitHub backup settings saved."
        elif section == "quiet":
            from .settings_store import set_quiet_hours
            set_quiet_hours(
                enabled=bool(request.form.get("quiet_enabled")),
                start=(request.form.get("quiet_start") or "22:00"),
                end=(request.form.get("quiet_end") or "07:00"),
            )
            message = "Quiet hours saved."
    from .update_check import VERSION, available_update
    from .settings_store import quiet_hours
    values = {k: setting(k) for k in ("alert_email", "smtp_host", "smtp_port",
                                      "smtp_from", "smtp_username", "github_repo")}
    return render_template(
        "settings.html", values=values, message=message,
        server_version=VERSION, update_available=available_update(),
        smtp_password_set=bool(setting("smtp_password")),
        github_token_set=bool(setting("github_token")),
        totp_enabled=bool(setting("totp_secret")),
        quiet=quiet_hours(),
        outbox=outbox(), csrf=csrf_token(),
    )


@bp.post("/settings/test-email")
@login_required
def settings_test_email():
    _csrf_or_400()
    ok, message = send_email("CHKT test message", "If you can read this, CHKT's email settings work.")
    return render_template("fragment_message.html", message=message, ok=ok)


@bp.post("/settings/test-github")
@login_required
def settings_test_github():
    _csrf_or_400()
    message = backup.github_test()
    return render_template("fragment_message.html", message=message, ok=message.startswith("Connected. Repository"))


@bp.post("/settings/backup-now")
@login_required
def settings_backup_now():
    _csrf_or_400()
    path = backup.write_daily_backup()
    return render_template("fragment_message.html", message=f"Backup written: {path.rsplit('/', 1)[-1]}", ok=True)


@bp.post("/settings/2fa")
@login_required
def settings_2fa():
    _csrf_or_400()
    action = request.form.get("action")
    if action == "start":
        secret = pyotp.random_base32()
        session["totp_pending"] = secret
        uri = pyotp.TOTP(secret).provisioning_uri(name="chkt", issuer_name="CHKT Server")
        return render_template("twofa_confirm.html", secret=secret, uri=uri, csrf=csrf_token())
    if action == "confirm":
        secret = session.get("totp_pending", "")
        code = (request.form.get("code") or "").strip()
        if secret and pyotp.TOTP(secret).verify(code, valid_window=1):
            setting_put("totp_secret", secret)
            session.pop("totp_pending", None)
            return redirect(url_for("views.settings_page"))
        uri = pyotp.TOTP(secret).provisioning_uri(name="chkt", issuer_name="CHKT Server") if secret else ""
        return render_template("twofa_confirm.html", secret=secret, uri=uri,
                               error="That code didn't match, try again.", csrf=csrf_token())
    if action == "disable":
        setting_put("totp_secret", "")
    return redirect(url_for("views.settings_page"))


# ---- Devices (sync access keys) ----

@bp.route("/devices", methods=["GET", "POST"])
@login_required
def devices():
    fresh_key = None
    if request.method == "POST":
        _csrf_or_400()
        if request.form.get("revoke"):
            revoke_access_key(request.form["revoke"])
        else:
            fresh_key = new_access_key((request.form.get("label") or "").strip() or "Device")
    return render_template("devices.html", keys=list_access_keys(),
                           fresh_key=fresh_key, csrf=csrf_token())


@bp.get("/devices/status")
@login_required
def devices_status():
    """Polled by the Devices page so a phone connecting shows up live,
    no manual refresh needed to see it land."""
    return jsonify({
        "keys": [
            {"id": k["id"], "last_used_at": k["last_used_at"]}
            for k in list_access_keys()
        ]
    })


# ---- Export / import / restore ----

@bp.get("/export.json")
@login_required
def export_json_route():
    return Response(backup.export_json(), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=chkt-export.json"})


@bp.get("/export.md")
@login_required
def export_md():
    lines = ["# CHKT reminders", ""]
    for r in store.reminders():
        entry = f"- [ ] **{r['title']}**"
        described = _describe(r)
        if described:
            entry += f", {described}"
        hashtags = " ".join("#" + t for t in store.tag_list(r))
        if hashtags:
            entry += "  " + hashtags
        lines.append(entry)
        if r["notes"]:
            lines.append(f"  {r['notes']}")
    body = "\n".join(lines) + f"\n\n_Exported {datetime.now():%Y-%m-%d %H:%M} by CHKT._\n"
    return Response(body, mimetype="text/markdown",
                    headers={"Content-Disposition": "attachment; filename=chkt-export.md"})


@bp.get("/chkt-everything.zip")
@login_required
def zip_route():
    return send_file(io.BytesIO(backup.zip_everything()), mimetype="application/zip",
                     as_attachment=True, download_name="chkt-everything.zip")


@bp.post("/import")
@login_required
def import_route():
    _csrf_or_400()
    f = request.files.get("file")
    replace = request.form.get("mode") == "replace"
    if not f:
        return render_template("fragment_message.html", message="Choose a file first.", ok=False)
    count = backup.import_json(f.read().decode("utf-8", "replace"), replace=replace)
    if count < 0:
        return render_template("fragment_message.html",
                               message="That doesn't look like a CHKT JSON export.", ok=False)
    return render_template("fragment_message.html",
                           message=f"Imported {count} reminders.", ok=True)


# ---- Web app plumbing (PWA, push, in-page alerts) ----

@bp.get("/web/vapid")
@login_required
def web_vapid():
    return jsonify({"key": pushsvc.public_key()})


@bp.post("/web/subscribe")
@login_required
def web_subscribe():
    if request.headers.get("X-CSRF", "") != session.get("csrf", "-"):
        abort(400)
    sub = request.get_json(silent=True)
    if sub and "endpoint" in sub:
        pushsvc.add_subscription(sub)
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400


@bp.get("/web/fired")
@login_required
def web_fired():
    since = int(request.args.get("since") or db.now_millis())
    return jsonify({"now": db.now_millis(), "fired": pushsvc.recently_fired(since)})


# ---- helpers ----

def _describe(r) -> str:
    parts = []
    if r.get("due_at"):
        parts.append(datetime.fromtimestamp(r["due_at"] / 1000).strftime("%a %d %b, %H:%M"))
    rule = r.get("repeat_rule") or ""
    if rule == "DAILY":
        parts.append("daily")
    elif rule.startswith("WEEKLY:"):
        parts.append("weekly (" + rule[7:].replace(",", ", ").title() + ")")
    elif rule == "MONTHLY:LAST":
        parts.append("monthly (last day)")
    elif rule.startswith("MONTHLY:"):
        parts.append(f"monthly (day {rule[8:]})")
    elif rule.startswith("YEARLY:"):
        parts.append("yearly")
    elif rule.startswith("EVERY:"):
        parts.append("every " + rule[6:])
    trigger = r.get("location_trigger", "NONE")
    if trigger == "ARRIVE":
        parts.append("on arrival")
    elif trigger == "LEAVE":
        parts.append("on leaving")
    return " · ".join(parts)


def _millis_to_local(millis: int) -> str:
    return datetime.fromtimestamp(millis / 1000).strftime("%Y-%m-%dT%H:%M")


def _reminder_from_form(form, existing):
    title = (form.get("title") or "").strip()
    if not title:
        return None
    due_raw = (form.get("due") or "").strip()
    due_at = None
    if due_raw:
        try:
            due_at = int(datetime.strptime(due_raw, "%Y-%m-%dT%H:%M").timestamp() * 1000)
        except ValueError:
            return None

    kind = form.get("repeat_kind") or "NONE"
    if kind == "DAILY":
        rule = "DAILY"
    elif kind == "WEEKLY":
        days = [d for d in form.getlist("weekday") if d in ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")]
        rule = "WEEKLY:" + ",".join(days) if days else ""
    elif kind == "MONTHLY":
        arg = (form.get("monthday") or "").strip().upper()
        rule = "MONTHLY:LAST" if arg == "LAST" else (
            f"MONTHLY:{int(arg)}" if arg.isdigit() and 1 <= int(arg) <= 31 else "")
    elif kind == "YEARLY":
        rule = f"YEARLY:{datetime.fromtimestamp(due_at / 1000):%m-%d}" if due_at else ""
    elif kind == "EVERY":
        n = (form.get("every_n") or "").strip()
        unit = form.get("every_unit") or "d"
        rule = f"EVERY:{int(n)}{unit}" if n.isdigit() and int(n) > 0 and unit in "mhdwy" else ""
    else:
        rule = ""

    trigger = form.get("location_trigger") or "NONE"
    if trigger not in ("NONE", "ARRIVE", "LEAVE"):
        trigger = "NONE"

    def _float_or_none(name):
        raw = (form.get(name) or "").strip()
        try:
            return float(raw) if raw else None
        except ValueError:
            return None

    def _int_in(name, allowed, fallback):
        raw = (form.get(name) or "").strip()
        try:
            value = int(raw)
        except ValueError:
            return fallback
        return value if value in allowed else fallback

    now = db.now_millis()
    base = existing or {
        "id": db.new_id(), "created_at": now, "snoozed_until": None, "deleted_at": None,
    }
    record = dict(base)
    tags = ", ".join(
        t.strip() for t in (form.get("tags") or "").split(",") if t.strip())
    record.update({
        "tags": tags,
        "title": title,
        "notes": (form.get("notes") or "").strip(),
        "due_at": due_at,
        "repeat_rule": rule,
        "alert_mode": store.normalize_alert_mode(form.get("alert_mode")),
        # No longer settable in the UI; kept only so existing rows don't
        # need a schema change.
        "pre_tone": 0,
        "enabled": 1 if form.get("active") else 0,
        "vibrate": 1 if form.get("vibrate") else 0,
        "respect_dnd": 1 if form.get("respect_dnd") else 0,
        "nag_interval_minutes": _int_in("nag_interval", {0, 1, 2, 5}, 0),
        "nag_stop_after_minutes": _int_in("nag_stop_after", {15, 30, 60, 120}, 60),
        "nag_started_at": None,
        "delete_after_dismissed": 1 if form.get("delete_after_dismissed") else 0,
        "location_trigger": trigger,
        "latitude": _float_or_none("latitude"),
        "longitude": _float_or_none("longitude"),
        "radius_metres": _float_or_none("radius") or 150.0,
        "updated_at": now,
    })
    return record
