# litreview.org — Estado del despliegue (2026-08-26 04:35 CDT)

Punto de guardado para continuar mañana.

## ✅ Hecho hoy

1. **Sitio construido** en `~/dev/litreview.org` (repo `alrobles/litreview.org`, rama main):
   - index.html, browse.html, abs.html, about.html (estilo xbioclim, Tailwind CDN, dark mode)
   - data/reviews.json — **6 reviews**, 3 áreas
   - papers/2608.00001–00005: Ecology & Evolution (placeholders tex+pdf+html)
   - **papers/2608.00006**: dLLM survey REAL (Computer Science) — fuente `~/ecoreasoner/docs/dllm-main-v3.tex`, compilado con pdflatex (11 págs) + pandoc HTML
2. **Docker funcionando**: contenedor `litreview-site` en **127.0.0.1:8670** (--restart unless-stopped). nginx.conf corregido (solo bloque server en conf.d). Verificado: /, PDF, JSON → 200.
3. **Ingress del tunnel aplicado**: `/etc/cloudflared/config.yml` tiene ahora:
   - ai.litreview.org → http://127.0.0.1:8670
   - litreview.org → http://127.0.0.1:8670
   (insertados antes del catch-all; `ingress validate` OK; cloudflared reiniciado y active)

## ⚠️ Limpieza hecha

El CLI `cloudflared tunnel route dns` creó 2 CNAME BASURA en la zona equivocada
(ecoseek.org): `ai.litreview.org.ecoseek.org` y `litreview.org.ecoseek.org`.
→ **Ambos ELIMINADOS vía API** (verificado success: true).

## 🔴 Bloqueo actual: falta token DNS para litreview.org

- Token existente `~/env/cloudflare-xbioclim-token`: lista las 3 zonas (ecoseek,
  litreview, xbioclim) pero SOLO tiene DNS Edit en xbioclim.org.
  → Falla con "Authentication error" al crear registros en litreview.org.
- cert.pem (~/.cloudflared): token embebido = solo zona ecoseek.org.

## 📋 Pasos para mañana

1. Angel crea API token en dash.cloudflare.com → My Profile → API Tokens → Create Token:
   - Permission: **Zone → DNS → Edit**
   - Zone Resources: Include → Specific zone → **litreview.org**
   - Guardar el valor en `~/env/cloudflare-litreview-token`
2. Crear los 2 CNAME (con ese token):
   ```bash
   TOK=$(head -1 ~/env/cloudflare-litreview-token | tr -d '\r')
   ZID=e9cd32ad76419bc1dc207037a59ac7ca
   for N in ai litreview.org; do curl -s -X POST \
     -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
     -d "{\"type\":\"CNAME\",\"name\":\"$N\",\"content\":\"154c1f8f-ad87-4dbe-b949-cf8a067dd4f9.cfargotunnel.com\",\"proxied\":true,\"ttl\":1}" \
     "https://api.cloudflare.com/client/v4/zones/$ZID/dns_records"; echo; done
   ```
3. Esperar TLS provisioning (minutos a ~2h; NO tocar el tunnel si da HTTP 000 con connection reset).
4. Verificar:
   - dig +short ai.litreview.org → IPs Cloudflare
   - curl -sk https://ai.litreview.org/ → 200
   - curl -sk https://ai.litreview.org/papers/2608.00006/main.pdf → 200
5. Commit+push de los cambios nuevos (nginx.conf, Dockerfile, dLLM paper, reviews.json) a GitHub.

## Datos clave

- Tunnel: reumanlab-agentic = 154c1f8f-ad87-4dbe-b949-cf8a067dd4f9
- Zona litreview.org ID: e9cd32ad76419bc1dc207037a59ac7ca (status active)
- Account ID: 76b5f6eee77f46d51284e0257f613a23
- Puerto local: 8670
