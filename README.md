# litreview.org

**ai.litreview.org** — an arXiv-style repository of AI-generated literature
reviews for the basic sciences, starting with Ecology & Evolution.

## What this is

Each review has an arXiv-style identifier (`YYMM.NNNNN`), an abstract page,
and three distribution formats like arXiv: LaTeX source (`main.tex`),
compiled PDF (`main.pdf`), and standalone HTML (`index.html`).

## Structure

```
├── index.html          # landing + recent submissions
├── browse.html         # full listing, filter by area
├── abs.html            # abstract page (?id=2608.00001)
├── about.html          # mission & methodology
├── data/reviews.json   # single index of all entries
└── papers/
    └── 2608.00001/     # one directory per review
        ├── main.tex    # LaTeX source
        ├── main.pdf    # compiled PDF
        └── index.html  # standalone HTML rendering
```

## Adding a review

1. Create `papers/<YYMM.NNNNN>/` with `main.tex`, compile to `main.pdf`
   (`pdflatex main.tex`) and render `index.html`
   (`pandoc main.tex -s -o index.html`).
2. Add an entry to `data/reviews.json`.
3. Commit and push; the site picks it up automatically (no build step).

## Areas

- Ecology & Evolution — active
- Physics — coming soon

## Deployment

Static site, no build step. Serve with any web server (nginx) and expose at
`ai.litreview.org`. See `docs/designs/2026-08-25-litreview-design.md`.

## License & caveat

Reviews are generated with AI assistance and human curation. Citations within
full texts should be verified against primary literature.
