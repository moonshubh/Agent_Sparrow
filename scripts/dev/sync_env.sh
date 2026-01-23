#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SOURCE_ROOT=${1:-${ENV_SOURCE_ROOT:-}}
SYNC_MODE=${ENV_SYNC_MODE:-symlink}

if [[ -z "$SOURCE_ROOT" ]]; then
  echo "Usage: $0 /path/to/source-repo"
  echo "Or set ENV_SOURCE_ROOT to the source repo path."
  exit 1
fi

if [[ ! -d "$SOURCE_ROOT" ]]; then
  echo "Source root not found: $SOURCE_ROOT"
  exit 1
fi

link_or_copy() {
  local src=$1
  local dest=$2

  if [[ ! -f "$src" ]]; then
    return 0
  fi

  # Avoid ln/cp errors when src and dest are identical
  if [[ -e "$dest" && "$src" -ef "$dest" ]]; then
    return 0
  fi

  mkdir -p "$(dirname "$dest")"

  case "$SYNC_MODE" in
    copy) cp -f "$src" "$dest" ;;
    symlink) ln -sf "$src" "$dest" ;;
    *) echo "Unknown ENV_SYNC_MODE=$SYNC_MODE (expected copy|symlink)" >&2; return 1 ;;
  esac
}

ENV_FILE="$SOURCE_ROOT/.env"
ENV_LOCAL_FILE="$SOURCE_ROOT/.env.local"

if [[ -f "$ENV_FILE" ]]; then
  link_or_copy "$ENV_FILE" "$ROOT_DIR/.env"
fi

if [[ -f "$ENV_LOCAL_FILE" ]]; then
  link_or_copy "$ENV_LOCAL_FILE" "$ROOT_DIR/.env.local"
  link_or_copy "$ENV_LOCAL_FILE" "$ROOT_DIR/frontend/.env.local"
else
  if [[ -f "$ENV_FILE" ]]; then
    # Fallback: only copy NEXT_PUBLIC_* for the frontend if no .env.local exists.
    mkdir -p "$ROOT_DIR/frontend"
    grep -E '^NEXT_PUBLIC_' "$ENV_FILE" > "$ROOT_DIR/frontend/.env.local" || true
  fi
fi

echo "Env sync complete."
