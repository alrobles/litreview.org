# litreview.org — Estado del despliegue (2026-09-04)

## ✅ LIVE — sitio publicado

- **ai.litreview.org** → HTTP 200 (TLS OK), sirviendo desde el tunnel reumanlab-agentic
- **litreview.org** (apex) → HTTP 200 (TLS OK)
- Verificado: `/` (título correcto, carga reviews.json), `/data/reviews.json`
  (6 reviews, 3 áreas), `/papers/2608.00006/main.pdf` (186 KB, 200)

## Cronología

- **2026-08-26**: sitio construido + Docker (`litreview-site`, 127.0.0.1:8670) +
  ingress del tunnel añadido. BLOQUEO: sin token DNS para la zona litreview.org.
- **2026-09-04**: Angel creó `~/env/litreview-dns-token` (DNS Edit, zona litreview.org).
  1. Verificado token (`/user/tokens/verify` → active) y zona visible
     (id=e9cd32ad76419bc1dc207037a59ac7ca).
  2. Creados 2 CNAME → `154c1f8f-ad87-4dbe-b949-cf8a067dd4f9.cfargotunnel.com`,
     proxied, ttl=1:
     - `ai.litreview.org` (id=c6459cf170a8315e3bcfff3690ace5ba)
     - `litreview.org` apex (id=d31da3c3722caf9fc2db8eab38a3e95a)
  3. Ingress ya estaba en `/etc/cloudflared/config.yml` (líneas 29-32) y el
     servicio systemd `cloudflared.service` lo servía desde el 25-ago — sin
     restart necesario.
  4. TLS provisionado en minutos. dig → 104.21.77.85 / 172.67.205.191.

## Datos clave

- Tunnel: reumanlab-agentic = `154c1f8f-ad87-4dbe-b949-cf8a067dd4f9`
- Zona litreview.org ID: `e9cd32ad76419bc1dc207037a59ac7ca`
- Token DNS: `~/env/litreview-dns-token` (solo DNS Edit litreview.org)
- Puerto local: 8670 (contenedor `litreview-site`, --restart unless-stopped)

## Nota

El quick tunnel efímero (`cloudflared-tunnel.sh`, `--url localhost:18789`) es
otro servicio destinado a Devin (ephemeral URL en `~/.cloudflared_url`) y NO
interfiere con el tunnel nombrado del systemd.