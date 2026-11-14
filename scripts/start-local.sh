#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
ROOT_DIR=$(pwd)
if [ ! -x backend/.venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo 'Install first: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt'
  echo 'Then: cd frontend && npm install'
  exit 1
fi
backend/.venv/bin/python - <<'CHECK_PORTS'
import socket
for port in (8000, 5173):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'Port {port} is already in use. Stop your old backend/frontend terminals with Ctrl+C, then run this script again.')
CHECK_PORTS
cleanup() {
  trap - EXIT INT TERM
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
# Explicit local settings override old OAuth/tunnel values in backend/.env.
(cd backend && exec env MODE=browser FRONTEND_ORIGIN=http://localhost:5173 COOKIE_SECURE=false TOKEN_KEY= "$ROOT_DIR/backend/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 --no-access-log) &
BACKEND_PID=$!
(cd frontend && exec node node_modules/vite/bin/vite.js --host localhost --port 5173 --strictPort) &
FRONTEND_PID=$!
trap cleanup EXIT INT TERM
echo 'Open http://localhost:5173 — Ctrl+C stops both servers. Close old servers first.'
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do sleep 1; done
