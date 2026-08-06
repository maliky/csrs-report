#!/usr/bin/env bash
set -euo pipefail

dry_run_only=0
clean_accounts=0
for argument in "$@"; do
    case "$argument" in
        --dry-run-only) dry_run_only=1 ;;
        --clean-accounts) clean_accounts=1 ;;
        *)
            echo "Option inconnue : $argument" >&2
            echo "Usage : $0 [--dry-run-only] [--clean-accounts]" >&2
            exit 2
            ;;
    esac
done

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
base=(docker compose -p "$project" -f compose.yml run --rm -T)
environment=(-e CSRS_DEMO_PASSWORD -e CSRS_ADMIN_PASSWORD)
command=(web python manage.py seed_pilot_users --replace-legacy --reset-password)
if [[ "$clean_accounts" == "1" ]]; then
    command+=(--prune-noncanonical-users)
fi

"${base[@]}" "${environment[@]}" "${command[@]}" --dry-run
if [[ "$dry_run_only" == "0" ]]; then
    if [[ "$clean_accounts" == "1" ]]; then
        ./scripts/backup_db.sh
        read -r -p "Taper SUPPRIMER pour confirmer la purge des comptes non canoniques : " confirmation
        if [[ "$confirmation" != "SUPPRIMER" ]]; then
            echo "Purge annulee; aucune modification n'a ete appliquee."
            exit 1
        fi
        command+=(--confirm-prune)
    fi
    "${base[@]}" "${environment[@]}" "${command[@]}"
fi
