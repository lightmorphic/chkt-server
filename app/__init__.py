import os
from datetime import timedelta

from flask import Flask

from . import api, auth, backup, db, pushsvc, views


def create_app():
    app = Flask(__name__)
    secret = os.environ.get("SECRET_KEY", "")
    if not secret:
        raise RuntimeError(
            "SECRET_KEY is not set. Generate one with:  python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    app.config.update(
        SECRET_KEY=secret,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("CHKT_INSECURE_COOKIES") != "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    )

    from datetime import datetime

    @app.template_filter("datetimeformat")
    def datetimeformat(epoch_seconds):
        return datetime.fromtimestamp(int(epoch_seconds)).strftime("%d %b %Y, %H:%M")

    db.init_db()
    pushsvc.ensure_vapid_keys()
    pushsvc.start_engine()
    backup.start_daily_backups()

    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)
    app.register_blueprint(api.bp)

    @app.after_request
    def harden(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; base-uri 'self'; form-action 'self'",
        )
        return resp

    return app
