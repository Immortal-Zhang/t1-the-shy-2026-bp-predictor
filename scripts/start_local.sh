#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# On this macOS host, prefer the regular Homebrew runtime over app-embedded Node.
if [[ -x /opt/homebrew/bin/node ]]; then export PATH="/opt/homebrew/bin:$PATH"; fi
if [[ ! -x .venv/bin/python ]]; then
  echo 'Missing .venv. Follow the Python setup commands in README.md first.' >&2
  exit 1
fi
command -v npm >/dev/null || { echo 'Node.js and npm are required.' >&2; exit 1; }
if [[ ! -d frontend/node_modules ]]; then (cd frontend && npm ci); fi
mkdir -p .runtime
backend_pid=''
frontend_pid=''
cleanup() {
  if [[ -n "$frontend_pid" ]]; then kill "$frontend_pid" 2>/dev/null || true; fi
  if [[ -n "$backend_pid" ]]; then kill "$backend_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8026/health > .runtime/health.json; then
  .venv/bin/python -c 'import json; assert json.load(open(".runtime/health.json"))["service"] == "Worlds 2026 BP Predictor", "Port 8026 belongs to a different service"'
  echo 'Reusing existing Worlds API on 8026.'
else
  .venv/bin/python -m uvicorn worlds_predictor.api:app --host 127.0.0.1 --port 8026 > .runtime/backend.log 2>&1 &
  backend_pid=$!
  for attempt in {1..30}; do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8026/health >/dev/null 2>&1; then break; fi
    kill -0 "$backend_pid" 2>/dev/null || { cat .runtime/backend.log >&2; exit 1; }
    sleep 1
  done
  curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8026/health >/dev/null
fi

if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:5173/ > .runtime/frontend.html; then
  .venv/bin/python -c 'from pathlib import Path; assert "Worlds 2026" in Path(".runtime/frontend.html").read_text(), "Port 5173 belongs to a different website"'
  echo 'Website already running: http://127.0.0.1:5173'
  if [[ -n "$backend_pid" ]]; then wait "$backend_pid"; fi
  exit 0
fi
if [[ "${1:-}" == '--production' ]]; then
  (cd frontend && npm run build)
  (cd frontend && exec node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort) > .runtime/frontend.log 2>&1 &
else
  (cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort) > .runtime/frontend.log 2>&1 &
fi
frontend_pid=$!
echo 'Website: http://127.0.0.1:5173'
echo 'API docs: http://127.0.0.1:8026/docs'
echo 'Logs: .runtime/backend.log and .runtime/frontend.log'
echo 'Ctrl+C stops only the processes started by this script.'
wait "$frontend_pid"
