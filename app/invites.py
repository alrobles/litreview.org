""""Editorial invitations for LitReview (Fase A).

Security rules (design 2026-09-06-editorial-invitations.md):

- T1: an invitation link NEVER grants admin. Links always invite to the
  'editorial' role; promotion to admin is a separate explicit action.
- T2: the link is bound to an identity — on accept the GitHub account's
  primary email must match the invited email (or the login must match
  expected_login).
- T3: tokens are high-entropy (token_urlsafe(32)), stored ONLY as SHA-256
  hashes, expire (default 7 days), single-use, and accept is rate-limited.

Storage: data/invites.json
    {"invites": [{"id", "email", "role", "expected_login", "token_hash",
                  "created_by", "created_at", "expires_at", "used",
                  "used_by", "used_at"}]}
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from app import staff

INVITE_TTL_DAYS = 7
ROLE_EDITORIAL = staff.ROLE_EDITORIAL


class InviteError(Exception):
    """Raised with a user-facing message for invalid invites."""
    pass


def _invites_path(root: Path) -> Path:
    return root / "data" / "invites.json"


def _load(root: Path) -> list[dict]:
    p = _invites_path(root)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text()).get("invites", [])
    except Exception:
        return []


def _save(root: Path, invites: list[dict]) -> None:
    p = _invites_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"invites": invites}, indent=2, ensure_ascii=False))


def _hash(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_invite(root: Path, email: str, role: str,
                  created_by: str, expected_login: Optional[str] = None,
                  ttl_days: int = INVITE_TTL_DAYS) -> dict:
    """Create an invite. Returns {'token', 'invite'} — token only here."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise InviteError("A valid email is required")
    role = (role or ROLE_EDITORIAL).strip().lower()
    if role != ROLE_EDITORIAL:
        # T1: links NEVER grant admin
        raise InviteError("Invitations can only grant the editorial role")
    if expected_login:
        expected_login = expected_login.strip()
    token = secrets.token_urlsafe(32)
    now = _now_iso()
    invite = {
        "id": "inv_" + secrets.token_hex(4),
        "email": email,
        "role": role,
        "expected_login": expected_login,
        "token_hash": _hash(token),
        "created_by": created_by,
        "created_at": now,
        "expires_at": _now_iso() if ttl_days <= 0 else
                      datetime.fromtimestamp(time.time() + ttl_days * 86400,
                                             tz=timezone.utc).isoformat(),
        "used": False,
        "used_by": None,
        "used_at": None,
    }
    invites = _load(root)
    invites.append(invite)
    _save(root, invites)
    return {"token": token, "invite": invite}


def get_invite_by_token(root: Path, token: str) -> tuple[Optional[dict], Optional[str]]:
    """Resolve a raw token to {invite, hash_match}. Returns (invite, None) if ok."""
    token = (token or "").strip()
    if not token:
        return None, "Missing invite token"
    h = _hash(token)
    for inv in _load(root):
        if inv.get("token_hash") == h:
            return inv, None
    return None, "Invitation not found"


def validate_invite(inv: dict) -> Optional[str]:
    """Return an error string if the invite cannot be accepted, else None."""
    if inv.get("used"):
        return "This invitation has already been used"
    exp = inv.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                return "This invitation has expired"
        except ValueError:
            pass
    return None


def accept_invite(root: Path, token: str, github: dict,
                  rate_ok: bool = True) -> dict:
    """Accept an invite with a verified GitHub identity.

    `github` = session dict {login, email, name, id, provider}.

    Rules:
    - token valid, not used, not expired (T3)
    - identity match: github email == invite.email OR login == expected_login (T2)
    - role is editorial (T1) — always
    Returns {'ok', 'role', 'login'} or raises InviteError.
    """
    inv, err = get_invite_by_token(root, token)
    if err:
        raise InviteError(err)
    assert inv is not None
    if not rate_ok:
        raise InviteError("Too many attempts — try again in a few minutes")
    err = validate_invite(inv)
    if err:
        raise InviteError(err)

    gh_email = (github.get("email") or "").strip().lower()
    gh_login = (github.get("login") or "").strip()
    invite_email = (inv.get("email") or "").strip().lower()
    expected = (inv.get("expected_login") or "").strip().lower()

    # T2: bound identity
    if not (gh_email and gh_email == invite_email) and not (expected and gh_login.lower() == expected):
        raise InviteError(
            "The GitHub account does not match the invitation. "
            "Accept with the GitHub account whose email matches the invite "
            "address (or the expected login).")

    # promote/insert member
    members = staff.load_members(root)
    existing = next((m for m in members if m.get("login") == gh_login), None)
    now = _now_iso()
    if existing:
        # a link NEVER degrades: admin stays admin, only (re)activates
        existing["status"] = "active"
        existing["email"] = existing.get("email") or gh_email
    else:
        members.append({
            "login": gh_login,
            "role": ROLE_EDITORIAL,
            "email": gh_email or None,
            "status": "active",
            "invited_by": inv.get("created_by"),
            "joined_at": now,
        })
    staff.save_members(members, root)

    # mark invite used
    inv["used"] = True
    inv["used_by"] = gh_login
    inv["used_at"] = now
    invites = _load(root)
    for i in invites:
        if i.get("id") == inv.get("id"):
            i.update(inv)
    _save(root, invites)
    return {"ok": True, "role": ROLE_EDITORIAL, "login": gh_login}


def list_invites(root: Path, include_token: bool = False) -> list[dict]:
    """List invites WITHOUT token hashes (safe). Include raw token only if asked."""
    out = []
    for inv in _load(root):
        safe = {k: v for k, v in inv.items() if k not in ("token_hash",)}
        if include_token:
            safe["token"] = inv.get("token_hash")  # never expose raw
        out.append(safe)
    return out