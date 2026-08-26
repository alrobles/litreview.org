# litreview.org — Design

**Date:** 2026-08-25
**Status:** Approved
**Domain:** ai.litreview.org (site) · litreview.org (apex)
**Repo:** alrobles/litreview.org

## Purpose

An arXiv-style repository of AI-generated literature reviews for basic
sciences. Launching with **Ecology & Evolution**; **Physics** planned next.
Reviews are organized by area and served in three formats per paper:
LaTeX source, PDF, and HTML (like arXiv's abstract page).

## Stack

Static HTML/CSS/JS, modeled on the xbioclim.org template:

- Tailwind via CDN, dark/light mode toggle
- Plain multipage HTML: `index.html`, `browse.html`, `about.html`
- `abs.html?id=<ID>` renders the abstract page from `data/reviews.json`
- No build step; deployable with nginx in Docker behind Cloudflare Tunnel
  (deployment is out of scope for this iteration)

## Identifier scheme

arXiv-style `YYMM.NNNNN`, e.g. `2608.00001`.

- Abstract page: `/abs.html?id=2608.00001`
- Paper files: `/papers/2608.00001/main.tex`, `/papers/2608.00001/main.pdf`,
  `/papers/2608.00001/index.html` (standalone HTML rendering)
- Sortable by date; area shown as metadata, not encoded in the ID.

## Data model

Single index file `data/reviews.json`:

```json
{
  "id": "2608.00001",
  "title": "...",
  "authors": ["..."],
  "area": "ecology-evolution",
  "abstract": "...",
  "date": "2026-08-25",
  "ai_model": "...",
  "keywords": ["..."]
}
```

Areas (initial): `ecology-evolution`. Planned: `physics`.

## Initial content (placeholders)

5 placeholder reviews in Ecology & Evolution, each with real compilable
LaTeX (`main.tex`), a compiled PDF (`pdflatex`), and standalone HTML
(pandoc), plus entries in `data/reviews.json`.

## Pages

| Page | Content |
|---|---|
| `index.html` | Hero + recent listings |
| `browse.html` | Full listing, filter by area |
| `abs.html` | arXiv-like abstract page w/ format links (PDF, HTML, LaTeX) |
| `about.html` | Mission, how reviews are generated, submission policy |

## Future / out of scope

- Docker + nginx deployment and Cloudflare Tunnel for ai.litreview.org
- Real review ingestion pipeline (AI generation workflow)
- Additional areas (physics), search, citations export
