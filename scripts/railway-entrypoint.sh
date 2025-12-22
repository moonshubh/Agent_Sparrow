#!/usr/bin/env sh
set -e

entry_name="$(basename "$0")"
# Railway worker services sometimes omit the "celery" executable and start with
# "-A ...", which Docker interprets as the command itself. Some setups execute
# the start command as the entrypoint, so handle both argv[0] and argv[1].
if [ "$entry_name" = "-A" ] || [ "$entry_name" = "-a" ]; then
  exec celery -A "$@"
fi

if [ "${1:-}" = "-A" ] || [ "${1:-}" = "-a" ]; then
  if [ "${1:-}" = "-a" ]; then
    shift
    set -- "-A" "$@"
  fi
  exec celery "$@"
fi

if [ "$#" -eq 0 ]; then
  exec sh -lc "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
fi

exec "$@"
