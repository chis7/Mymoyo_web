#!/bin/sh
set -eu

: "${POSTGRES_HOST:?Set POSTGRES_HOST}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:?Set POSTGRES_DB}"
: "${POSTGRES_USER:?Set POSTGRES_USER}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}"
: "${BACKUP_PREFIX:=${POSTGRES_DB}}"
: "${BACKUP_DIR:=/backups}"
: "${BACKUP_INTERVAL_SECONDS:=86400}"
: "${BACKUP_RETENTION_DAYS:=14}"
: "${BACKUP_RETENTION_COUNT:=30}"

export PGPASSWORD="$POSTGRES_PASSWORD"

mkdir -p "$BACKUP_DIR"

wait_for_database() {
  until pg_isready \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" >/dev/null 2>&1; do
    echo "Waiting for $POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB..."
    sleep 5
  done
}

run_backup() {
  timestamp="$(date -u +%Y%m%d-%H%M%S)"
  output="$BACKUP_DIR/$BACKUP_PREFIX-$timestamp.sql.gz"

  echo "Creating backup $output"
  pg_dump \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=plain \
    --no-owner \
    --no-privileges \
    | gzip > "$output"

  find "$BACKUP_DIR" \
    -type f \
    -name "$BACKUP_PREFIX-*.sql.gz" \
    -mtime +"$BACKUP_RETENTION_DAYS" \
    -delete

  find "$BACKUP_DIR" -type f -name "$BACKUP_PREFIX-*.sql.gz" \
    | sort \
    | awk -v keep="$BACKUP_RETENTION_COUNT" '
        { files[NR] = $0 }
        END {
          for (i = 1; i <= NR - keep; i++) {
            print files[i]
          }
        }
      ' \
    | while IFS= read -r old_backup; do
        rm -f "$old_backup"
      done
}

while true; do
  wait_for_database
  run_backup
  echo "Next $BACKUP_PREFIX backup in $BACKUP_INTERVAL_SECONDS seconds"
  sleep "$BACKUP_INTERVAL_SECONDS"
done
