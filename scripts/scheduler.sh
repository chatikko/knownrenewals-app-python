#!/bin/sh
set -e

exec celery -A celery_app.celery_app beat -l info
