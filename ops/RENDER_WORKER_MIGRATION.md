# Render Worker Migration Guide

This runbook is for moving from the current free-tier workaround (Celery running in Render Web Services) to paid Render worker services.

## Why This Migration

On free tier, we use a `PORT` hack in:

- `scripts/worker.sh`
- `scripts/scheduler.sh`

That is only to satisfy Web Service port checks. Paid worker services do not need this.

## Target Architecture (Paid)

1. `api` -> Render **Web Service**
2. `worker` -> Render **Background Worker** (Celery worker)
3. `scheduler` -> Render **Background Worker** (Celery beat), or Render Cron Job

## Required Changes

Set this env var to disable the free-tier port hack:

- `ENABLE_RENDER_PORT_HACK=0`

Keep these env vars set:

- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_WORKER_CONCURRENCY` (start with `2` on small instances)
- all app-specific vars from `.env.example`

## Render Service Setup

## 1) Worker service

- Service type: **Background Worker**
- Dockerfile: `Dockerfile.worker`
- Start command: `sh ./scripts/worker.sh`

## 2) Scheduler service

- Service type: **Background Worker**
- Dockerfile: `Dockerfile.worker`
- Start command: `sh ./scripts/scheduler.sh`

Alternative: use Render Cron Job if you want only periodic execution and not continuous beat.

## 3) API service

- Keep as **Web Service**
- No worker-specific changes needed.

## Cutover Checklist

1. Deploy worker service as Background Worker.
2. Deploy scheduler service as Background Worker (or Cron).
3. Set `ENABLE_RENDER_PORT_HACK=0` for worker/scheduler.
4. Remove or disable old free-tier Web Service worker/scheduler instances.
5. Verify task execution from logs:
   - worker logs show tasks received/executed.
   - scheduler logs show beat schedule ticks.
6. Trigger a test task manually (example from app flow) and confirm completion.

## Post-Migration Validation

- No more `No open ports detected` messages on worker/scheduler.
- No root warning if using updated `Dockerfile.worker` (`USER app`).
- Celery startup warning about broker retry is gone (`broker_connection_retry_on_startup=True`).

## Rollback

If needed, temporarily revert to free-tier style by setting:

- `ENABLE_RENDER_PORT_HACK=1`

and running worker/scheduler as Web Services again.

