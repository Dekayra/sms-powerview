"""Single-password JWT auth.

There's one shared password (WEB_PASSWORD), not per-user accounts. If it's
left blank, auth is disabled entirely - fine for a trusted LAN, but means
anyone who can reach the port can read status and send commands. Set
WEB_PASSWORD if that matters to you.

JWT_SECRET can be pinned via env for sessions to survive a restart;
otherwise a random one is generated at startup, which invalidates existing
sessions each time the container restarts (an acceptable default for a
single-password tool - it just means logging in again).
"""
import hmac
import os
import secrets
import time

import jwt

WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")
JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
JWT_EXPIRY_SECONDS = float(os.environ.get("JWT_EXPIRY_HOURS", "24")) * 3600
COOKIE_NAME = "spv_token"

AUTH_ENABLED = bool(WEB_PASSWORD)


def check_password(password: str) -> bool:
    return hmac.compare_digest(password or "", WEB_PASSWORD)


def issue_token() -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": "user", "iat": now, "exp": now + int(JWT_EXPIRY_SECONDS)},
        JWT_SECRET,
        algorithm="HS256",
    )


def verify_token(token: str) -> bool:
    if not token:
        return False
    try:
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return True
    except jwt.PyJWTError:
        return False


def is_authenticated(request) -> bool:
    if not AUTH_ENABLED:
        return True
    return verify_token(request.cookies.get(COOKIE_NAME, ""))
