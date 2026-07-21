#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CSRS_DEMO_PASSWORD:-}" ]]; then
    read -r -s -p "Mot de passe des comptes metier : " CSRS_DEMO_PASSWORD
    echo
fi
if [[ -z "${CSRS_ADMIN_PASSWORD:-}" ]]; then
    read -r -s -p "Mot de passe du compte dev : " CSRS_ADMIN_PASSWORD
    echo
fi
export CSRS_DEMO_PASSWORD CSRS_ADMIN_PASSWORD
trap 'unset CSRS_DEMO_PASSWORD CSRS_ADMIN_PASSWORD' EXIT

project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n 1)"
project="${project:-csrs}"
base=(docker-compose -p "$project" -f compose.yml run --rm -T)
environment=(-e CSRS_DEMO_PASSWORD -e CSRS_ADMIN_PASSWORD)
command=(web python manage.py seed_pilot_users --replace-legacy --reset-password)

"${base[@]}" "${environment[@]}" "${command[@]}" --dry-run
if [[ "${1:-}" != "--dry-run-only" ]]; then
    "${base[@]}" "${environment[@]}" "${command[@]}"
fi
