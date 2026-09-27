import json
import logging
import os
import queue
import signal
import sys
import time

from flask import Flask, jsonify, make_response, request, send_from_directory
from flask_sock import Sock

import auth
from mqtt_publisher import MqttPublisher
from poller import poller
from reader import COMMANDS, PowerViewError, read_monitor, send_command

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("sms_powerview.app")

app = Flask(__name__)
sock = Sock(app)
publisher = MqttPublisher()
poller.add_sink(publisher.publish)

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")


def _require_auth():
    if not auth.is_authenticated(request):
        return jsonify({"error": "unauthorized"}), 401
    return None


def _compute_events(entries):
    """Derives state-change events from a sequence of readings - e.g.
    "battery_in_use: Off -> On at 14:32:10" - by diffing each entry's info
    dict against the previous one. Newest first."""
    events = []
    prev_info = None
    for entry in entries:
        info = entry.get("info", {})
        if prev_info is not None:
            for key, value in info.items():
                if key.startswith("_"):
                    continue  # debug fields (e.g. _debug_estado_byte), not real events
                if prev_info.get(key) != value:
                    events.append(
                        {"ts": entry["ts"], "field": key, "from": prev_info.get(key), "to": value}
                    )
        prev_info = info
    events.reverse()
    return events


# --- API ---------------------------------------------------------------


@app.route("/api/auth-status", methods=["GET"])
def api_auth_status():
    """Lets the frontend tell 'not logged in' from 'auth disabled entirely'
    without guessing, and know whether the logout button should render."""
    return jsonify({"auth_enabled": auth.AUTH_ENABLED, "authenticated": auth.is_authenticated(request)})


@app.route("/api/login", methods=["POST"])
def api_login():
    body = request.get_json(silent=True) or {}
    if not auth.AUTH_ENABLED or auth.check_password(body.get("password", "")):
        resp = make_response(jsonify({"ok": True}))
        if auth.AUTH_ENABLED:
            resp.set_cookie(
                auth.COOKIE_NAME,
                auth.issue_token(),
                max_age=int(auth.JWT_EXPIRY_SECONDS),
                httponly=True,
                samesite="Lax",
            )
        return resp
    return jsonify({"ok": False, "error": "incorrect password"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp


@app.route("/api/history", methods=["GET"])
def api_history():
    unauth = _require_auth()
    if unauth:
        return unauth
    since = request.args.get("since", type=float, default=0.0)
    return jsonify(poller.history(since))


@app.route("/api/events", methods=["GET"])
def api_events():
    unauth = _require_auth()
    if unauth:
        return unauth
    since = request.args.get("since", type=float, default=0.0)
    return jsonify(_compute_events(poller.history(since)))


@app.route("/api/integration", methods=["GET"])
def api_integration():
    unauth = _require_auth()
    if unauth:
        return unauth
    return jsonify(publisher.status())


@app.route("/api/commands", methods=["GET"])
def api_commands():
    """The command catalog (name/description/danger/params) - the old
    Jinja template baked this into controls.html server-side; the React
    frontend fetches it instead."""
    unauth = _require_auth()
    if unauth:
        return unauth
    return jsonify(COMMANDS)


@app.route("/api/command", methods=["POST"])
def api_command():
    unauth = _require_auth()
    if unauth:
        return unauth

    body = request.get_json(silent=True) or {}
    name = body.get("name")
    params = body.get("params") or {}
    confirm = bool(body.get("confirm"))

    spec = COMMANDS.get(name)
    if spec is None:
        return jsonify({"error": f"unknown command {name!r}"}), 400
    if spec["danger"] != "low" and not confirm:
        return jsonify({"error": "this command requires confirm=true", "danger": spec["danger"]}), 400

    try:
        poller.submit_command(name, params)
    except PowerViewError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"ok": True})


@app.route("/monitor", methods=["GET"])
def monitor():
    """Deliberately unauthenticated - see json.html's old copy: this is
    what Home Assistant's REST integration (or anything else without a
    login flow) hits directly. Keep this route's path and no-auth
    behavior exactly as-is; it's a documented external integration point,
    not just an internal API call the frontend happens to use."""
    data, error = poller.latest()
    if data is None:
        return jsonify({"error": error or "no reading yet"}), 502
    return jsonify(data)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@sock.route("/ws")
def ws_route(ws):
    if not auth.is_authenticated(request):
        return

    updates = queue.Queue()

    def listener(data, error):
        updates.put((data, error))

    poller.add_listener(listener)
    try:
        data, error = poller.latest()
        ws.send(json.dumps({"data": data, "error": error}))
        while True:
            data, error = updates.get()
            ws.send(json.dumps({"data": data, "error": error}))
    except Exception:
        pass
    finally:
        poller.remove_listener(listener)


@sock.route("/ws/diagnostics")
def diagnostics_ws(ws):
    """Drives tools/watch_status.py's logic over a websocket instead of
    docker exec, so the log lands directly on /diagnostics for copying -
    see reader.py / that script's docstring for why this exists (real
    hardware disagreeing with the protocol XML's documented status bits).
    Talks to the serial port independently of the main poller, same
    caveat as the standalone tools: an occasional error from a collision
    with the app's own poll is normal noise.
    """
    if not auth.is_authenticated(request):
        return

    try:
        raw = ws.receive(timeout=30)
    except Exception:
        return
    if not raw:
        return

    try:
        req = json.loads(raw)
    except (TypeError, ValueError):
        return
    if not isinstance(req, dict):
        return

    mode = req.get("mode")
    try:
        duration = min(max(int(req.get("duration", 15)), 5), 120)
    except (TypeError, ValueError):
        duration = 15

    def emit(payload) -> bool:
        try:
            ws.send(json.dumps(payload))
            return True
        except Exception:
            return False

    def sample(t):
        data, error = None, None
        try:
            data = read_monitor()
        except PowerViewError as exc:
            error = str(exc)
        return emit({"type": "sample", "t": t, "data": data, "error": error})

    try:
        if not sample(0):
            return

        if mode == "transition":
            test_seconds = max(3, duration - 5)
            try:
                send_command("test_for_seconds", seconds=test_seconds)
                emit({"type": "instruction", "text": f"Sent test_for_seconds({test_seconds}s). Watching..."})
            except PowerViewError as exc:
                emit({"type": "error", "text": str(exc)})
        elif mode == "watch":
            emit({"type": "instruction", "text": "Trigger the event now (e.g. briefly unplug AC power)."})
        else:
            emit({"type": "error", "text": f"unknown mode {mode!r}"})
            return

        for t in range(1, duration + 1):
            time.sleep(1)
            if not sample(t):
                return

        emit({"type": "done"})
        # Give the "done" frame a moment to actually reach the client
        # before the connection closes - closing immediately after send()
        # otherwise races the browser's read, which was showing up
        # client-side as a spurious "websocket error" right at the end
        # of every run instead of a clean close.
        time.sleep(0.3)
    except Exception:
        logger.exception("diagnostics session failed")


# --- static frontend (built React SPA) ----------------------------------


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    """Serves the built React SPA for everything not already matched
    above (API/WS routes are registered first and take priority). Static
    assets (JS/CSS/favicon) are served directly if they exist on disk;
    any other path (client-side routes like /controls, /diagnostics)
    falls back to index.html so React Router (or whatever client routing
    is used) can handle it."""
    full_path = os.path.join(FRONTEND_DIST, path)
    if path and os.path.isfile(full_path):
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, "index.html")


def _handle_sigterm(signum, frame):
    logger.info("received signal %s, shutting down", signum)
    poller.stop()
    publisher.stop()
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)


def main():
    poller.start()
    publisher.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("JSON_PORT_INTERNAL", "5000")), threaded=True)


if __name__ == "__main__":
    main()
