#!/bin/sh
set -e

if [ -z "$CELERY_LOG_LEVEL" ]; then
  CELERY_LOG_LEVEL=info
fi

if [ -z "$CELERY_WORKER_CONCURRENCY" ]; then
  CELERY_WORKER_CONCURRENCY=2
fi

if [ -z "$CELERY_WORKER_POOL" ]; then
  CELERY_WORKER_POOL=prefork
fi

# Async SQLAlchemy + asyncio.run in Celery tasks can hit event-loop mismatch
# with pooled asyncpg connections. Use NullPool in worker process by default.
if [ -z "$DB_ASYNC_NULLPOOL" ]; then
  DB_ASYNC_NULLPOOL=1
fi
export DB_ASYNC_NULLPOOL

# Render free-tier workaround:
# when deployed as a Web Service, Render expects something to bind $PORT.
if [ -n "$PORT" ] && [ "${ENABLE_RENDER_PORT_HACK:-1}" = "1" ]; then
  python ./scripts/render_port_stub.py >/dev/null 2>&1 &
fi

exec celery -A celery_app.celery_app worker -l "$CELERY_LOG_LEVEL" --concurrency "$CELERY_WORKER_CONCURRENCY" --pool "$CELERY_WORKER_POOL"
