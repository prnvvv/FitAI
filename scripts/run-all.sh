#!/usr/bin/env bash
# Run the FitAI backend and frontend together locally.
# Usage: ./scripts/run-all.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8000"

echo "Starting FitAI..."
echo "  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "  Frontend: http://127.0.0.1:5173"
echo "  Press Ctrl+C to stop both."
echo ""

cleanup() {
  echo ""
  echo "Shutting down..."
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
    wait "${FRONTEND_PID}" 2>/dev/null || true
  fi
  echo "Done."
}

trap cleanup INT TERM EXIT

cd "${BACKEND_DIR}"
python -m uvicorn app.main:app --reload --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" &
BACKEND_PID=$!

cd "${FRONTEND_DIR}"
npm run dev &
FRONTEND_PID=$!

wait
