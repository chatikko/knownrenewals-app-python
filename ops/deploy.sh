#!/bin/sh
set -e

if [ ! -f .env ]; then
  echo ".env not found. Copy .env.example to .env and set secrets."
  exit 1
fi

docker compose -f docker-compose.prod.yml pull || true
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
