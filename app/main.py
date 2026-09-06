#!/usr/bin/env python3
"""LitReview v2 — scientist-written, AI-assisted literature reviews.

Backend: public submission intake + admin moderation queue.
Writes approved reviews straight into the repo (bind-mounted), so nginx
serves them immediately without a rebuild.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import uuid
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import BackgroundTasks
from fastapi.responses import RedirectResponse
from app import auth
from app import staff
from app.screening import run_screening, sanitize_html

import markdown as md
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from markupsafe import escape
from pydantic import BaseModel, EmailStr, Field, field_validator
from urllib.parse import quote

ROOT = Path(os.environ.get("LITREVIEW_ROOT", "/srv/litreview"))
DATA_FILE = ROOT / "data" / "reviews.json"
SUBMISSIONS_DIR = ROOT / ".submissions"
ADMIN_TOKEN = os.environ.get("LITREVIEW_ADMIN_TOKEN", "")

ID_RE = re.compile(r"^\d{4}\.\d{5}$")
DOMAIN = "litreview.org"

app = FastAPI(title="LitReview API", docs_url=None, redoc_url=None)

# ---------- rate limiting (in-memory, per IP) ----------
RATE_LIMIT = defaultdict(deque)  # ip -> deque of unix timestamps
MAX_SUBMISSIONS = 5              # per hour per IP
RATE_WINDOW = 3600

def rate_limited(ip: str):
    now = time.time()
    q = RATE_LIMIT[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= MAX_SUBMISSIONS:
        raise HTTPException(429, "Too many submissions from this IP. Please try again later.")
    q.append(now)

def check_admin(x_admin_token: Optional[str] = Header(None),
                request: Request | None = None) -> dict:
    """Resolve staff identity: legacy token OR GitHub session. Returns {role}.

    - Static token (X-Admin-Token == LITREVIEW_ADMIN_TOKEN) -> role 'admin'.
    - GitHub OAuth session cookie -> role from data/admins.json
      (admins[] = 'admin', editorial[] = 'editorial').
    Raises 401 if neither is valid staff.
    """
    # 1) legacy static token (emergency credential)
    if x_admin_token and ADMIN_TOKEN and secrets.compare_digest(x_admin_token, ADMIN_TOKEN):
        return {"role": "admin", "via": "token"}
    # 2) GitHub session identity
    if request is not None:
        sess = auth.read_session(request.cookies.get(auth.COOKIE_NAME, ""))
        if sess:
            role = staff.role_for_login(sess.get("login", ""), ROOT)
            if role:
                return {"role": role, "via": "github", "login": sess.get("login")}
    raise HTTPException(401, "Admin credentials required")


def require_admin(identity: dict) -> None:
    """Gate a decision endpoint: only the 'admin' role may pass."""
    if not identity or identity.get("role") != "admin":
        raise HTTPException(403, "Admin role required for this action")

# ---------- models ----------
class Submission(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    authors: str = Field(min_length=2, max_length=500)   # comma-separated
    area: str = Field(min_length=3, max_length=50)
    abstract: str = Field(min_length=20, max_length=4000)
    keywords: str = Field(default="", max_length=500)    # comma-separated
    ai_assist: str = Field(default="", max_length=1000)  # AI tools used (declaration)
    content: str = Field(min_length=100, max_length=120000)
    format: Literal["markdown", "latex"] = "markdown"
    contact_name: str = Field(min_length=2, max_length=200)
    contact_email: EmailStr
    publish_score: bool = False

    @field_validator("area")
    def area_must_exist(cls, v):
        data = _load_data()
        if not any(a["id"] == v and a["status"] == "active" for a in data["areas"]):
            raise ValueError(f"Unknown or inactive area: {v}")
        return v

# ---------- helpers ----------
def _load_data() -> dict:
    with open(DATA_FILE) as f:
        return json.load(f)

def _save_data(data: dict):
    tmp = DATA_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(DATA_FILE)

def _next_id(data: dict) -> str:
    """Next arXiv-style YYMM.NNNNN id, skipping existing ones."""
    yymm = datetime.now().strftime("%y%m")
    existing = {r["id"] for r in data["reviews"]}
    for i in range(1, 20000):
        cand = f"{yymm}.{i:05d}"
        if cand not in existing:
            return cand
    raise RuntimeError("ID space exhausted")

def _markdown_to_html(text: str) -> str:
    """Render markdown to safe HTML for a review page."""
    return md.markdown(text, extensions=["extra", "sane_lists", "nl2br"])


def _compile_latex(workdir: Path) -> tuple[bool, str]:
    """Compile main.tex -> main.pdf with pdflatex (two passes for refs)."""
    try:
        r = None
        for _ in range(2):
            r = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                 "-no-shell-escape", "-output-directory", str(workdir), "main.tex"],
                cwd=workdir, capture_output=True, text=True, timeout=180)
        pdf = workdir / "main.pdf"
        if r is None or r.returncode != 0 or not pdf.exists():
            log = workdir / "main.log"
            tail = ""
            if log.exists():
                lines = [ln for ln in log.read_text(errors="replace").splitlines() if ln.strip()]
                tail = "\n".join(lines[-12:])
            return False, tail or "pdflatex failed (no log)"
        for junk in ("aux", "log", "out"):
            (workdir / f"main.{junk}").unlink(missing_ok=True)
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "pdflatex timed out after 180s"
    except FileNotFoundError:
        return False, "pdflatex not found in container"


def _latex_to_html(tex: str) -> str:
    """Convert LaTeX source to an HTML fragment (math stays as MathJax delimiters)."""
    try:
        r = subprocess.run(
            ["pandoc", "-f", "latex", "-t", "html5", "--mathjax", "--wrap=none"],
            input=tex, capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and r.stdout.strip():
            return _number_citations(r.stdout, tex)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return f"<pre>{escape(tex)}</pre>"


def _number_citations(html: str, tex: str) -> str:
    """Replace pandoc's empty citation spans with [n] numbers.

    pandoc keeps inline thebibliography items but renders \\cite as empty
    spans when no citeproc engine runs; number them by \\bibitem order.
    """
    keys = re.findall(r"\\bibitem\{([^}]+)\}", tex)
    idx = {k: i + 1 for i, k in enumerate(keys)}

    def repl(m: re.Match) -> str:
        cites = re.split(r"[\s,]+", m.group(1))
        nums = ", ".join(str(idx.get(k, "?")) for k in cites if k)
        return f"<sup class=\"cite-num\">[{nums}]</sup>"

    return re.sub(r'<span class="citation" data-cites="([^"]+)"></span>', repl, html)

def _submission_dir(sid: str) -> Path:
    d = SUBMISSIONS_DIR / sid
    if not d.is_dir():
        raise HTTPException(404, "Submission not found")
    return d

def _read_payload(sid: str) -> dict:
    with open(_submission_dir(sid) / "payload.json") as f:
        return json.load(f)


def _read_screening(sid: str) -> Optional[dict]:
    f = _submission_dir(sid) / "screening.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def _reject_auto(sid: str, reason: str):
    p = _read_payload(sid)
    p["status"] = "rejected"
    p["rejected_at"] = datetime.now(timezone.utc).isoformat()
    p["rejected_auto"] = True
    p["reject_reason"] = reason
    (SUBMISSIONS_DIR / sid / "payload.json").write_text(
        json.dumps(p, indent=2, ensure_ascii=False))

# ---------- public API ----------
@app.get("/auth/login")
async def auth_login(return_to: str = "/submit.html"):
    if not auth.oauth_configured():
        raise HTTPException(503, "OAuth is not configured on this server")
    state = auth.put_state(return_to)
    return RedirectResponse(auth.build_authorize_url(state))


@app.get("/auth/github/callback")
async def auth_callback(code: str = "", state: str = ""):
    if not auth.oauth_configured():
        raise HTTPException(503, "OAuth is not configured on this server")
    if not code or not state:
        raise HTTPException(400, "Missing code or state")
    return_to = auth.take_state(state)
    if return_to is None:
        raise HTTPException(400, "Invalid or expired state")
    user = auth.exchange_code(code)
    if user is None:
        raise HTTPException(502, "GitHub OAuth exchange failed")
    cookie = auth.mint_session(user)
    resp = RedirectResponse(return_to or "/submit.html")
    # Secure cookie in production (https); allow http only for local dev
    resp.headers["Set-Cookie"] = auth.session_cookie_header(
        cookie, secure=os.environ.get("LITREVIEW_DEV_HTTP", "") != "1")
    return resp


@app.get("/auth/orcid/login")
async def auth_orcid_login(return_to: str = "/submit.html"):
    if not auth.orcid_configured():
        raise HTTPException(503, "ORCID OAuth is not configured on this server")
    state = auth.put_state(return_to)
    return RedirectResponse(auth.build_orcid_authorize_url(state))


@app.get("/auth/orcid/callback")
async def auth_orcid_callback(code: str = "", state: str = ""):
    if not auth.orcid_configured():
        raise HTTPException(503, "ORCID OAuth is not configured on this server")
    if not code or not state:
        raise HTTPException(400, "Missing code or state")
    return_to = auth.take_state(state)
    if return_to is None:
        raise HTTPException(400, "Invalid or expired state")
    user = auth.exchange_orcid_code(code)
    if user is None:
        raise HTTPException(502, "ORCID OAuth exchange failed")
    cookie = auth.mint_session(user)
    resp = RedirectResponse(return_to or "/submit.html")
    resp.headers["Set-Cookie"] = auth.session_cookie_header(
        cookie, secure=os.environ.get("LITREVIEW_DEV_HTTP", "") != "1")
    return resp


@app.get("/auth/providers")
async def auth_providers():
    """Which OAuth providers are configured (public, no redirect)."""
    return {"github": auth.oauth_configured(), "orcid": auth.orcid_configured()}


@app.get("/auth/me")
async def auth_me(request: Request):
    sess = auth.read_session(request.cookies.get(auth.COOKIE_NAME, ""))
    if sess is None:
        raise HTTPException(401, "Not logged in")
    return {"user": sess}


@app.post("/auth/logout")
async def auth_logout():
    resp = JSONResponse({"ok": True})
    resp.headers["Set-Cookie"] = auth.clear_cookie_header(
        secure=os.environ.get("LITREVIEW_DEV_HTTP", "") != "1")
    return resp


@app.post("/api/v1/submit")
async def submit(request: Request, sub: Submission, background_tasks: BackgroundTasks):
    sess = auth.read_session(request.cookies.get(auth.COOKIE_NAME, ""))
    if sess is None:
        raise HTTPException(401, "Login required — authenticate with GitHub before submitting")
    rate_limited(request.client.host if request.client else "?")
    sid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    d = SUBMISSIONS_DIR / sid
    d.mkdir(parents=True, exist_ok=False)
    payload = {
        "sid": sid,
        "submitted_by": sess,
        "title": sub.title,
        "authors": [a.strip() for a in sub.authors.split(",") if a.strip()],
        "area": sub.area,
        "abstract": sub.abstract,
        "keywords": [k.strip() for k in sub.keywords.split(",") if k.strip()],
        "ai_assist": sub.ai_assist.strip(),
        "content": sub.content,
        "format": sub.format,
        "contact_name": sub.contact_name,
        "contact_email": sub.contact_email,
        "publish_score": sub.publish_score,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    (d / "payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    (d / ("content.tex" if sub.format == "latex" else "content.md")).write_text(sub.content)
    background_tasks.add_task(run_screening, sid, ROOT)
    return {"ok": True, "sid": sid, "message": "Review submitted. It will appear after moderation."}

# ---------- admin API ----------
@app.get("/admin.html", response_class=HTMLResponse)
async def admin_page():
    f = ROOT / "admin.html"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)

@app.get("/api/v1/admin/whoami")
async def admin_whoami(x_admin_token: Optional[str] = Header(None),
                       request: Request = None):
    """Return the current staff identity (role/via/login) or 401."""
    identity = check_admin(x_admin_token, request)
    return {"ok": True, **identity}

@app.get("/api/v1/admin/submissions")
async def list_submissions(x_admin_token: Optional[str] = Header(None),
                           request: Request = None):
    check_admin(x_admin_token, request)
    out = []
    for d in sorted(SUBMISSIONS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        try:
            p = json.loads((d / "payload.json").read_text())
        except Exception:
            continue
        p.pop("content", None)
        scr = _read_screening(p["sid"])
        if scr is not None:
            p["screening"] = {
                "verdict": scr.get("overall", "review"),
                "security": scr.get("security"),
                "soft_quality": scr.get("soft_quality"),
                "score": scr.get("score"),
                "flags": scr.get("overall"),
            }
        out.append(p)
    return {"submissions": out}

@app.get("/api/v1/admin/content/{sid}")
async def submission_content(sid: str, x_admin_token: Optional[str] = Header(None),
                             request: Request = None):
    check_admin(x_admin_token, request)
    if not re.fullmatch(r"[\w-]+", sid):
        raise HTTPException(400, "Bad sid")
    p = _read_payload(sid)
    f = _submission_dir(sid) / ("content.tex" if p.get("format") == "latex" else "content.md")
    if not f.exists():
        raise HTTPException(404, "No content")
    return Response(f.read_text(), media_type="text/plain")

@app.post("/api/v1/admin/screening/{sid}")
async def rerun_screening(sid: str, x_admin_token: Optional[str] = Header(None),
                           request: Request = None):
    check_admin(x_admin_token, request)
    if not re.fullmatch(r"[\w-]+", sid):
        raise HTTPException(400, "Bad sid")
    p = _read_payload(sid)
    if p.get("status") != "pending":
        raise HTTPException(409, f"Submission is {p.get('status')}")
    result = run_screening(sid, ROOT)
    return {"ok": True, "screening": result}


@app.post("/api/v1/admin/approve/{sid}")
async def approve(sid: str, x_admin_token: Optional[str] = Header(None),
                  request: Request = None):
    identity = check_admin(x_admin_token, request)
    require_admin(identity)
    if not re.fullmatch(r"[\w-]+", sid):
        raise HTTPException(400, "Bad sid")
    p = _read_payload(sid)
    if p.get("status") != "pending":
        raise HTTPException(409, f"Submission is {p.get('status')}")

    # screening gate: never approve something that fails security or high-conf spam
    scr = _read_screening(sid)
    if scr is None:
        # screening may still be running; surface it, don't block permanently
        raise HTTPException(409, "Screening still running — try again in a few seconds.")
    overall = scr.get("overall")
    if overall == "reject_blocked_security":
        raise HTTPException(400, "Blocked: submission failed the security check (" +
                            ", ".join(scr["security"]["flags"]) + ").")
    if overall == "reject_blocked_spam":
        raise HTTPException(400, "Blocked: submission flagged as spam with high confidence.")

    data = _load_data()
    rid = _next_id(data)
    area = next((a for a in data["areas"] if a["id"] == p["area"]), None)
    if area is None:
        raise HTTPException(400, "Area no longer active")

    entry = {
        "id": rid,
        "title": p["title"],
        "authors": p["authors"],
        "area": p["area"],
        "abstract": p["abstract"],
        "keywords": p["keywords"],
        "ai_assist": p.get("ai_assist", ""),
        "impact_index": scr.get("score", {}).get("impact_index", {}),
        "score_model": scr.get("score", {}).get("model", ""),
        "score_public": bool(p.get("publish_score", False)),
        "screening": {
            "verdict": scr.get("overall", "ok"),
            "security": scr.get("security", {}).get("verdict", "ok"),
            "soft_quality": scr.get("soft_quality", {}).get("scores", {}),
            "red_flags": scr.get("score", {}).get("red_flags", []),
            "one_line": scr.get("score", {}).get("one_line", ""),
        },
        "date": date.today().isoformat(),
        "status": "published",
        "reviewed_by": {"name": p["contact_name"], "email": p["contact_email"]},
        "version": 1,
    }
    data["reviews"].append(entry)
    data["reviews"].sort(key=lambda r: r["id"], reverse=True)

    # content: source (markdown or latex) + rendered HTML page (+ PDF for latex)
    papers_dir = ROOT / "papers" / rid
    papers_dir.mkdir(parents=True, exist_ok=False)
    fmt = p.get("format", "markdown")
    if fmt == "latex":
        (papers_dir / "main.tex").write_text(p["content"])
        ok, err = _compile_latex(papers_dir)
        if not ok:
            shutil.rmtree(papers_dir, ignore_errors=True)
            raise HTTPException(400, f"LaTeX compilation failed — fix the source and resubmit:\n{err[:400]}")
        body_html = _latex_to_html(p["content"])
    else:
        (papers_dir / "main.md").write_text(p["content"])
        body_html = _markdown_to_html(p["content"])
    html = _render_review_page(entry, sanitize_html(body_html), fmt)
    (papers_dir / "index.html").write_text(html)

    _save_data(data)
    p["status"] = "published"
    p["published_id"] = rid
    p["published_at"] = datetime.now(timezone.utc).isoformat()
    p["reviewed_by"] = entry.get("reviewed_by", {})
    (SUBMISSIONS_DIR / sid / "payload.json").write_text(
        json.dumps(p, indent=2, ensure_ascii=False))
    # notificar al autor (no bloqueante: la moderación no depende del email)
    from app.email import notify_auth_decision
    notify_auth_decision("accepted", p, rid, report=scr.get("score", {}))
    return {"ok": True, "id": rid, "url": f"/abs.html?id={rid}"}

@app.post("/api/v1/admin/reject/{sid}")
async def reject(sid: str, x_admin_token: Optional[str] = Header(None),
                 request: Request = None):
    identity = check_admin(x_admin_token, request)
    require_admin(identity)
    if not re.fullmatch(r"[\w-]+", sid):
        raise HTTPException(400, "Bad sid")
    p = _read_payload(sid)
    p["status"] = "rejected"
    p["rejected_at"] = datetime.now(timezone.utc).isoformat()
    (SUBMISSIONS_DIR / sid / "payload.json").write_text(
        json.dumps(p, indent=2, ensure_ascii=False))
    # notificar al autor (no bloqueante); incluye el reporte del revisor AI
    from app.email import notify_auth_decision
    _scr = _read_screening(sid) or {}
    notify_auth_decision("rejected", p, report=_scr.get("score", {}))
    return {"ok": True, "sid": sid, "status": "rejected"}

@app.get("/healthz")
async def health():
    return {"ok": True, "root": str(ROOT)}

# ---------- review page rendering ----------
_REVIEW_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>[{rid}] {title} — LitReview</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{abstract}">
<link rel="stylesheet" href="/static/css/style.css">
<!-- citation metadata (Google Scholar, Zotero, semantic scholar) -->
<meta name="citation_title" content="{title}">
{citation_authors}
<meta name="citation_publication_date" content="{date}">
<meta name="citation_online_date" content="{date}">
<meta name="citation_id" content="LitReview:{rid}">
<meta name="citation_language" content="en">
<meta name="citation_abstract" content="{abstract}">
{citation_keywords}
{citation_pdf}
<script type="application/ld+json">{jsonld}</script>
</head>
<body class="page-review">
<nav class="nav">
  <a href="/" class="nav-brand"><span>Lit</span>Review</a>
  <div class="nav-links">
    <a href="/browse.html">Browse</a>
    <a href="/submit.html">Submit</a>
    <a href="/about.html">About</a>
  </div>
</nav>
<main class="container narrow prose">
  <p class="meta-sm"><a href="/browse.html">&larr; All reviews</a></p>
  <p class="area-badge">{area}</p>
  <h1>{title}</h1>
  <p class="authors">{authors}</p>
  <p class="meta-sm">{rid} &middot; Published {date} &middot; Reviewed by {reviewer}</p>
  <p class="meta-sm">AI assistance: <strong>{ai_assist}</strong> &middot; License: <a href="https://creativecommons.org/licenses/by/4.0/" rel="license" target="_blank" rel="noopener">CC BY 4.0</a></p>
  <p class="meta-sm">How to cite: <em>{citation_text}</em></p>
  {coins}
  <hr>
  {body}
  <hr>
  <p class="meta-sm">{source_links} &middot;
  Report an issue: <a href="mailto:{contact}">contact</a></p>
</main>
<footer class="footer">LitReview © 2026 &middot; Citable literature reviews written with AI assistance &middot; CC BY 4.0</footer>
<script id="MathJax-script" async src="/static/vendor/mathjax/tex-svg.js"></script>
</body>
</html>"""


def _render_review_page(entry: dict, body_html: str, fmt: str = "markdown") -> str:
    """Render the full HTML page for an approved review.

    Includes machine-readable citation metadata (citation_* meta tags for
    Google Scholar, JSON-LD ScholarlyArticle, and COinS for Zotero/Reference
    Manager), a visible AI-assistance disclosure, and the CC BY 4.0 license.
    """
    area = entry["area"].replace("-", " & ").title()
    authors = entry["authors"]
    esc_authors = [escape(a) for a in authors]
    kw = entry.get("keywords", []) or []
    citation_authors = "".join(
        f'<meta name="citation_author" content="{escape(a)}">' for a in authors)
    citation_keywords = "".join(
        f'<meta name="citation_keywords" content="{escape(k)}">' for k in kw)
    coins = "&".join([
        "ctx_ver=Z39.88-2004",
        "rft_val_fmt=info:ofi/fmt:kev:mtx:dc",
        "rft.type=preprint",
        "rft.title=" + quote(entry["title"]),
        "rft.creator=" + quote("; ".join(authors)),
        "rft.date=" + entry.get("date", ""),
        "rft.identifier=" + quote(f"LitReview:{entry['id']}"),
    ])
    jsonld = {
        "@context": "https://schema.org",
        "@type": "ScholarlyArticle",
        "headline": entry["title"],
        "identifier": f"LitReview:{entry['id']}",
        "datePublished": entry.get("date", ""),
        "author": [{"@type": "Person", "name": a} for a in authors],
        "abstract": entry.get("abstract", ""),
        "isPartOf": {"@type": "Periodical", "name": "LitReview"},
        "publisher": {"@type": "Organization", "name": "LitReview"},
        "license": "https://creativecommons.org/licenses/by/4.0/",
    }
    ai = (entry.get("ai_assist") or "").strip()
    ai_display = escape(ai) if ai else "None declared — written without AI tools"
    citation_text = (
        f'{escape(entry["id"])} (LitReview, {escape(entry.get("date", ""))}). '
        f'{escape(entry["title"])}. ' + "; ".join(esc_authors) + "."
    )
    if fmt == "latex":
        source_links = (f'Source: <a href="/papers/{entry["id"]}/main.tex">main.tex</a>'
                        f' &middot; <a href="/papers/{entry["id"]}/main.pdf">PDF</a>')
        citation_pdf = (f'<meta name="citation_pdf_url" content="https://{DOMAIN}'
                        f'/papers/{entry["id"]}/main.pdf">')
    else:
        source_links = f'Source: <a href="/papers/{entry["id"]}/main.md">main.md</a>'
        citation_pdf = ""
    return _REVIEW_TEMPLATE.format(
        rid=escape(entry["id"]),
        title=escape(entry["title"]),
        abstract=escape(entry.get("abstract", ""))[:300],
        area=escape(area),
        authors=", ".join(esc_authors),
        citation_authors=citation_authors,
        citation_keywords=citation_keywords,
        date=escape(entry.get("date", "")),
        reviewer=escape(entry.get("reviewed_by", {}).get("name", "")),
        body=body_html,
        contact=escape(entry.get("reviewed_by", {}).get("email", "")),
        ai_assist=ai_display,
        citation_text=citation_text,
        coins=f'<span class="Z3988" title="{coins}" aria-hidden="true"></span>',
        jsonld=json.dumps(jsonld, ensure_ascii=False),
        source_links=source_links,
        citation_pdf=citation_pdf,
    )