# litreview.org

**litreview.org** — an arXiv-style repository of literature reviews written by
scientists with AI assistance.

## What this is

An open repository of literature reviews **written by scientists with AI
assistance** (AI as drafting, synthesis, and fact-checking aid), curated by a
human moderator. Reviews are not auto-generated. AI use is **declared openly
on every review** — using agentic AI is the norm here, never a disqualifier.
Each review has an arXiv-style identifier (`YYMM.NNNNN`), an abstract page,
machine-readable citation metadata, and is published as standalone HTML plus
Markdown source under the **CC BY 4.0** license.

## Structure

```
├── index.html          # landing + recent reviews
├── browse.html         # full listing, filter by area
├── abs.html            # abstract page (?id=2609.00001)
├── about.html          # mission
├── submit.html         # public submission form
├── admin.html          # moderation queue (token-gated)
├── app/                # FastAPI backend (submit + moderation API)
├── static/             # self-hosted CSS/JS (no CDN)
├── data/reviews.json   # index of all entries
├── .submissions/       # pending submissions (gitignored, not published)
└── papers/
    └── 2609.00001/     # one directory per published review
        ├── main.md     # Markdown source (markdown submissions)
        ├── main.tex    # LaTeX source (latex submissions)
        ├── main.pdf    # compiled PDF (latex submissions)
        └── index.html  # rendered HTML
```

## Adding a review (user flow)

1. A scientist submits a review (written with AI assistance) through `/submit.html` (title, authors, area,
   abstract, keywords, optional `ai_assist` disclosure of AI tools, Markdown body, contact).
2. The submission lands in `.submissions/` as `pending`.
3. A moderator approves or rejects it from `/admin.html` (token-gated).
4. On approval the backend assigns the next `YYMM.NNNNN` id, renders the review
   to `papers/<id>/` (with citation metadata, AI-assistance disclosure, and CC BY 4.0
   license), and updates `data/reviews.json`. Nothing is public until
   then — and nothing is public in the repo until you commit it.

## Formats

Submissions are either **Markdown** or **LaTeX**:

- **Markdown** — rendered to HTML with the `markdown` library.
- **LaTeX** — compiled to `main.pdf` with `pdflatex` (two passes, no shell
  escape) and converted to HTML with `pandoc --mathjax`; math renders via
  self-hosted MathJax (`static/vendor/mathjax/tex-svg.js`).

LaTeX sources must be self-contained (single file): use an inline
`thebibliography` environment instead of `\bibliography{...}`. Compilation is
sandboxed (`-no-shell-escape`, `-halt-on-error`, 180s timeout). A failed
compile blocks approval and the submission stays pending with the compiler
log.

## Moderation

- Admin API: `GET/POST /api/v1/admin/*` with `X-Admin-Token`.
- Token is passed at container start via `LITREVIEW_ADMIN_TOKEN` (local file,
  never committed).
- Rate limit: 5 submissions/hour/IP.

## Development & deployment

Single container: nginx (static + proxy) + uvicorn (API). The repo is
bind-mounted into the container, so approved reviews are written straight into
the working tree — commit and push to keep the public repo in sync.

```
docker build -t litreview-site:v4 .
docker run -d --name litreview-site --restart unless-stopped \
  -p 127.0.0.1:8670:80 \
  -v $(pwd):/srv/litreview \
  -e LITREVIEW_ADMIN_TOKEN="$(cat ~/env/litreview-admin-token)" \
  -e OPENROUTER_API_KEY="$(cat ~/env/openrouter-key)" \
  litreview-site:v4
```

Exposed via Cloudflare Tunnel at `litreview.org` and `ai.litreview.org`.

## Screening & moderation

Every submission is screened automatically in the background after submit
(`app/screening.py`, results in `.submissions/<sid>/screening.json`). The
human moderator remains the only publish gate.

1. **Security** (deterministic, no LLM) — LaTeX submissions are scanned for
   `\write18`, file I/O, path traversal in `\input`/`\includegraphics`,
   dangerous `\href` schemes, and non-whitelisted `\usepackage`; markdown for
   `<script>`, event handlers, and `javascript:`/`data:` URLs. Findings block
   approval (HTTP 400) — an insecure source is never compiled or served.
2. **Soft quality** (heuristics) — lexical diversity, bigram repetition,
   character entropy, word count, spam keywords. High-confidence spam blocks
   approval; borderline cases are flagged for human review.
3. **Scientific impact score** (LLM via OpenRouter, free models) — a 1-10
   impact index (AI-predicted citation potential, like an impact factor for
   THIS paper) with confidence, five rubric sub-scores (originality, rigor,
   clarity, relevance, bibliography), red flags, and a one-line summary.
   Model chain: `minimax/minimax-m3:free` → `nvidia/nemotron-3.5-lightning:free`,
   falling back to heuristic-only screening if the LLM is unavailable. The
   model and latency are stored alongside the score.

On approval, `impact_index`, `score_model`, and the screening summary are
stored in `data/reviews.json` and shown on the abstract page (⭐ badge) and
browse listings. The admin queue shows the full screening panel per
submission with a "re-run screening" button (`POST /api/v1/admin/screening/{sid}`).

The API key is passed via `OPENROUTER_API_KEY` (host file `~/env/openrouter-key`),
never committed. Scores are advisory — they influence the human's decision but
never replace it.

## OAuth — digital responsibility signature (v5)

Submitting a review requires **identity verification** (GitHub or ORCID). The
login is a digital signature: the submitter's verified identity is stored in
the submission (`submitted_by`) and shown to the moderator, making every
submission accountable. It proves control of an identity — not humanness
(a human-verification survey can be layered on later).

- **Providers**:
  - **GitHub** — DEDICATED OAuth App for litreview.org, deliberately isolated
    from the agenticplug/ecoseek app.
  - **ORCID** — standard ORCID public API (`/authenticate` scope, iD + name +
    best-effort public email). Ideal for the scientific-journal trajectory;
    ORCID iDs travel with the author's publication record.
- **Flow** (in `app/auth.py`, stateless signed-cookie sessions):
  `GET /auth/login` or `/auth/orcid/login` → provider authorize →
  `GET /auth/github/callback` or `/auth/orcid/callback` → HMAC-signed httpOnly
  cookie (`litreview_session`, 7d) → `GET /auth/me` / `POST /auth/logout`.
  OAuth `state` is single-use in-memory (CSRF).
- **Gate**: `POST /api/v1/submit` returns 401 without a valid session;
  `payload.json` records `submitted_by` (login, id, name, provider,
  verified_at).
- **Env**: `GITHUB_OAUTH_CLIENT_ID/_SECRET` (host file
  `~/env/litreview-oauth-credentials`), `ORCID_CLIENT_ID/_SECRET` (host file
  `~/env/litreview-orcid-credentials`), `LITREVIEW_SESSION_SECRET` (host file
  `~/env/litreview-session-secret`), `LITREVIEW_BASE_URL=https://litreview.org`.
- nginx proxies `/auth/` to uvicorn (nginx.conf is bind-mounted into the
  container). Without a provider configured, its `/auth/*` returns 503
  (graceful); the submit gate still requires SOME session.

Create the GitHub app at `https://github.com/settings/developers` → OAuth Apps
(name `litreview.org`, callback `https://litreview.org/auth/github/callback`).
Register ORCID public API credentials at
`https://info.orcid.org/register-client-application/` (redirect
`https://litreview.org/auth/orcid/callback`).

## License & caveat

Reviews are written and owned by their named authors; they are published after
curation under **CC BY 4.0** (attribution required). AI assistance is declared
per review; use of AI tools never disqualifies a submission. Verify claims with
the primary literature. See `docs/designs/2026-08-25-litreview-design.md` for
the original design.