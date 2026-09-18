#!/usr/bin/env bash
# Start the complete local development environment with one command.
#
#   scripts/dev-start.sh              start the backend and the console
#   scripts/dev-start.sh --dry-run    run preflight checks and credential setup only
#
# The script owns the credential lifecycle for the environment it starts: it generates
# one ephemeral JWT signing secret, mints one token from that exact secret, gives the
# secret to the backend and the token to the Vite development proxy, and verifies the
# pair before handing over. Both values live only in process environment variables and
# disappear when the environment stops. Nothing is written to the repository.
#
# The secret stays server-side: the frontend process is started with JWT_SECRET_KEY
# removed from its environment. The browser receives neither value (see
# frontend/vite.config.ts).
#
# Environment:
#   BACKEND_PORT                      backend port (default 8000)
#   FRONTEND_PORT                     console port (default 3000)
#   EASP_DEV_TOKEN_ROLE               ANALYST (default), or ADMIN for admin/runtime endpoints
#   EASP_DEV_TOKEN_LIFETIME_MINUTES   token lifetime (default 1440, one day)
#   EASP_DEV_RELOAD=1                 run the backend with --reload
#   EASP_DEV_PYTHON                   interpreter to use (default .venv/bin/python)
#
# The console proxy is pointed at the backend this script started (EASP_DEV_API_TARGET),
# so a non-default BACKEND_PORT never sends development credentials to another backend.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
ROLE="${EASP_DEV_TOKEN_ROLE:-ANALYST}"
LIFETIME_MINUTES="${EASP_DEV_TOKEN_LIFETIME_MINUTES:-1440}"
PYTHON="${EASP_DEV_PYTHON:-$ROOT/.venv/bin/python}"
CREDENTIALS="$ROOT/scripts/dev_credentials.py"

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
elif [ -n "${1:-}" ]; then
  echo "usage: scripts/dev-start.sh [--dry-run]" >&2
  exit 2
fi

BACKEND_PID=""
FRONTEND_PID=""
STOPPING=0

fail() {
  echo "error: $1" >&2
  exit 1
}

# Stop what this script started: the recorded process ids and their immediate children
# (npm spawns Vite as a child). Deliberately not a pattern-based kill, which would risk
# stopping unrelated developer processes.
cleanup() {
  trap - INT TERM EXIT
  local pid
  for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
    [ -n "$pid" ] || continue
    kill -0 "$pid" 2>/dev/null || continue
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo ""
  echo "Development environment stopped. The development secret and token are gone."
}

port_is_free() {
  "$PYTHON" - "$1" <<'PY'
import socket
import sys

with socket.socket() as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", int(sys.argv[1])))
    except OSError:
        raise SystemExit(1)
raise SystemExit(0)
PY
}

preflight() {
  [ -x "$PYTHON" ] || fail "no interpreter at $PYTHON. Create it with: python3.13 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"

  "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)' \
    || fail "$PYTHON is not Python 3.13, which this project targets."

  "$PYTHON" -c 'import fastapi, uvicorn, jwt' 2>/dev/null \
    || fail "backend dependencies are missing. Install them with: $PYTHON -m pip install -r requirements.txt"

  [ -d "$ROOT/frontend" ] || fail "frontend directory not found at $ROOT/frontend"
  [ -d "$ROOT/frontend/node_modules" ] \
    || fail "frontend dependencies are missing. Install them with: (cd frontend && npm install)"

  port_is_free "$BACKEND_PORT" \
    || fail "port $BACKEND_PORT is already in use. Stop that process, or set BACKEND_PORT."
  port_is_free "$FRONTEND_PORT" \
    || fail "port $FRONTEND_PORT is already in use. Stop that process, or set FRONTEND_PORT."

  case "$ROLE" in
    ANALYST|ADMIN) ;;
    *) fail "EASP_DEV_TOKEN_ROLE must be ANALYST or ADMIN (got '$ROLE')." ;;
  esac
}

wait_for_health() {
  local attempt=0
  while [ "$attempt" -lt 60 ]; do
    if curl -sf -o /dev/null "http://$BACKEND_HOST:$BACKEND_PORT/health"; then
      return 0
    fi
    kill -0 "$BACKEND_PID" 2>/dev/null || fail "the backend exited during startup."
    attempt=$((attempt + 1))
    sleep 0.5
  done
  fail "the backend did not become healthy at http://$BACKEND_HOST:$BACKEND_PORT/health"
}

echo "Enterprise Agent Security Platform — local development"
preflight

# One secret, one token, both minted here and never written to disk.
JWT_SECRET_KEY="$("$PYTHON" "$CREDENTIALS" secret)"
export JWT_SECRET_KEY
EASP_DEV_API_TOKEN="$("$PYTHON" "$CREDENTIALS" token --role "$ROLE" --lifetime-minutes "$LIFETIME_MINUTES")"
export EASP_DEV_API_TOKEN

"$PYTHON" "$CREDENTIALS" summary --role "$ROLE" --lifetime-minutes "$LIFETIME_MINUTES"

if [ "$ROLE" = "ADMIN" ]; then
  echo "note: ADMIN role requested; the console normally runs with the least-privileged ANALYST role."
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run complete: preflight checks passed and credentials were generated."
  exit 0
fi

# Ctrl+C and SIGTERM are a requested stop; the EXIT trap covers every other exit path.
on_signal() {
  STOPPING=1
  cleanup
  exit 0
}
trap on_signal INT TERM
trap cleanup EXIT

echo "Starting backend on http://$BACKEND_HOST:$BACKEND_PORT ..."
if [ "${EASP_DEV_RELOAD:-0}" = "1" ]; then
  "$PYTHON" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload &
else
  "$PYTHON" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
fi
BACKEND_PID=$!

wait_for_health
echo "Backend healthy. Verifying the development credential pair ..."
"$PYTHON" "$CREDENTIALS" smoke --base-url "http://$BACKEND_HOST:$BACKEND_PORT" \
  || fail "the development credential check failed; see the message above."

echo "Starting console on http://localhost:$FRONTEND_PORT ..."
# The console proxy needs the token and the backend origin, and must never receive the
# signing secret.
export EASP_DEV_API_TARGET="http://$BACKEND_HOST:$BACKEND_PORT"
(
  cd "$ROOT/frontend"
  env -u JWT_SECRET_KEY npm run dev -- --port "$FRONTEND_PORT" --strictPort
) &
FRONTEND_PID=$!

echo ""
echo "Console:  http://localhost:$FRONTEND_PORT"
echo "Backend:  http://$BACKEND_HOST:$BACKEND_PORT (API docs at /docs)"
echo "Role:     $ROLE, token valid for $LIFETIME_MINUTES minutes"
echo "Press Ctrl+C to stop both."
echo ""

# Exit as soon as either process stops, so a crashed backend does not leave a console
# that only returns 401s. Reaching this point without a stop request means one of them
# terminated on its own, which is a failure: report it and exit non-zero.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

if [ "$STOPPING" -eq 0 ]; then
  kill -0 "$BACKEND_PID" 2>/dev/null || echo "error: the backend stopped unexpectedly." >&2
  kill -0 "$FRONTEND_PID" 2>/dev/null || echo "error: the console stopped unexpectedly." >&2
  exit 1
fi
