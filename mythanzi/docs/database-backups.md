# Database Backups

`docker-compose.yml` runs two backup worker containers:

- `db-backup` backs up the main MyThanzi Postgres database.
- `hapi-db-backup` backs up the HAPI FHIR Postgres database.

Each worker creates compressed `*.sql.gz` dumps in a Docker named volume, not in the project `backups/` folder. By default, backups run once per day, keep files for 14 days, and keep no more than 30 dumps per database.

Configure the schedule and pruning in `.env`:

```env
BACKUP_INTERVAL_SECONDS=86400
BACKUP_RETENTION_DAYS=14
BACKUP_RETENTION_COUNT=30
```

Start the backup workers with the rest of the stack:

```powershell
docker compose up -d
```

Inspect backup logs:

```powershell
docker compose logs db-backup
docker compose logs hapi-db-backup
```

Copy backups out of their Docker volumes when you need an off-machine archive:

```powershell
docker run --rm -v mythanzi_mythanzi-db-backups:/backups -v ${PWD}:/out alpine sh -c "cp /backups/*.sql.gz /out/"
docker run --rm -v mythanzi_hapi-db-backups:/backups -v ${PWD}:/out alpine sh -c "cp /backups/*.sql.gz /out/"
```

Restore a main database backup:

```powershell
docker compose stop web
docker compose exec -T db dropdb -U postgres mythanzi
docker compose exec -T db createdb -U postgres mythanzi
gzip -dc .\mythanzi-YYYYMMDD-HHMMSS.sql.gz | docker compose exec -T db psql -U postgres -d mythanzi
docker compose start web
```

Restore a HAPI database backup:

```powershell
docker compose stop hapi-fhir
docker compose exec -T hapi-db dropdb -U hapi hapi
docker compose exec -T hapi-db createdb -U hapi hapi
gzip -dc .\hapi-YYYYMMDD-HHMMSS.sql.gz | docker compose exec -T hapi-db psql -U hapi -d hapi
docker compose start hapi-fhir
```
