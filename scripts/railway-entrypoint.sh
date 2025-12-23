#!/usr/bin/env sh
set -e

entry_name="$(basename "$0")"

log() {
  printf '[railway-entrypoint] %s\n' "$*"
}

start_health_server() {
  # Lightweight health endpoint for worker services so Railway HTTP checks pass.
  log "starting worker health server on port ${PORT:-8000}"
  python - <<'PY' &
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args):
        # Silence default request logs in worker containers.
        return

port = int(os.getenv("HEALTH_PORT") or os.getenv("PORT", "8000"))
HTTPServer(("", port), Handler).serve_forever()
PY
}
# Railway worker services sometimes omit the "celery" executable and start with
# "-A ...", which Docker interprets as the command itself. Some setups execute
# the start command as the entrypoint, so handle both argv[0] and argv[1].
if [ "$entry_name" = "-A" ] || [ "$entry_name" = "-a" ]; then
  start_health_server
  exec celery -A "$@"
fi

if [ "${1:-}" = "-A" ] || [ "${1:-}" = "-a" ]; then
  if [ "${1:-}" = "-a" ]; then
    shift
    set -- "-A" "$@"
  fi
  start_health_server
  exec celery "$@"
fi

if [ "${1:-}" = "celery" ]; then
  start_health_server
  exec "$@"
fi

if [ "${1:-}" = "sh" ] || [ "${1:-}" = "bash" ]; then
  if [ "${2:-}" = "-lc" ] || [ "${2:-}" = "-c" ]; then
    cmd_string="${3:-}"
    case "$cmd_string" in
      *celery*|*-A*)
        log "detected celery command via shell wrapper"
        start_health_server
        ;;
    esac
  fi
fi

if [ "$#" -eq 0 ]; then
  exec sh -lc "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
fi

exec "$@"
