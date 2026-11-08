"""Flask app: serves the UI and a small JSON API over loopback."""

import secrets
from http import HTTPStatus
from ipaddress import ip_address
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from . import __version__
from .device import Device
from .errors import AppError

WILDCARD = ("0.0.0.0", "::", "")

CSP = (
    "default-src 'self'; img-src 'self' data:; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


def hostname(value):
    """Pull the host out of a Host or Origin header, IPv6 brackets included."""
    prefixed = value if "//" in value else "//" + value
    return (urlsplit(prefixed).hostname or "").lower()


def is_loopback(name):
    """Any 127.x address, ::1 or plain localhost. Everything else is another machine."""
    if name == "localhost":
        return True
    try:
        return ip_address(name).is_loopback
    except ValueError:
        return False


def browser_url(host, port):
    """Where to point a browser. Wildcard and loopback binds are all just localhost."""
    if host in WILDCARD or is_loopback(host):
        host = "localhost"
    elif ":" in host:
        host = "[%s]" % host
    return "http://%s:%d/" % (host, port)


def fail(message, code, kind="request", hint=""):
    body = {"error": message, "kind": kind}
    return jsonify(dict(body, hint=hint) if hint else body), code


def create_app(device=None):
    app = Flask(__name__)
    app.config.update(TOKEN=secrets.token_urlsafe(32), SEND_FILE_MAX_AGE_DEFAULT=0)
    mouse = device or Device()

    @app.before_request
    def guard():
        # Host stops DNS rebinding, Origin and the token stop cross-site posts
        if not is_loopback(hostname(request.host)):
            return fail(
                "Only loopback requests are allowed.",
                HTTPStatus.FORBIDDEN,
                hint="Reach it on localhost, or publish the port to 127.0.0.1 only.",
            )
        origin = request.headers.get("Origin")
        if origin and not is_loopback(hostname(origin)):
            return fail("Cross-origin requests are blocked.", HTTPStatus.FORBIDDEN)
        if request.method == "POST" and not secrets.compare_digest(
            request.headers.get("X-Token", ""), app.config["TOKEN"]
        ):
            return fail(
                "Missing or invalid token.",
                HTTPStatus.FORBIDDEN,
                hint="Reload the page to pick up a fresh one.",
            )

    @app.after_request
    def headers(response):
        response.headers.update(
            {
                "Content-Security-Policy": CSP,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    @app.errorhandler(AppError)
    def device_trouble(error):
        app.logger.warning(error.log_line())
        return jsonify(error.as_dict()), error.status

    @app.errorhandler(HTTPException)
    def http_problem(error):
        return fail(error.description, error.code)

    @app.errorhandler(Exception)
    def crash(error):
        app.logger.error("unhandled %s: %s", type(error).__name__, error, exc_info=True)
        return fail(
            "Something broke inside rivalcfg-gui.",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            kind="bug",
            hint="Re-run with --log-level debug for the traceback.",
        )

    @app.get("/")
    def index():
        return render_template("index.html", token=app.config["TOKEN"], version=__version__)

    @app.get("/api/status")
    def status():
        return jsonify(mouse.status())

    @app.get("/api/schema")
    def schema():
        return jsonify(mouse.schema())

    @app.post("/api/settings")
    def write():
        body = request.get_json(silent=True)
        name = body.get("name") if isinstance(body, dict) else None
        if not isinstance(name, str):
            return fail("A setting name is required.", HTTPStatus.BAD_REQUEST)
        try:
            return jsonify({"values": mouse.apply(name, body.get("value"))})
        except (ValueError, TypeError, KeyError) as error:
            return fail(str(error), HTTPStatus.BAD_REQUEST, kind="invalid")

    @app.post("/api/save")
    def save():
        mouse.persist()
        return jsonify({"ok": True})

    @app.post("/api/reset")
    def reset():
        return jsonify({"values": mouse.reset()})

    return app
