# LitReview.org — Deployment Status

## 2026-09-04 — v2: scientist-written, AI-assisted reviews LIVE

**Status: LIVE** — https://litreview.org and https://ai.litreview.org (HTTP 200, TLS OK)

### What changed (v2 refactor)

The site pivoted from auto-generated reviews to **reviews written by
scientists with AI assistance**: authors write the reviews (AI as a drafting,
synthesis, and fact-checking aid), submit them through a public form, and a
moderator approves them before publication. No AI placeholder content is
served.

- **Backend**: FastAPI (`app/main.py`) — public `POST /api/v1/submit`, admin
  queue (`GET /api/v1/admin/submissions`, `GET .../content/{sid}`, `POST
  .../approve/{sid}`, `POST .../reject/{sid}`), rate limit 5/h/IP, pydantic
  validation (content >= 100 chars, abstract >= 20, active areas only).
- **Moderation**: `/admin.html` is served by the API and gated with
  `X-Admin-Token` (env `LITREVIEW_ADMIN_TOKEN`, file
  `~/env/litreview-admin-token`). Admin API rejects unauthenticated/bad-token
  requests with 401.
- **Data model** (`data/reviews.json`): entries now carry `status`
  (published|hidden), `reviewed_by {name,email}`, `version`; legacy AI
  placeholders (2608.00001–00005) were hidden and their `papers/` dirs
  removed. Only the real human review 2608.00006 is published.
- **Frontend**: self-hosted CSS (`static/css/style.css`) + JS — Tailwind CDN
  removed. `submit.html` (public form, live Markdown preview, no JS deps),
  `admin.html` (queue), pages rewritten to the "scientist-written,
  AI-assisted" pitch.
- **Deployment**: single container `litreview-site` (nginx + uvicorn,
  image `litreview-site:v2`); repo is bind-mounted read-write at
  `/srv/litreview`, so approvals write straight into the working tree (commit +
  push keeps GitHub in sync). Port unchanged: 127.0.0.1:8670.

### Verified (2026-09-04)

- E2E: submit → pending → approve → assigned id 2609.00001 → rendered
  `papers/<id>/index.html` + `main.md` → visible in public reviews.json.
  Test artifacts then removed (site shows only real content).
- Security: admin endpoints return 401 without/with bad token; malformed
  payloads return 422; 6th submission in an hour returns 429.
- Missing static paths return 404 (nginx `try_files ... =404`).
- All routes 200: `/`, `/submit.html`, `/browse.html`, `/about.html`,
  `/admin.html`, `/static/css/style.css`, `/data/reviews.json`,
  `/papers/2608.00006/index.html`.

### DNS / tunnel

- Cloudflare zone litreview.org (e9cd32ad76419bc1dc207037a59ac7ca)
- CNAME litreview.org + ai.litreview.org → tunnel
  154c1f8f-ad87-4dbe-b949-cf8a067dd4f9.cfargotunnel.com (proxied)
- cloudflared.service (systemd) routes both → 127.0.0.1:8670

### Rollback

Previous image with static nginx-only v1 is superseded; rebuild v2 from the
repo (`docker build -t litreview-site:v2 .`) at any time. DNS/ingress
unchanged from v1.