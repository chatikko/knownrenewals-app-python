#!/bin/sh
set -e

if [ -z "$CELERY_LOG_LEVEL" ]; then
  CELERY_LOG_LEVEL=info
fi

if [ -z "$CELERY_WORKER_CONCURRENCY" ]; then
  CELERY_WORKER_CONCURRENCY=2
fi

# Render free-tier workaround:
# when deployed as a Web Service, Render expects something to bind $PORT.
if [ -n "$PORT" ] && [ "${ENABLE_RENDER_PORT_HACK:-1}" = "1" ]; then
  python -m http.server "$PORT" --bind 0.0.0.0 >/dev/null 2>&1 &
fi

exec celery -A celery_app.celery_app worker -l "$CELERY_LOG_LEVEL" --concurrency "$CELERY_WORKER_CONCURRENCY"
