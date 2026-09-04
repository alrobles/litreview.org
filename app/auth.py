"""GitHub OAuth for LitReview — digital responsibility signature.

Flows:
  GET  /auth/login?return_to=/submit.html   -> 302 to GitHub authorize
  GET  /auth/github/callback?code&state     -> exchange, mint session cookie
  GET  /auth/me                             -> {user} or 401
  POST /auth/logout                         -> clear cookie

Sessions are STATELESS: a signed (HMAC) httpOnly cookie carrying the verified
GitHub identity. No server-side session store. The OAuth `state` is stored
in-memory with a TTL; the callback consumes it once (CSRF protection).

This uses a DEDICATED GitHub OAuth App for litreview.org — intentionally
isolated from the agenticplug/ecoseek OAuth app. A login here proves control
of a GitHub account (digital signature), not humanness; a human-verification
survey can be layered on later without changing this module.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

# ---------- config (env) ----------
CLIENT_ID = os.environ.get("GITHUB_OAUTH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "")
BASE_URL = os.environ.get("LITREVIEW_BASE_URL", "https://litreview.org").rstrip("/")
SESSION_SECRET = os.environ.get("LITREVIEW_SESSION_SECRET", "")
SESSION_TTL = int(os.environ.get("LITREVIEW_SESSION_TTL", str(7 * 86400)))  # 7 days
COOKIE_NAME = "litreview_session"

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
SCOPE = "read:user user:email"

# in-memory OAuth state store: state -> {"return_to": str, "exp": ts}
_STATE: dict[str, dict] = {}
_STATE_TTL = 600  # 10 minutes


def oauth_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and SESSION_SECRET)


# ---------- state (CSRF) ----------
def put_state(return_to: Optional[str]) -> str:
    state = secrets.token_hex(32)
    _STATE[state] = {"return_to": return_to or "/submit.html", "exp": time.time() + _STATE_TTL}
    return state


def take_state(state: str) -> Optional[str]:
    """Consume a state once; returns return_to or None if unknown/expired."""
    payload = _STATE.pop(state, None)
    if not payload:
        return None
    if payload["exp"] < time.time():
        return None
    return payload["return_to"]


# ---------- session cookie (signed, stateless) ----------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()


def mint_session(user: dict) -> str:
    """Create a signed cookie value carrying the verified GitHub identity."""
    body = {
        "login": user.get("login", ""),
        "id": str(user.get("id", "")),
        "name": user.get("name"),
        "email": user.get("email"),
        "avatar": user.get("avatar_url"),
        "exp": int(time.time()) + SESSION_TTL,
    }
    payload = _b64(json.dumps(body, ensure_ascii=False).encode())
    return f"{payload}.{_sign(payload)}"


def read_session(cookie: str) -> Optional[dict]:
    """Verify and decode a session cookie; None if invalid/expired."""
    if not cookie or "." not in cookie:
        return None
    payload_b64, sig = cookie.rsplit(".", 1)
    expected = _sign(payload_b64)
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        body = json.loads(_unb64(payload_b64).decode())
    except Exception:
        return None
    if body.get("exp", 0) < time.time():
        return None
    return body


def session_cookie_header(value: str, secure: bool = True) -> str:
    parts = [f"{COOKIE_NAME}={value}", "HttpOnly", "Path=/", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    parts.append(f"Max-Age={SESSION_TTL}")
    return "; ".join(parts)


def clear_cookie_header(secure: bool = True) -> str:
    parts = [f"{COOKIE_NAME}=", "HttpOnly", "Path=/", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    parts.append("Max-Age=0")
    return "; ".join(parts)


# ---------- GitHub API ----------
def build_authorize_url(state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": f"{BASE_URL}/auth/github/callback",
        "scope": SCOPE,
        "state": state,
        "allow_signup": "true",
    })
    return f"{AUTHORIZE_URL}?{q}"


def exchange_code(code: str) -> Optional[dict]:
    """Exchange an OAuth code for a GitHub user (token exchange + /user)."""
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": f"{BASE_URL}/auth/github/callback",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST",
                                 headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tok = json.loads(resp.read())
    except Exception:
        return None
    if tok.get("error") or not tok.get("access_token"):
        return None
    ureq = urllib.request.Request(USER_URL,
                                  headers={"Authorization": f"Bearer {tok['access_token']}",
                                           "Accept": "application/vnd.github+json",
                                           "User-Agent": "litreview-broker"})
    try:
        with urllib.request.urlopen(ureq, timeout=15) as resp:
            user = json.loads(resp.read())
    except Exception:
        return None
    if not user.get("id") or not user.get("login"):
        return None
    return {
        "login": user["login"],
        "id": str(user["id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "avatar_url": user.get("avatar_url"),
        "provider": "github",
        "verified_at": time.time(),
    }