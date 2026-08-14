#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"
# shellcheck source=scripts/lib/compose.sh
source scripts/lib/compose.sh
csrs_compose_command

actor="dev"
reason=""
dry_run_only=0
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --actor)
            actor="${2:-}"
            shift 2
            ;;
        --reason)
            reason="${2:-}"
            shift 2
            ;;
        --dry-run-only)
            dry_run_only=1
            shift
            ;;
        *)
            echo "Option inconnue : $1" >&2
            echo "Usage : $0 [--actor ALIAS] [--reason MOTIF] [--dry-run-only]" >&2
            exit 2
            ;;
    esac
done

if [[ -z "$reason" ]]; then
    read -r -p "Motif de la reinitialisation : " reason
fi
if [[ ${#reason} -lt 3 ]]; then
    echo "Le motif doit contenir au moins 3 caracteres." >&2
    exit 2
fi
if [[ ! -f .env ]]; then
    echo ".env est requis pour identifier le projet Compose." >&2
    exit 1
fi

project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n 1)"
project="${project:-csrs}"
compose=("${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml)
command=(python manage.py reset_reporting_data --actor "$actor" --reason "$reason")
run=("${compose[@]}" run --rm -T web)

"${run[@]}" "${command[@]}" --dry-run
if [[ "$dry_run_only" == "1" ]]; then
    exit 0
fi

./scripts/backup_db.sh
read -r -p "Taper REINITIALISER pour confirmer : " confirmation
if [[ "$confirmation" != "REINITIALISER" ]]; then
    echo "Reinitialisation annulee; aucune donnee n'a ete supprimee."
    exit 1
fi

services_stopped=0
restore_services() {
    if [[ "$services_stopped" == "1" ]]; then
        "${compose[@]}" up -d web notifier >/dev/null
    fi
}
trap restore_services EXIT INT TERM

"${compose[@]}" stop notifier web
services_stopped=1
"${run[@]}" "${command[@]}" --confirm
"${compose[@]}" up -d web notifier
services_stopped=0

web_id="$("${compose[@]}" ps -q web)"
for _attempt in $(seq 1 24); do
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$web_id")"
    if [[ "$health" == "healthy" ]]; then
        echo "Reinitialisation terminee; service web sain."
        exit 0
    fi
    sleep 5
done
echo "La reinitialisation est terminee, mais le service web n'est pas sain." >&2
exit 1
