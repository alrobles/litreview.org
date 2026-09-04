# LitReview v2 — community review intake.
# Runs uvicorn (FastAPI backend, :8000) + nginx (static + proxy :80).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/litreview

# backend deps
COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# backend code
COPY app/ /app/

# nginx: proxy /api + /admin to uvicorn; serve static from bind-mounted repo
RUN rm -f /etc/nginx/conf.d/default.conf \
    && rm -f /etc/nginx/sites-enabled/default
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV LITREVIEW_ROOT=/srv/litreview

EXPOSE 80
CMD ["/entrypoint.sh"]