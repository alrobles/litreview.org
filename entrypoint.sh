#!/bin/sh
# LitReview v2 — start backend + frontend together.
set -e
# ensure writeable dirs belong to the host user (uid 1000) so the repo
# stays editable on the host; creates .submissions if missing.
mkdir -p /srv/litreview/.submissions
chown -R 1000:1000 /srv/litreview/data /srv/litreview/papers /srv/litreview/.submissions 2>/dev/null || true
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
exec nginx -g 'daemon off;'