#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

if [[ ! -f .env ]]; then
    echo ".env est requis; executer d'abord scripts/bootstrap_env.sh." >&2
    exit 1
fi

project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n 1)"
project="${project:-csrs}"
start_notifier="$(sed -n 's/^CSRS_START_NOTIFIER=//p' .env | tail -n 1)"
start_notifier="${start_notifier:-1}"

if [[ "$start_notifier" != "0" && "$start_notifier" != "1" ]]; then
    echo "CSRS_START_NOTIFIER doit valoir 0 ou 1." >&2
    exit 1
fi

if ! command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose est requis sur l'hote de deploiement." >&2
    exit 1
fi

services=(db clamav web)
if [[ "$start_notifier" == "1" ]]; then
    services+=(notifier)
fi

docker-compose -p "$project" -f compose.yml up -d --build "${services[@]}"
if [[ "$start_notifier" == "0" ]]; then
    docker-compose -p "$project" -f compose.yml stop notifier >/dev/null 2>&1 || true
fi
docker-compose -p "$project" -f compose.yml exec -T web python manage.py check --deploy
docker-compose -p "$project" -f compose.yml ps
