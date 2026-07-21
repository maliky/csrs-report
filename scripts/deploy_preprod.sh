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

if ! command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose est requis sur l'hote de deploiement." >&2
    exit 1
fi

docker-compose -p "$project" -f compose.yml up -d --build
docker-compose -p "$project" -f compose.yml exec -T web python manage.py check --deploy
docker-compose -p "$project" -f compose.yml ps
