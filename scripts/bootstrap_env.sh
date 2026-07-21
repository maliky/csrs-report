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
secret_key="$(${python_command} -c 'import secrets; print(secrets.token_urlsafe(50))')"
db_password="$(${python_command} -c 'import secrets; print(secrets.token_urlsafe(32))')"

umask 077
{
    echo "COMPOSE_PROJECT_NAME=${project}"
    echo "CSRS_BIND_ADDRESS=${bind_address}"
    echo "CSRS_PORT=${port}"
    echo "CSRS_HOST=${host}"
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
} > .env

echo ".env cree avec des secrets locaux et des permissions restrictives."
