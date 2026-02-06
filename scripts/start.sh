#!/bin/sh
set -e

if [ -z "$WEB_CONCURRENCY" ]; then
  WEB_CONCURRENCY=2
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$WEB_CONCURRENCY"
