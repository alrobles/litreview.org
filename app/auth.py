"""OAuth for LitReview — digital responsibility signature (GitHub + ORCID).

Flows:
  GET  /auth/login?return_to=/submit.html        -> 302 to GitHub authorize
  GET  /auth/github/callback?code&state          -> exchange, mint session cookie
  GET  /auth/orcid/login?return_to=/submit.html  -> 302 to ORCID authorize
  GET  /auth/orcid/callback?code&state           -> exchange, mint session cookie
  GET  /auth/me                             -> {user} or 401
  POST /auth/logout                         -> clear cookie

Sessions are STATELESS: a signed (HMAC) httpOnly cookie carrying the verified
identity (GitHub or ORCID). No server-side session store. The OAuth `state`
is stored in-memory with a TTL; the callback consumes it once (CSRF).

GitHub uses a DEDICATED OAuth App for litreview.org — isolated from
agenticplug/ecoseek. ORCID uses the standard ORCID public API (/authenticate).
A login proves control of an identity (digital signature), not humanness; a
human-verification survey can be layered on later.
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

GH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GH_TOKEN_URL = "https://github.com/login/oauth/access_token"
GH_USER_URL = "https://api.github.com/user"
GH_SCOPE = "read:user user:email"

# ORCID (public API, scope /authenticate)
ORCID_CLIENT_ID = os.environ.get("ORCID_CLIENT_ID", "")
ORCID_CLIENT_SECRET = os.environ.get("ORCID_CLIENT_SECRET", "")
ORCID_AUTHORIZE_URL = os.environ.get("ORCID_AUTHORIZE_URL", "https://orcid.org/oauth/authorize")
ORCID_TOKEN_URL = os.environ.get("ORCID_TOKEN_URL", "https://orcid.org/oauth/token")
ORCID_PUB_URL = os.environ.get("ORCID_PUB_URL", "https://pub.orcid.org/v3.0")
ORCID_SCOPE = "/authenticate"

# in-memory OAuth state store: state -> {"return_to": str, "exp": ts}
_STATE: dict[str, dict] = {}
_STATE_TTL = 600  # 10 minutes


def oauth_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and SESSION_SECRET)


def orcid_configured() -> bool:
    return bool(ORCID_CLIENT_ID and ORCID_CLIENT_SECRET and SESSION_SECRET)


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
        "provider": user.get("provider", "github"),
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
        "scope": GH_SCOPE,
        "state": state,
        "allow_signup": "true",
    })
    return f"{GH_AUTHORIZE_URL}?{q}"


def build_orcid_authorize_url(state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": ORCID_CLIENT_ID,
        "response_type": "code",
        "scope": ORCID_SCOPE,
        "redirect_uri": f"{BASE_URL}/auth/orcid/callback",
        "state": state,
    })
    return f"{ORCID_AUTHORIZE_URL}?{q}"


def exchange_code(code: str) -> Optional[dict]:
    """Exchange an OAuth code for a GitHub user (token exchange + /user)."""
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": f"{BASE_URL}/auth/github/callback",
    }).encode()
    req = urllib.request.Request(GH_TOKEN_URL, data=data, method="POST",
                                 headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tok = json.loads(resp.read())
    except Exception:
        return None
    if tok.get("error") or not tok.get("access_token"):
        return None
    ureq = urllib.request.Request(GH_USER_URL,
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


def exchange_orcid_code(code: str) -> Optional[dict]:
    """Exchange an ORCID auth code for the ORCID iD + name (public API)."""
    data = urllib.parse.urlencode({
        "client_id": ORCID_CLIENT_ID,
        "client_secret": ORCID_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": f"{BASE_URL}/auth/orcid/callback",
        "scope": ORCID_SCOPE,
    }).encode()
    req = urllib.request.Request(ORCID_TOKEN_URL, data=data, method="POST",
                                 headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tok = json.loads(resp.read())
    except Exception:
        return None
    orcid = tok.get("orcid", "")
    if tok.get("error") or not orcid:
        return None
    # best-effort public email from the public record (scope /authenticate may
    # not include it; that's fine — name + iD are the core identity)
    email = None
    try:
        preq = urllib.request.Request(
            f"{ORCID_PUB_URL}/{orcid}/person",
            headers={"Accept": "application/json",
                     "Authorization": f"Bearer {tok.get('access_token', '')}"})
        with urllib.request.urlopen(preq, timeout=10) as resp:
            person = json.loads(resp.read())
        emails = person.get("emails", {}).get("email", []) or []
        for e in emails:
            if e.get("visibility") == "public" and e.get("email"):
                email = e["email"]
                break
    except Exception:
        pass
    return {
        "login": orcid,
        "id": orcid,
        "name": tok.get("name") or orcid,
        "email": email,
        "avatar_url": None,
        "provider": "orcid",
        "verified_at": time.time(),
    }