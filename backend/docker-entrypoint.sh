#!/bin/sh
# Container entrypoint for the FitAI backend (Render / local Docker).
#
# 1. As root: create the persistent directories and hand them to the app user,
#    because a freshly mounted disk is owned by root. Then re-exec unprivileged.
# 2. As the app user: apply Alembic migrations (upgrade only, never destructive;
#    disable with RUN_MIGRATIONS=false) and start uvicorn on $PORT.
set -eu

if [ "$(id -u)" = "0" ]; then
    for dir in "${CHROMADB_PERSIST_DIR:-}" "${UPLOAD_DIR:-}" "${HF_HOME:-}"; do
        if [ -n "$dir" ]; then
            mkdir -p "$dir"
            chown -R app:app "$dir"
        fi
    done
    exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "entrypoint: applying database migrations (alembic upgrade head)"
    alembic upgrade head
fi

echo "entrypoint: starting uvicorn on 0.0.0.0:${PORT:-8000}"
# exec: uvicorn becomes PID 1 and receives SIGTERM directly for a graceful stop.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips "*" \
    --timeout-graceful-shutdown "${GRACEFUL_SHUTDOWN_SECONDS:-25}"
