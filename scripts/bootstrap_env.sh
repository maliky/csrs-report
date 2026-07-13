#!/usr/bin/env bash
set -euo pipefail

if [[ -e .env ]]; then
    echo ".env existe deja; aucun secret n'a ete remplace."
    exit 0
fi

secret_key="$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')"
db_password="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

umask 077
{
    echo "DJANGO_SECRET_KEY=${secret_key}"
    echo "DJANGO_DEBUG=0"
    echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,csrs.koba.sarl"
    echo "DJANGO_CSRF_TRUSTED_ORIGINS=https://csrs.koba.sarl"
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
