#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    cat <<'EOF'
Usage : scripts/sync_preprod_from_production.sh --check|--apply

  --check  Vérifie les deux environnements sans transférer ni modifier de données.
  --apply  Copie la base et les documents de production vers la préproduction.

La production est lue par SSH, sans fichier temporaire ni commande d'écriture.
EOF
}

mode="${1:-}"
if [[ "$#" -ne 1 || ( "$mode" != "--check" && "$mode" != "--apply" ) ]]; then
    usage >&2
    exit 2
fi

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"
# shellcheck source=scripts/lib/compose.sh
source scripts/lib/compose.sh
csrs_compose_command

production_ssh="${CSRS_PRODUCTION_SSH:-jil@179.237.107.40}"
production_path="${CSRS_PRODUCTION_PATH:-/home/jil/csrs_report}"
minimum_free_kb="${CSRS_SYNC_MIN_FREE_KB:-262144}"
ssh_options=(-o BatchMode=yes -o StrictHostKeyChecking=yes)
incoming_dir=""
services_stopped=0
rollback_ready=0
rollback_dump=""
rollback_documents=""

env_value() {
    local key="$1"
    sed -n "s/^${key}=//p" .env | tail -n 1
}

require_preprod() {
    [[ -f .env ]] || { echo ".env de préproduction absent." >&2; return 1; }

    local project port host notifier
    project="$(env_value COMPOSE_PROJECT_NAME)"
    port="$(env_value CSRS_PORT)"
    host="$(env_value CSRS_HOST)"
    notifier="$(env_value CSRS_START_NOTIFIER)"

    [[ "$project" == "csrs_preprod" ]] || { echo "Projet Compose inattendu : $project" >&2; return 1; }
    [[ "$port" == "18008" ]] || { echo "Port de préproduction inattendu : $port" >&2; return 1; }
    [[ "$host" == "preprod.report.ent.koba.sarl" ]] || { echo "Hôte de préproduction inattendu : $host" >&2; return 1; }
    [[ "$notifier" == "0" ]] || { echo "CSRS_START_NOTIFIER doit rester à 0 en préproduction." >&2; return 1; }
    [[ "$minimum_free_kb" =~ ^[0-9]+$ ]] || { echo "CSRS_SYNC_MIN_FREE_KB invalide." >&2; return 1; }

    local available_kb db_id web_id db_health web_health
    available_kb="$(df -Pk "$repo" | awk 'NR == 2 {print $4}')"
    (( available_kb >= minimum_free_kb )) || { echo "Espace disque insuffisant pour la synchronisation." >&2; return 1; }

    compose=("${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml)
    db_id="$("${compose[@]}" ps -q db)"
    web_id="$("${compose[@]}" ps -q web)"
    [[ -n "$db_id" && -n "$web_id" ]] || { echo "Services db ou web de préproduction absents." >&2; return 1; }
    db_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$db_id")"
    web_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$web_id")"
    [[ "$db_health" == "healthy" && "$web_health" == "healthy" ]] || { echo "Préproduction non saine : db=$db_health web=$web_health" >&2; return 1; }
}

check_production() {
    ssh "${ssh_options[@]}" "$production_ssh" bash -s -- "$production_path" <<'REMOTE'
set -Eeuo pipefail
repo="$1"
cd "$repo"
[[ -f .env ]] || { echo ".env de production absent." >&2; exit 1; }
env_value() { sed -n "s/^$1=//p" .env | tail -n 1; }
project="$(env_value COMPOSE_PROJECT_NAME)"
port="$(env_value CSRS_PORT)"
branch="$(git branch --show-current)"
[[ "$project" == "csrs" ]] || { echo "Projet Compose de production inattendu : $project" >&2; exit 1; }
[[ "$port" == "18005" ]] || { echo "Port de production inattendu : $port" >&2; exit 1; }
[[ "$branch" == "main" ]] || { echo "Branche de production inattendue : $branch" >&2; exit 1; }
db_id="$(docker ps -q --filter label=com.docker.compose.project=csrs --filter label=com.docker.compose.service=db)"
web_id="$(docker ps -q --filter label=com.docker.compose.project=csrs --filter label=com.docker.compose.service=web)"
[[ -n "$db_id" && -n "$web_id" ]] || { echo "Services db ou web de production absents." >&2; exit 1; }
db_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$db_id")"
web_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$web_id")"
[[ "$db_health" == "healthy" && "$web_health" == "healthy" ]] || { echo "Production non saine : db=$db_health web=$web_health" >&2; exit 1; }
printf 'PRODUCTION_OK branch=%s db=%s web=%s\n' "$branch" "$db_health" "$web_health"
REMOTE
}

fetch_database() {
    local output="$1"
    ssh "${ssh_options[@]}" "$production_ssh" bash -s -- "$production_path" >"$output" <<'REMOTE'
set -Eeuo pipefail
cd "$1"
db_id="$(docker ps -q --filter label=com.docker.compose.project=csrs --filter label=com.docker.compose.service=db)"
[[ -n "$db_id" ]] || { echo "Base de production absente." >&2; exit 1; }
docker exec "$db_id" sh -c 'exec pg_dump --format=custom --no-owner --no-acl --username "$POSTGRES_USER" "$POSTGRES_DB"'
REMOTE
}

fetch_documents() {
    local output="$1"
    ssh "${ssh_options[@]}" "$production_ssh" bash -s -- "$production_path" >"$output" <<'REMOTE'
set -Eeuo pipefail
cd "$1"
web_id="$(docker ps -q --filter label=com.docker.compose.project=csrs --filter label=com.docker.compose.service=web)"
[[ -n "$web_id" ]] || { echo "Service web de production absent." >&2; exit 1; }
docker exec "$web_id" tar --create --gzip --directory /private-media .
REMOTE
}

restore_database() {
    local dump="$1"
    local database user
    database="$(env_value POSTGRES_DB)"
    user="$(env_value POSTGRES_USER)"
    [[ -n "$database" && -n "$user" ]] || return 1
    "${compose[@]}" exec -T db dropdb --if-exists --force --username "$user" "$database"
    "${compose[@]}" exec -T db createdb --username "$user" --owner "$user" "$database"
    "${compose[@]}" exec -T db pg_restore --exit-on-error --no-owner --no-acl --username "$user" --dbname "$database" <"$dump"
}

restore_documents() {
    local archive="$1"
    "${compose[@]}" run --rm -T --no-deps --entrypoint sh web -c \
        'find /private-media -mindepth 1 -delete && tar --extract --gzip --no-same-owner --directory /private-media' \
        <"$archive"
}

wait_for_web() {
    local web_id health
    web_id="$("${compose[@]}" ps -q web)"
    [[ -n "$web_id" ]] || return 1
    for _attempt in $(seq 1 36); do
        health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$web_id")"
        if [[ "$health" == "healthy" ]] && curl --fail --silent \
            --header 'Host: preprod.report.ent.koba.sarl' \
            --header 'X-Forwarded-Proto: https' \
            http://127.0.0.1:18008/connexion/ >/dev/null; then
            return 0
        fi
        sleep 5
    done
    return 1
}

cleanup() {
    if [[ -n "$incoming_dir" && -d "$incoming_dir" ]]; then
        rm -rf -- "$incoming_dir"
    fi
}

rollback_preprod() {
    echo "Échec de synchronisation; restauration de la sauvegarde de préproduction." >&2
    "${compose[@]}" stop notifier web >/dev/null 2>&1 || true
    if restore_database "$rollback_dump" && restore_documents "$rollback_documents"; then
        "${compose[@]}" up -d web
        "${compose[@]}" stop notifier >/dev/null 2>&1 || true
        if wait_for_web; then
            services_stopped=0
            echo "Retour arrière terminé; la préproduction est de nouveau saine." >&2
            return 0
        fi
    fi
    "${compose[@]}" stop notifier web >/dev/null 2>&1 || true
    echo "ÉCHEC CRITIQUE : retour arrière impossible; préproduction maintenue indisponible." >&2
    return 1
}

on_exit() {
    local status="$1"
    trap - EXIT
    if [[ "$status" -ne 0 && "$services_stopped" == "1" && "$rollback_ready" == "1" ]]; then
        rollback_preprod || true
    fi
    cleanup
    exit "$status"
}
trap 'on_exit $?' EXIT

require_preprod
check_production
if [[ "$mode" == "--check" ]]; then
    echo "SYNC_CHECK_OK production en lecture seule et préproduction prête."
    exit 0
fi

sync_id="$(date -u +%Y%m%dT%H%M%SZ)"
incoming_dir="backups/sync/${sync_id}"
mkdir -p "$incoming_dir"
chmod 700 backups backups/sync "$incoming_dir"
production_dump="$incoming_dir/production.dump"
production_documents="$incoming_dir/production-documents.tar.gz"

fetch_database "$production_dump"
fetch_documents "$production_documents"
[[ -s "$production_dump" && -s "$production_documents" ]] || { echo "Archives de production vides." >&2; exit 1; }
"${compose[@]}" exec -T db pg_restore --list <"$production_dump" >/dev/null
tar --list --gzip --file "$production_documents" >/dev/null
(
    cd "$incoming_dir"
    sha256sum production.dump production-documents.tar.gz >manifest.sha256
)

CSRS_BACKUP_TIMESTAMP="$sync_id" ./scripts/backup_db.sh
rollback_dump="backups/csrs_${sync_id}.dump"
rollback_documents="backups/csrs_documents_${sync_id}.tar.gz"
[[ -s "$rollback_dump" && -s "$rollback_documents" ]] || { echo "Sauvegarde de retour arrière absente." >&2; exit 1; }
rollback_ready=1

"${compose[@]}" stop notifier web
services_stopped=1
restore_database "$production_dump"
restore_documents "$production_documents"
"${compose[@]}" up -d web
"${compose[@]}" stop notifier >/dev/null 2>&1 || true
wait_for_web
services_stopped=0

echo "SYNC_OK source=$production_ssh cible=preprod date=$sync_id"
