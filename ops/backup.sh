#!/bin/sh
set -e

if [ -z "$PROJECT_DIR" ]; then
  PROJECT_DIR="/opt/knowrenewals"
fi

if [ -z "$BACKUP_DIR" ]; then
  BACKUP_DIR="/var/backups/knowrenewals"
fi

mkdir -p "$BACKUP_DIR"
timestamp=$(date +"%Y%m%d_%H%M%S")
backup_file="$BACKUP_DIR/knowrenewals_$timestamp.sql"

container_id=$(docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" ps -q postgres)
if [ -z "$container_id" ]; then
  echo "Postgres container not running."
  exit 1
fi

docker exec -i "$container_id" pg_dump -U postgres -d knowrenewals > "$backup_file"

echo "Backup saved to $backup_file"
