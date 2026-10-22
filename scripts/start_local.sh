#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
if [[ -x /opt/homebrew/bin/node ]]; then export PATH="/opt/homebrew/bin:$PATH"; fi
if [[ ! -x .venv/bin/python ]]; then echo 'Run ./start.sh to install the pretrained runtime first.' >&2; exit 1; fi
export WORLDS_API_PORT="${WORLDS_API_PORT:-8026}"
export WORLDS_WEB_PORT="${WORLDS_WEB_PORT:-5173}"
.venv/bin/python -c 'import os; assert all(1024 <= int(os.environ[k]) <= 65535 for k in ("WORLDS_API_PORT","WORLDS_WEB_PORT")), "Invalid service port"'
command -v npm >/dev/null || { echo 'Node.js and npm are required.' >&2; exit 1; }
if [[ ! -d frontend/node_modules ]]; then (cd frontend && npm ci); fi
mkdir -p .runtime
backend_pid=''; frontend_pid=''
cleanup() {
  if [[ -n "$frontend_pid" ]]; then kill "$frontend_pid" 2>/dev/null || true; wait "$frontend_pid" 2>/dev/null || true; fi
  if [[ -n "$backend_pid" ]]; then kill "$backend_pid" 2>/dev/null || true; wait "$backend_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM
api_url="http://127.0.0.1:$WORLDS_API_PORT"
web_url="http://127.0.0.1:$WORLDS_WEB_PORT"
if curl --noproxy '*' -fsS --max-time 3 "$api_url/health" > .runtime/health.json; then
  .venv/bin/python -c 'import hashlib,json,pathlib; h=json.load(open(".runtime/health.json")); assert h.get("instance_id")==hashlib.sha256(str(pathlib.Path.cwd().resolve()).encode()).hexdigest(), "API port belongs to another checkout or an older running version; use another port or stop that service yourself"'
  echo "Reusing this checkout's API on $WORLDS_API_PORT."
else
  .venv/bin/python -m uvicorn worlds_predictor.api:app --host 127.0.0.1 --port "$WORLDS_API_PORT" > .runtime/backend.log 2>&1 &
  backend_pid=$!
  for attempt in {1..45}; do
    if curl --noproxy '*' -fsS --max-time 2 "$api_url/health" >/dev/null 2>&1; then break; fi
    kill -0 "$backend_pid" 2>/dev/null || { cat .runtime/backend.log >&2; exit 1; }
    sleep 1
  done
  kill -0 "$backend_pid" 2>/dev/null || { cat .runtime/backend.log >&2; exit 1; }
  curl --noproxy '*' -fsS --max-time 3 "$api_url/health" >/dev/null
fi
if curl --noproxy '*' -fsS --max-time 3 "$web_url/__worlds_instance" > .runtime/frontend-instance.json; then
  .venv/bin/python -c 'import hashlib,json,pathlib,os; h=json.load(open(".runtime/frontend-instance.json")); assert h.get("instance_id")==hashlib.sha256(str(pathlib.Path.cwd().resolve()).encode()).hexdigest() and h.get("api_port")==int(os.environ["WORLDS_API_PORT"]), "Web port belongs to another checkout/backend"'
  echo "Website already running: $web_url"
  if [[ -n "$backend_pid" ]]; then wait "$backend_pid"; fi
  exit 0
fi
if [[ "${1:-}" == '--production' ]]; then (cd frontend && npm run build); fi
if [[ "${1:-}" == '--production' || "${1:-}" == '--built' ]]; then
  (cd frontend && exec node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port "$WORLDS_WEB_PORT" --strictPort) > .runtime/frontend.log 2>&1 &
else
  (cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$WORLDS_WEB_PORT" --strictPort) > .runtime/frontend.log 2>&1 &
fi
frontend_pid=$!
for attempt in {1..30}; do
  if curl --noproxy '*' -fsS --max-time 2 "$web_url/__worlds_instance" >/dev/null 2>&1; then break; fi
  kill -0 "$frontend_pid" 2>/dev/null || { cat .runtime/frontend.log >&2; exit 1; }
  sleep 1
 done
kill -0 "$frontend_pid" 2>/dev/null || { cat .runtime/frontend.log >&2; exit 1; }
curl --noproxy '*' -fsS --max-time 3 "$web_url/__worlds_instance" >/dev/null
echo "T1.the shy 2026 BP Predictor: $web_url"
echo "API docs: $api_url/docs"
echo 'Ctrl+C stops only the processes this command started.'
wait "$frontend_pid"
