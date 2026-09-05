#!/bin/bash
# Activa las credenciales ORCID/GitHub en el contenedor litreview-site.
# Lee de ~/env/litreview-orcid-credentials (line1=ClientID, line2=Secret)
# y ~/env/litreview-oauth-credentials (line1=ClientID, line2=Secret).
# Uso: ./activate-oauth.sh [sandbox|prod]   (default: prod)
set -euo pipefail

MODE="${1:-prod}"
REPO=/home/reumanlab/alrobles/litreview.org

get_creds() { # $1=archivo -> imprime "ID SECRET" (primera línea no comentario = ID, segunda = secret)
  local f="$1" vals=()
  while IFS= read -r l; do
    l="${l%%$'\r'}"
    [[ -z "$l" || "$l" == \#* ]] && continue
    vals+=("$l")
  done < "$f"
  if [ "${#vals[@]}" -lt 2 ]; then return 1; fi
  echo "${vals[0]} ${vals[1]}"
}

GH=$(get_creds ~/env/litreview-oauth-credentials || true)
ORCID=$(get_creds ~/env/litreview-orcid-credentials || true)

echo "=== GitHub  credenciales: $([ -n "$GH" ] && echo OK || echo 'NO (opcional, pero submit requiere una sesión)')"
echo "=== ORCID   credenciales: $([ -n "$ORCID" ] && echo OK || echo NO)  [$MODE]"

ARGS=(-d --name litreview-site --restart unless-stopped -p 127.0.0.1:8670:80
  -v "$REPO:/srv/litreview"
  -v "$REPO/nginx.conf:/etc/nginx/conf.d/default.conf"
  -e "LITREVIEW_ADMIN_TOKEN=$(cat ~/env/litreview-admin-token)"
  -e "OPENROUTER_API_KEY=$(cat ~/env/openrouter-key)"
  -e "LITREVIEW_SESSION_SECRET=$(cat ~/env/litreview-session-secret)"
  -e "LITREVIEW_BASE_URL=https://litreview.org"
)

if [ -n "$GH" ]; then
  read -r GHID GHSEC <<< "$GH"
  ARGS+=(-e "GITHUB_OAUTH_CLIENT_ID=$GHID" -e "GITHUB_OAUTH_CLIENT_SECRET=$GHSEC")
fi

if [ -n "$ORCID" ]; then
  read -r ORID ORSEC <<< "$ORCID"
  ARGS+=(-e "ORCID_CLIENT_ID=$ORID" -e "ORCID_CLIENT_SECRET=$ORSEC")
  if [ "$MODE" = "sandbox" ]; then
    ARGS+=(-e "ORCID_AUTHORIZE_URL=https://sandbox.orcid.org/oauth/authorize"
           -e "ORCID_TOKEN_URL=https://sandbox.orcid.org/oauth/token"
           -e "ORCID_PUB_URL=https://pub.sandbox.orcid.org/v3.0")
  fi
fi

docker stop litreview-site 2>/dev/null || true
docker rm litreview-site 2>/dev/null || true
docker run "${ARGS[@]}" litreview-site:v5

sleep 4
echo "=== smoke ==="
echo -n "/auth/orcid/login -> "; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8670/auth/orcid/login
echo -n "/auth/login      -> "; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8670/auth/login