#!/usr/bin/env sh
set -eu

MB_HOST="${MB_HOST:-$METABASE_HOST}"
MB_PORT="${MB_PORT:-$METABASE_PORT}"
TARGET_DB_PORT="${TARGET_DB_PORT:-5432}"
BASE="http://${MB_HOST}:${MB_PORT}"

echo "Waiting for Metabase at ${BASE}..."
for _ in $(seq 1 120); do
  if curl -sf "${BASE}/api/health" >/dev/null; then
    break
  fi
  sleep 2
done

if ! curl -sf "${BASE}/api/health" >/dev/null; then
  echo "Metabase not healthy in time" >&2
  exit 1
fi

# If already setup, exit gracefully
if curl -s "${BASE}/api/session/properties" | grep -q '"has-user-setup":true'; then
  echo "Metabase already set up. Exiting."
  exit 0
fi

payload=$(printf '{"token":"%s","user":{"first_name":"%s","last_name":"%s","email":"%s","password":"%s"},"prefs":{"site_name":"QR Metabase","site_locale":"it","allow_tracking":false},"database":{"engine":"postgres","name":"QR App DB","details":{"host":"%s","port":%s,"dbname":"%s","user":"%s","password":"%s","ssl":false}}}' \
  "$MB_SETUP_TOKEN" "$MB_ADMIN_FIRST_NAME" "$MB_ADMIN_LAST_NAME" "$MB_ADMIN_EMAIL" "$MB_ADMIN_PASSWORD" \
  "$TARGET_DB_HOST" "$TARGET_DB_PORT" "$TARGET_DB_NAME" "$POSTGRES_USER" "$POSTGRES_PASSWORD")

curl -sS -X POST "${BASE}/api/setup" \
  -H 'Content-Type: application/json' \
  -d "$payload"

echo "Setup completed."
