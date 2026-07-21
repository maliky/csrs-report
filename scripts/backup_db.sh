#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f .env ]]; then
    echo ".env est requis pour identifier la base CSRS." >&2
    exit 1
fi

POSTGRES_DB="$(sed -n 's/^POSTGRES_DB=//p' .env)"
POSTGRES_USER="$(sed -n 's/^POSTGRES_USER=//p' .env)"
if [[ -z "$POSTGRES_DB" || -z "$POSTGRES_USER" ]]; then
    echo "POSTGRES_DB et POSTGRES_USER sont requis dans .env." >&2
    exit 1
fi

mkdir -p backups
chmod 700 backups
output="backups/csrs_$(date -u +%Y%m%dT%H%M%SZ).dump"

docker compose -p csrs -f compose.yml exec -T db \
    pg_dump --format=custom --no-owner --username "$POSTGRES_USER" "$POSTGRES_DB" > "$output"
chmod 600 "$output"
docker compose -p csrs -f compose.yml exec -T db pg_restore --list < "$output" > /dev/null
find backups -type f -name 'csrs_*.dump' -mtime +14 -delete

echo "Sauvegarde verifiee : $output"
