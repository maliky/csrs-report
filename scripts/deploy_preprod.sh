#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"
# shellcheck source=scripts/lib/compose.sh
source scripts/lib/compose.sh
csrs_compose_command

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

services=(db clamav web)
if [[ "$start_notifier" == "1" ]]; then
    services+=(notifier)
fi

revision="$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"
if ! git diff --quiet || ! git diff --cached --quiet; then
    revision="dirty-${revision}"
fi
export CSRS_GIT_SHA="$revision"

"${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml up -d --build "${services[@]}"
if [[ "$start_notifier" == "0" ]]; then
    "${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml stop notifier >/dev/null 2>&1 || true
fi
"${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml exec -T web python manage.py check --deploy
"${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml ps
echo "Revision de l'image : $revision"
