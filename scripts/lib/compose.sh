#!/usr/bin/env bash

csrs_compose_command() {
    if docker compose version >/dev/null 2>&1; then
        CSRS_COMPOSE=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        CSRS_COMPOSE=(docker-compose)
    else
        echo "Docker Compose v2 ou docker-compose v1 est requis." >&2
        return 1
    fi
}
