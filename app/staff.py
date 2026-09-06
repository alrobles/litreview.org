""""Staff & roles for the LitReview editorial panel.

Identity resolution for admin endpoints. Two credential paths:

1. Static token (X-Admin-Token header) — the legacy emergency credential
   (LITREVIEW_ADMIN_TOKEN env). Always grants the 'admin' role.
2. GitHub OAuth session (litreview_session cookie) — the modern path.
   The signed session carries the verified GitHub login; we look it up in
   data/staff.json to assign a role.

Roles are stored in data/staff.json (editor-managed, lives in the repo):

    {
      "members": [
        {"login": "alrobles", "role": "admin", "email": "...",
         "status": "active", "invited_by": "bootstrap", ...}
      ]
    }

Back-compat: if only the legacy data/admins.json exists ({admins:[], 
editorial:[]}), it is migrated to staff.json on first read.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

ROLE_ADMIN = "admin"
ROLE_EDITORIAL = "editorial"
ROOT_MARKER = "data"  # marker for finding ROOT in staff files


def _root() -> Path:
    # store under <repo>/data — resolved relative to this file's repo
    here = Path(__file__).resolve()
    # app/staff.py -> repo root is two levels up
    return here.parent.parent


def _staff_path(root: Optional[Path] = None) -> Path:
    return (root or _root()) / "data" / "staff.json"


def _admins_path(root: Optional[Path] = None) -> Path:
    return (root or _root()) / "data" / "admins.json"


def load_members(root: Optional[Path] = None) -> list[dict]:
    """Load active members; migrates legacy admins.json on first run."""
    sp = _staff_path(root)
    if sp.exists():
        try:
            data = json.loads(sp.read_text())
            return data.get("members", [])
        except Exception:
            return []
    # legacy migration
    ap = _admins_path(root)
    members = []
    if ap.exists():
        try:
            old = json.loads(ap.read_text())
        except Exception:
            old = {}
        # keep admins.json untouched (read-only legacy); staff.json is source
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        for login in old.get("admins", []):
            members.append({"login": login, "role": ROLE_ADMIN, "status": "active",
                            "invited_by": "bootstrap", "joined_at": now})
        for login in old.get("editorial", []):
            members.append({"login": login, "role": ROLE_EDITORIAL, "status": "active",
                            "invited_by": "bootstrap", "joined_at": now})
        if members:
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(json.dumps({"members": members}, indent=2, ensure_ascii=False))
    return members


def save_members(members: list[dict], root: Optional[Path] = None) -> None:
    sp = _staff_path(root)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps({"members": members}, indent=2, ensure_ascii=False))


def role_for_login(login: str, root: Optional[Path] = None) -> Optional[str]:
    """Return the role for a GitHub login, or None if not active staff."""
    if not login:
        return None
    for m in load_members(root):
        if m.get("login") == login and m.get("status") == "active":
            return m.get("role") or None
    return None


def staff_list(root: Optional[Path] = None) -> dict:
    """Public staff summary (logins by role) — no secrets."""
    members = load_members(root)
    return {
        "admins": [m["login"] for m in members
                   if m.get("role") == ROLE_ADMIN and m.get("status") == "active"],
        "editorial": [m["login"] for m in members
                      if m.get("role") == ROLE_EDITORIAL and m.get("status") == "active"],
        "members": [
            {"login": m["login"], "role": m.get("role"), "status": m.get("status"),
             "email": m.get("email"), "joined_at": m.get("joined_at"),
             "invited_by": m.get("invited_by")}
            for m in members
        ],
    }