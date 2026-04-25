"""Optional shared-password auth for ``grok-orchestra serve``.

Threat model
------------
Local-first development = no auth needed; the server binds to
``127.0.0.1`` by default. The moment you expose ``grok-orchestra
serve`` on a public hostname (Render, Fly.io, a tunnel) you become
liable for every token a stranger burns. This module's whole job is
to make that case opt-in safe.

Design
------
- **Off by default.** When ``GROK_ORCHESTRA_AUTH_PASSWORD`` is unset,
  every request is allowed and no cookie is set. Existing dev flows
  are byte-for-byte unchanged.
- **One env var, no DB.** When the password is set, the backend
  enforces it on the expensive endpoints (``POST /api/run``,
  ``WS /ws/runs/*``). Cheap endpoints (``GET /api/health``,
  ``GET /api/templates``) stay open so the login page can render
  without a session.
- **Cookie-based session.** ``POST /api/auth/login`` accepts a JSON
  body ``{"password": "..."}`` and, on match, sets an ``HttpOnly``
  ``__orchestra_session`` cookie containing an HMAC-signed token.
  Sessions live 24 h; the cookie is ``Secure`` when the request is
  https.
- **No persistence.** Tokens are stateless (HMAC of ``user|exp``
  with the password as the key). Rotating the password invalidates
  every session — the entire feature.
- **Library-friendly.** ``auth_dependency()`` is a regular FastAPI
  dependency; ``ws_auth_ok()`` is a small helper for the WebSocket
  handler. Both no-op when the password is unset.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

from fastapi import Cookie, Depends, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel

__all__ = [
    "AUTH_COOKIE_NAME",
    "LoginBody",
    "auth_dependency",
    "auth_enabled",
    "create_session_token",
    "register_auth_routes",
    "verify_session_token",
    "ws_auth_ok",
]

AUTH_COOKIE_NAME = "__orchestra_session"
AUTH_HEADER_NAME = "Authorization"
SESSION_TTL_SECONDS = 24 * 60 * 60


class LoginBody(BaseModel):
    password: str


# --------------------------------------------------------------------------- #
# Configuration helpers.
# --------------------------------------------------------------------------- #


def _password() -> str | None:
    """Read the configured password. Empty/whitespace counts as unset."""
    raw = os.environ.get("GROK_ORCHESTRA_AUTH_PASSWORD") or ""
    raw = raw.strip()
    return raw or None


def auth_enabled() -> bool:
    """True iff a non-empty password is configured."""
    return _password() is not None


# --------------------------------------------------------------------------- #
# Token format: base64url(json({"u": "default", "e": <unix-exp>})).<sig>
# Sig = base64url(HMAC-SHA256(payload, password)). Stateless, no DB.
# --------------------------------------------------------------------------- #


def _b64e(data: bytes) -> str:
    return urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return urlsafe_b64decode(s + pad)


def create_session_token(user: str = "default") -> str:
    """Return a fresh session token. Caller must set it as a cookie."""
    pw = _password()
    if pw is None:
        raise RuntimeError("create_session_token called with auth disabled")
    payload = {"u": user, "e": int(time.time()) + SESSION_TTL_SECONDS}
    payload_b = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(
        hmac.new(pw.encode("utf-8"), payload_b.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{payload_b}.{sig}"


def verify_session_token(token: str | None) -> bool:
    """Return True iff ``token`` is a current, signed session for the
    active password. False on any parse / signature / expiry failure."""
    if not token:
        return False
    pw = _password()
    if pw is None:
        # Auth disabled — every "session" is implicitly valid.
        return True
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    payload_b, sig = parts
    expected = _b64e(
        hmac.new(pw.encode("utf-8"), payload_b.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, sig):
        return False
    try:
        payload = json.loads(_b64d(payload_b).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    exp = payload.get("e")
    if not isinstance(exp, int) or exp < int(time.time()):
        return False
    return True


# --------------------------------------------------------------------------- #
# FastAPI dependency.
# --------------------------------------------------------------------------- #


def auth_dependency(
    request: Request,
    session: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
) -> None:
    """Raise 401 if auth is on and no valid session/header is present."""
    if not auth_enabled():
        return
    # Allow either the session cookie OR an Authorization: Bearer header.
    # The header is for CLI / curl callers in dev — the cookie is the
    # browser's preferred path.
    if verify_session_token(session):
        return
    header = request.headers.get(AUTH_HEADER_NAME, "")
    if header.startswith("Bearer ") and verify_session_token(header[7:]):
        return
    pw = _password()
    # Allow the Bearer header to also match the raw password — quick
    # for one-off curl checks; never enable in shared environments.
    if pw and header == f"Bearer {pw}":
        return
    raise HTTPException(status_code=401, detail="authentication required")


def ws_auth_ok(ws: WebSocket) -> bool:
    """WebSocket equivalent of ``auth_dependency``. Returns True when
    the connection is allowed, False otherwise; the caller is
    responsible for closing the socket on a False result."""
    if not auth_enabled():
        return True
    cookie = ws.cookies.get(AUTH_COOKIE_NAME)
    if verify_session_token(cookie):
        return True
    header = ws.headers.get(AUTH_HEADER_NAME, "")
    if header.startswith("Bearer ") and verify_session_token(header[7:]):
        return True
    pw = _password()
    if pw and header == f"Bearer {pw}":
        return True
    return False


# --------------------------------------------------------------------------- #
# Routes.
# --------------------------------------------------------------------------- #


def register_auth_routes(app: Any) -> None:
    """Wire ``/api/auth/login``, ``/api/auth/logout``, ``/api/auth/status``.

    The status endpoint is the single source of truth the frontend
    reads to decide whether to render the login page or skip it.
    """

    @app.get("/api/auth/status")
    async def auth_status(request: Request) -> dict[str, Any]:
        if not auth_enabled():
            return {"required": False, "authenticated": True}
        cookie = request.cookies.get(AUTH_COOKIE_NAME)
        return {
            "required": True,
            "authenticated": verify_session_token(cookie),
        }

    @app.post("/api/auth/login")
    async def auth_login(body: LoginBody, request: Request) -> JSONResponse:
        pw = _password()
        if pw is None:
            return JSONResponse({"required": False, "authenticated": True})
        if not hmac.compare_digest(body.password, pw):
            raise HTTPException(status_code=401, detail="invalid password")
        token = create_session_token()
        secure = request.url.scheme == "https"
        resp = JSONResponse({"required": True, "authenticated": True})
        resp.set_cookie(
            key=AUTH_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=SESSION_TTL_SECONDS,
            path="/",
        )
        return resp

    @app.post("/api/auth/logout")
    async def auth_logout() -> JSONResponse:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(AUTH_COOKIE_NAME, path="/")
        return resp


# Re-exported for the dependency form: ``Depends(auth_dep)``.
auth_dep = Depends(auth_dependency)
