#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  echo "[i] .env already exists. Nothing to do."
  exit 0
fi

if [[ ! -f ".env.example" ]]; then
  echo "[!] .env.example not found in $ROOT_DIR"
  exit 1
fi

cp .env.example .env

# Generate secrets (best-effort)
gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    # fallback
    python - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
  fi
}

JWT="$(gen_secret)"
STEAMSLOT_KEY="$(gen_secret)"

# Replace defaults
# Use POSIX-safe sed
tmp="$(mktemp)"
sed "s/^JWT_SECRET=.*/JWT_SECRET=$JWT/; s/^STEAMSLOT_SESSION_KEY=.*/STEAMSLOT_SESSION_KEY=$STEAMSLOT_KEY/" .env > "$tmp"
mv "$tmp" .env

echo "[✓] Created .env from .env.example"
echo
echo "Next:"
echo "1) Set TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_ID (optional if approval not needed)."
echo "2) Set DATABASE_URL (OBS) and STEAMSLOT_DATABASE_URL if you use Postgres."
echo "3) Run: docker compose up --build"
