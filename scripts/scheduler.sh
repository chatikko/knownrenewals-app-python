#!/bin/sh
set -e

if [ -z "$CELERY_LOG_LEVEL" ]; then
  CELERY_LOG_LEVEL=info
fi

# Render free-tier workaround:
# when deployed as a Web Service, Render expects something to bind $PORT.
if [ -n "$PORT" ] && [ "${ENABLE_RENDER_PORT_HACK:-1}" = "1" ]; then
  python -m http.server "$PORT" --bind 0.0.0.0 >/dev/null 2>&1 &
fi

exec celery -A celery_app.celery_app beat -l "$CELERY_LOG_LEVEL"
