import os
from datetime import timedelta

from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import api, auth, backup, caldav, db, pushsvc, views


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

    @app.context_processor
    def _inject_version():
        # Every page can show which version is running (the corner badge in
        # base.html) without each view having to pass it along.
        from .update_check import VERSION
        return {"server_version": VERSION,
                "project_url": "https://github.com/lightmorphic/chkt-server"}

    @app.template_filter("datetimeformat")
    def datetimeformat(epoch_seconds):
        return datetime.fromtimestamp(int(epoch_seconds)).strftime("%d %b %Y, %H:%M")

    # Tailscale serve/funnel, Caddy and every other TLS terminator forward
    # plain HTTP inwards, so Flask built its redirects with http:// — a
    # CalDAV client following one leaves HTTPS and lands nowhere. Trust the
    # forwarded scheme only; the host stays whatever was actually asked for,
    # so a spoofed X-Forwarded-Host can't rewrite our URLs.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

    db.init_db()
    pushsvc.ensure_vapid_keys()
    pushsvc.start_engine()
    backup.start_daily_backups()

    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(caldav.bp)

    @app.after_request
    def harden(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        # Only meaningful when the request actually came over TLS (Funnel,
        # Caddy); harmless and ignored by browsers otherwise.
        if request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; base-uri 'self'; form-action 'self'",
        )
        return resp

    return app
