#!/usr/bin/env bash
# Run the FitAI backend and frontend together locally (bash / Git Bash).
# Usage: ./scripts/run-all.sh
#
# The backend address has a single source of truth: BACKEND_HOST and
# BACKEND_PORT in backend/.env (falling back to the defaults below).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

read_env_value() {
  local key="$1" default="$2"
  if [[ -f "${BACKEND_DIR}/.env" ]]; then
    local value
    value="$(sed -n "s/^${key}=//p" "${BACKEND_DIR}/.env" | head -n 1 | tr -d '\r' | xargs)"
    if [[ -n "${value}" ]]; then
      echo "${value}"
      return
    fi
  fi
  echo "${default}"
}

BACKEND_HOST="$(read_env_value BACKEND_HOST 127.0.0.1)"
BACKEND_PORT="$(read_env_value BACKEND_PORT 8000)"

if command -v powershell.exe >/dev/null 2>&1; then
  if powershell.exe -NoProfile -Command \
      "if (Get-NetTCPConnection -LocalPort ${BACKEND_PORT} -State Listen -ErrorAction SilentlyContinue) { exit 1 }"; then
    :
  else
    echo "Cannot start the backend: port ${BACKEND_PORT} is already in use." >&2
    echo "Find the owner:  Get-NetTCPConnection -LocalPort ${BACKEND_PORT} | Select-Object -ExpandProperty OwningProcess" >&2
    echo "Or change the port: set BACKEND_PORT in backend/.env (the Vite proxy reads the same value)." >&2
    exit 1
  fi
fi

PYTHON="${BACKEND_DIR}/.venv/Scripts/python.exe"
[[ -x "${PYTHON}" ]] || PYTHON="${BACKEND_DIR}/.venv/bin/python"
[[ -x "${PYTHON}" ]] || PYTHON="python"

echo "Starting FitAI..."
echo "  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "  Frontend: http://127.0.0.1:5173"
echo "  Press Ctrl+C to stop both."
echo ""

cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in "${BACKEND_PID:-}" "${FRONTEND_PID:-}"; do
    [[ -n "${pid}" ]] || continue
    taskkill.exe //PID "${pid}" //T //F >/dev/null 2>&1 || kill "${pid}" 2>/dev/null || true
  done
  echo "Done."
}

trap cleanup INT TERM EXIT

cd "${BACKEND_DIR}"
"${PYTHON}" -m uvicorn app.main:app --reload --reload-dir app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" &
BACKEND_PID=$!

cd "${FRONTEND_DIR}"
npm run dev &
FRONTEND_PID=$!

wait
