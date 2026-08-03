#!/usr/bin/env bash
set -euo pipefail

if [[ -e .env ]]; then
    echo ".env existe deja; aucun secret n'a ete remplace."
    exit 0
fi

python_command="${PYTHON:-python3}"
host="${CSRS_HOST:-csrs.koba.sarl}"
bind_address="${CSRS_BIND_ADDRESS:-127.0.0.1}"
port="${CSRS_PORT:-18005}"
project="${COMPOSE_PROJECT_NAME:-csrs}"
start_notifier="${CSRS_START_NOTIFIER:-1}"

if [[ "$start_notifier" != "0" && "$start_notifier" != "1" ]]; then
    echo "CSRS_START_NOTIFIER doit valoir 0 ou 1." >&2
    exit 1
fi

secret_key="$(${python_command} -c 'import secrets; print(secrets.token_urlsafe(50))')"
db_password="$(${python_command} -c 'import secrets; print(secrets.token_urlsafe(32))')"

umask 077
{
    echo "COMPOSE_PROJECT_NAME=${project}"
    echo "CSRS_BIND_ADDRESS=${bind_address}"
    echo "CSRS_PORT=${port}"
    echo "CSRS_HOST=${host}"
    echo "CSRS_START_NOTIFIER=${start_notifier}"
    echo "DJANGO_SECRET_KEY=${secret_key}"
    echo "DJANGO_DEBUG=0"
    echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,${host}"
    echo "DJANGO_CSRF_TRUSTED_ORIGINS=https://${host}"
    echo "DJANGO_SECURE_SSL_REDIRECT=1"
    echo "DJANGO_SECURE_HSTS_SECONDS=3600"
    echo "POSTGRES_DB=csrs"
    echo "POSTGRES_USER=csrs"
    echo "POSTGRES_PASSWORD=${db_password}"
    echo "EMAIL_HOST=mail.koba.sarl"
    echo "EMAIL_PORT=587"
    echo "EMAIL_HOST_USER="
    echo "EMAIL_HOST_PASSWORD="
    echo "EMAIL_USE_TLS=1"
    echo "DEFAULT_FROM_EMAIL=CSRS Report <noreply@koba.sarl>"
    echo "PROCESS_DOCUMENT_BACKEND=local"
    echo "PROCESS_DOCUMENT_ROOT=/private-media"
    echo "PROCESS_DOCUMENT_MAX_BYTES=20971520"
    echo "PROCESS_DOCUMENT_SCAN_REQUIRED=1"
    echo "CLAMAV_HOST=clamav"
    echo "CLAMAV_PORT=3310"
    echo "CLAMAV_TIMEOUT_SECONDS=15"
} > .env

echo ".env cree avec des secrets locaux et des permissions restrictives."
