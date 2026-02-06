#!/bin/sh
set -e

if [ -z "$WEB_CONCURRENCY" ]; then
  WEB_CONCURRENCY=2
fi

if [ -z "$PORT" ]; then
  PORT=10000
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$WEB_CONCURRENCY"
