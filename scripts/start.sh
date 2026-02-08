#!/bin/sh
set -e

if [ -z "$WEB_CONCURRENCY" ]; then
  WEB_CONCURRENCY=2
fi

if [ -z "$PORT" ]; then
  PORT=8000
fi

MIGRATION_RETRIES="${DB_MIGRATION_RETRIES:-30}"

echo "Running database migrations..."
until alembic upgrade head; do
  MIGRATION_RETRIES=$((MIGRATION_RETRIES - 1))
  if [ "$MIGRATION_RETRIES" -le 0 ]; then
    echo "Database migrations failed after retries. Exiting."
    exit 1
  fi
  echo "Migration failed, retrying in 2 seconds..."
  sleep 2
done

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$WEB_CONCURRENCY"
