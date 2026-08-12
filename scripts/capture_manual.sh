#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

if ! command -v npm >/dev/null 2>&1; then
    echo "npm et Node 24 sont requis pour produire les captures." >&2
    exit 1
fi
if [[ -z "${CSRS_DEMO_PASSWORD:-}" ]]; then
    read -r -s -p "Mot de passe temporaire des comptes métier : " CSRS_DEMO_PASSWORD
    echo
fi
if [[ -z "${CSRS_ADMIN_PASSWORD:-}" ]]; then
    read -r -s -p "Mot de passe temporaire du compte dev : " CSRS_ADMIN_PASSWORD
    echo
fi
if [[ "$CSRS_DEMO_PASSWORD" == "$CSRS_ADMIN_PASSWORD" ]]; then
    echo "Les deux mots de passe temporaires doivent être différents." >&2
    exit 1
fi

runtime="$(mktemp -d /tmp/csrs-manual.XXXXXX)"
django_pid=""
vite_pid=""

cleanup() {
    status=$?
    if [[ -n "$vite_pid" ]]; then kill "$vite_pid" >/dev/null 2>&1 || true; fi
    if [[ -n "$django_pid" ]]; then kill "$django_pid" >/dev/null 2>&1 || true; fi
    wait "$vite_pid" >/dev/null 2>&1 || true
    wait "$django_pid" >/dev/null 2>&1 || true
    if [[ "$status" != "0" ]]; then
        echo "Dernières lignes de Django :" >&2
        tail -n 30 "$runtime/django.log" >&2 || true
        echo "Dernières lignes de Vite :" >&2
        tail -n 30 "$runtime/vite.log" >&2 || true
    fi
    rm -rf "$runtime"
    unset CSRS_DEMO_PASSWORD CSRS_ADMIN_PASSWORD
    exit "$status"
}
trap cleanup EXIT INT TERM

export CSRS_DEMO_PASSWORD CSRS_ADMIN_PASSWORD
export CSRS_SQLITE_PATH="$runtime/manual.sqlite3"
export DJANGO_SECRET_KEY="manual-screenshots-local-only"
export DJANGO_DEBUG=1
export DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost"
export DJANGO_CSRF_TRUSTED_ORIGINS="http://127.0.0.1:5173,http://localhost:5173"
export DJANGO_SECURE_SSL_REDIRECT=0
export EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
export PROCESS_DOCUMENT_ROOT="$runtime/private-media"
export PROCESS_DOCUMENT_SCAN_REQUIRED=0
export CSRS_MANUAL_BASE_URL="http://127.0.0.1:5173"
unset DATABASE_URL
mkdir -p "$PROCESS_DOCUMENT_ROOT"

PYENV_VERSION="${PYENV_VERSION:-csrs}" python manage.py migrate --noinput
PYENV_VERSION="${PYENV_VERSION:-csrs}" python manage.py seed_pilot_users --replace-legacy --reset-password

PYENV_VERSION="${PYENV_VERSION:-csrs}" python manage.py runserver 127.0.0.1:8000 --noreload >"$runtime/django.log" 2>&1 &
django_pid=$!
for _attempt in $(seq 1 30); do
    if curl --silent --fail http://127.0.0.1:8000/connexion/ >/dev/null; then break; fi
    sleep 1
done
curl --silent --fail http://127.0.0.1:8000/connexion/ >/dev/null

(
    cd frontend
    CSRS_DJANGO_URL="http://127.0.0.1:8000" npm run dev -- --host 127.0.0.1
) >"$runtime/vite.log" 2>&1 &
vite_pid=$!
for _attempt in $(seq 1 30); do
    if curl --silent --fail http://127.0.0.1:5173/app/ >/dev/null; then break; fi
    sleep 1
done
curl --silent --fail http://127.0.0.1:5173/app/ >/dev/null

(
    cd frontend
    npm run manual:screenshots
)

echo "Captures mises à jour dans docs/manual/screenshots/."
