""""Staff & roles for the LitReview editorial panel.

Identity resolution for admin endpoints. Two credential paths:

1. Static token (X-Admin-Token header) — the legacy emergency credential
   (LITREVIEW_ADMIN_TOKEN env). Always grants the 'admin' role.
2. GitHub OAuth session (litreview_session cookie) — the modern path.
   The signed session carries the verified GitHub login; we look it up in
   data/admins.json to assign a role:
     - admins[]    -> role 'admin'    (approve / reject / publish)
     - editorial[] -> role 'editorial' (view the queue + screening only)

Roles are stored in data/admins.json (editor-managed, lives in the repo).

This replaces the old token-only gate with a proper structure: the panel
owner (alrobles) authenticates with GitHub; future editors are added to
the editorial list; nothing is shared-secret except the emergency token.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

ROLE_ADMIN = "admin"
ROLE_EDITORIAL = "editorial"


def _load_roles(root: Path) -> dict:
    try:
        data = json.loads((root / "data" / "admins.json").read_text())
    except Exception:
        data = {}
    return data


def role_for_login(login: str, root: Path) -> Optional[str]:
    """Return the role for a GitHub login, or None if not staff."""
    if not login:
        return None
    roles = _load_roles(root)
    if login in roles.get("admins", []):
        return ROLE_ADMIN
    if login in roles.get("editorial", []):
        return ROLE_EDITORIAL
    return None


def staff_list(root: Path) -> dict:
    """Public staff summary (logins by role) — no secrets."""
    roles = _load_roles(root)
    return {
        "admins": roles.get("admins", []),
        "editorial": roles.get("editorial", []),
    }