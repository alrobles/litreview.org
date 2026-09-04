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
        ├── main.md     # Markdown source
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
docker build -t litreview-site:v2 .
docker run -d --name litreview-site --restart unless-stopped \
  -p 127.0.0.1:8670:80 \
  -v $(pwd):/srv/litreview \
  -e LITREVIEW_ADMIN_TOKEN="$(cat ~/env/litreview-admin-token)" \
  litreview-site:v2
```

Exposed via Cloudflare Tunnel at `litreview.org` and `ai.litreview.org`.

## License & caveat

Reviews are written and owned by their named authors; they are published after
curation under **CC BY 4.0** (attribution required). AI assistance is declared
per review; use of AI tools never disqualifies a submission. Verify claims with
the primary literature. See `docs/designs/2026-08-25-litreview-design.md` for
the original design.