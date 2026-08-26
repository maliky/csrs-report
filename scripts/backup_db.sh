#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

timestamp="${CSRS_BACKUP_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
if [[ ! "$timestamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
    echo "CSRS_BACKUP_TIMESTAMP doit utiliser le format UTC YYYYMMDDTHHMMSSZ." >&2
    exit 2
fi

# shellcheck source=scripts/lib/compose.sh
source scripts/lib/compose.sh
csrs_compose_command

if [[ ! -f .env ]]; then
    echo ".env est requis pour identifier la base CSRS." >&2
    exit 1
fi

postgres_db="$(sed -n 's/^POSTGRES_DB=//p' .env)"
postgres_user="$(sed -n 's/^POSTGRES_USER=//p' .env)"
if [[ -z "$postgres_db" || -z "$postgres_user" ]]; then
    echo "POSTGRES_DB et POSTGRES_USER sont requis dans .env." >&2
    exit 1
fi

project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n 1)"
project="${project:-csrs}"
mkdir -p backups
chmod 700 backups
database_output="backups/csrs_${timestamp}.dump"
documents_output="backups/csrs_documents_${timestamp}.tar.gz"
manifest_output="backups/csrs_${timestamp}.sha256"
compose=("${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml)

"${compose[@]}" exec -T db \
    pg_dump --format=custom --no-owner --username "$postgres_user" "$postgres_db" > "$database_output"
"${compose[@]}" exec -T web \
    tar --create --gzip --directory /private-media . > "$documents_output"
chmod 600 "$database_output" "$documents_output"
"${compose[@]}" exec -T db pg_restore --list < "$database_output" > /dev/null
tar --list --gzip --file "$documents_output" > /dev/null
(
    cd backups
    sha256sum "$(basename "$database_output")" "$(basename "$documents_output")" > "$(basename "$manifest_output")"
)
chmod 600 "$manifest_output"
find backups -type f \( -name 'csrs_*.dump' -o -name 'csrs_documents_*.tar.gz' -o -name 'csrs_*.sha256' \) -mtime +14 -delete

echo "Sauvegarde verifiee : $database_output, $documents_output et $manifest_output"
