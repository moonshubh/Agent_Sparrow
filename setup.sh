#!/usr/bin/env bash
# -------------------------------------------------------------------
# MB-Sparrow – one-shot environment bootstrap for the Codex agent
# -------------------------------------------------------------------
# Idempotent: safe to run multiple times.
# Exits immediately on any error.
# -------------------------------------------------------------------

set -euo pipefail

echo ">>> Updating APT index & installing system packages"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
     build-essential git curl \
     python3.10 python3.10-venv python3.10-dev \
     libpq-dev  # → psycopg2 / pgvector wheels

echo ">>> Installing Node.js 18.x & pnpm"
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
if ! command -v pnpm >/dev/null 2>&1; then
  sudo npm install -g pnpm
fi

echo ">>> Creating Python virtual-env & installing backend dependencies"
if [ ! -d venv ]; then
  python3.10 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ">>> Installing frontend dependencies"
pushd frontend >/dev/null
pnpm install --frozen-lockfile
popd >/dev/null

echo ">>> Provisioning environment templates (no secrets committed)"
[ -f .env ] || cp .env.example .env || true
[ -f frontend/.env.local ] || cp frontend/.env.example frontend/.env.local || true

echo ">>> Setup complete ✔"
