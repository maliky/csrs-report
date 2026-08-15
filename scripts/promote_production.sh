#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
production_ssh="${CSRS_PRODUCTION_SSH:-jil@179.237.107.40}"
production_path="${CSRS_PRODUCTION_PATH:-/home/jil/csrs_report}"
minimum_free_kb="${CSRS_DEPLOY_MIN_FREE_KB:-4194304}"
mode="check"
candidate=""
previous_commit=""
previous_image=""
previous_image_name=""

usage() {
    cat <<'EOF'
Usage:
  scripts/promote_production.sh --candidate SHA --check
  scripts/promote_production.sh --candidate SHA --apply

La commande publique se lance depuis /srv/apps/csrs-preprod/app sur
54.36.60.51. --check ne modifie ni main ni la production. --apply exige une
confirmation, avance main uniquement en fast-forward, sauvegarde la production
et redeploie web par SSH.
EOF
}

die() {
    echo "ERREUR: $*" >&2
    exit 1
}

env_value() {
    local path="$1"
    local name="$2"
    sed -n "s/^${name}=//p" "$path" | tail -n 1
}

require_sha() {
    [[ "$candidate" =~ ^[0-9a-f]{40}$ ]] || die "--candidate doit etre un SHA Git complet de 40 caracteres."
}

require_clean_checkout() {
    [[ -z "$(git status --porcelain)" ]] || die "Le checkout Git doit etre propre."
}

wait_for_healthy() {
    local container_id="$1"
    local attempt status
    for ((attempt = 1; attempt <= 30; attempt++)); do
        status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
        if [[ "$status" == "healthy" ]]; then
            return 0
        fi
        if [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]]; then
            return 1
        fi
        sleep 4
    done
    return 1
}

production_preflight() {
    ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$production_ssh" \
        bash -s -- "$production_path" "$candidate" "$minimum_free_kb" <<'REMOTE'
set -euo pipefail
path="$1"
candidate="$2"
minimum_free_kb="$3"
cd "$path"

[[ -f .env ]] || { echo "ERREUR: .env de production absent." >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "ERREUR: checkout de production non propre." >&2; exit 1; }

env_value() { sed -n "s/^$2=//p" "$1" | tail -n 1; }
project="$(env_value .env COMPOSE_PROJECT_NAME)"
port="$(env_value .env CSRS_PORT)"
host="$(env_value .env CSRS_HOST)"
start_notifier="$(env_value .env CSRS_START_NOTIFIER)"
[[ "$project" == "csrs" ]] || { echo "ERREUR: projet Compose de production inattendu: $project" >&2; exit 1; }
[[ "$port" == "18005" ]] || { echo "ERREUR: port de production inattendu: $port" >&2; exit 1; }
[[ "$host" == "179.237.107.40" ]] || { echo "ERREUR: hote de production inattendu: $host" >&2; exit 1; }
[[ "$start_notifier" == "0" ]] || { echo "ERREUR: CSRS_START_NOTIFIER doit rester a 0 en production." >&2; exit 1; }

available_kb="$(df -Pk "$path" | awk 'NR == 2 {print $4}')"
[[ "$available_kb" =~ ^[0-9]+$ ]] && (( available_kb >= minimum_free_kb )) || {
    echo "ERREUR: espace libre insuffisant pour construire la release." >&2
    exit 1
}

docker compose version >/dev/null
web_id="$(docker compose -p "$project" -f compose.yml ps -q web)"
[[ -n "$web_id" ]] || { echo "ERREUR: conteneur web de production absent." >&2; exit 1; }
health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$web_id")"
[[ "$health" == "healthy" ]] || { echo "ERREUR: production non saine: $health" >&2; exit 1; }

remote_candidate="$(git ls-remote origin refs/heads/preprod | awk '{print $1}')"
[[ "$remote_candidate" == "$candidate" ]] || {
    echo "ERREUR: origin/preprod ne correspond plus au candidat." >&2
    exit 1
}

echo "PRODUCTION_PREFLIGHT_OK project=$project port=$port free_kb=$available_kb current=$(git rev-parse HEAD)"
REMOTE
}

rollback_web() {
    local -n compose_ref=$1
    echo "Le nouveau service web est invalide; restauration de l'image precedente." >&2
    docker image tag "$previous_image" "$previous_image_name"
    "${compose_ref[@]}" up -d --no-deps --force-recreate web
    local rollback_id
    rollback_id="$("${compose_ref[@]}" ps -q web)"
    wait_for_healthy "$rollback_id" || die "La restauration automatique du service web a echoue."
    echo "ROLLBACK_WEB_OK image=$previous_image"
}

post_deploy_checks() {
    local -n compose_ref=$1
    local web_id running_revision migration_output api_code
    web_id="$("${compose_ref[@]}" ps -q web)"
    running_revision="$(docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$web_id")"
    [[ "$running_revision" == "$candidate" ]] || return 1

    "${compose_ref[@]}" exec -T web python manage.py check --deploy
    migration_output="$("${compose_ref[@]}" exec -T web python manage.py showmigrations --plan)"
    if grep -F '[ ]' <<<"$migration_output"; then
        echo "Des migrations restent non appliquees." >&2
        return 1
    fi

    curl --fail --silent --show-error --location --max-redirs 3 --output /dev/null https://179.237.107.40/app/
    curl --fail --silent --show-error --location --max-redirs 3 --output /dev/null https://csrs.koba.sarl/app/
    curl --fail --silent --show-error --output /dev/null https://179.237.107.40/static/react/assets/app.js
    api_code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' https://179.237.107.40/api/v1/session/)"
    [[ "$api_code" == "401" ]] || {
        echo "Le controle de session anonyme attendait HTTP 401 et a recu $api_code." >&2
        return 1
    }
}

deploy_target() {
    [[ "${CSRS_DEPLOY_LOCK_HELD:-}" == "1" ]] || die "Le mode interne --deploy-target exige le verrou de l'orchestrateur."
    require_sha
    [[ -n "$previous_commit" && -n "$previous_image" && -n "$previous_image_name" ]] || die "Informations de restauration incompletes."
    cd "$repo"
    require_clean_checkout
    [[ "$(git rev-parse HEAD)" == "$candidate" ]] || die "Le checkout de production n'est pas au SHA attendu."
    [[ "$(git branch --show-current)" == "main" ]] || die "Le checkout de production doit etre sur main."

    # shellcheck source=scripts/lib/compose.sh
    source scripts/lib/compose.sh
    csrs_compose_command
    project="$(env_value .env COMPOSE_PROJECT_NAME)"
    start_notifier="$(env_value .env CSRS_START_NOTIFIER)"
    [[ "$project" == "csrs" ]] || die "Projet Compose inattendu: $project"
    [[ "$start_notifier" == "0" || "$start_notifier" == "1" ]] || die "CSRS_START_NOTIFIER invalide."
    compose=("${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml)

    rollback_tag="csrs-web:rollback-$(date -u +%Y%m%dT%H%M%SZ)"
    docker image tag "$previous_image" "$rollback_tag"
    export CSRS_GIT_SHA="$candidate"

    build_services=(web)
    if [[ "$start_notifier" == "1" ]]; then
        build_services+=(notifier)
    fi
    "${compose[@]}" build "${build_services[@]}"

    built_image="$("${compose[@]}" images -q web | head -n 1)"
    [[ -n "$built_image" ]] || die "Image web construite introuvable."
    built_revision="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$built_image")"
    [[ "$built_revision" == "$candidate" ]] || die "L'image construite ne porte pas le SHA attendu."

    "${compose[@]}" run --rm --no-deps web python manage.py check --deploy
    "${compose[@]}" run --rm --no-deps web python manage.py migrate --plan

    if ! "${compose[@]}" up -d --no-deps --force-recreate web; then
        rollback_web compose
        die "La recreation du service web a echoue."
    fi
    web_id="$("${compose[@]}" ps -q web)"
    if ! wait_for_healthy "$web_id"; then
        rollback_web compose
        die "Le nouveau service web n'est pas devenu sain."
    fi

    if [[ "$start_notifier" == "1" ]]; then
        "${compose[@]}" up -d --no-deps --force-recreate notifier
    else
        "${compose[@]}" stop notifier >/dev/null 2>&1 || true
    fi

    if ! post_deploy_checks compose; then
        rollback_web compose
        die "Les controles post-deploiement ont echoue."
    fi

    mkdir -p backups/deployments
    chmod 700 backups/deployments
    backup_manifest="$(find backups -maxdepth 1 -type f -name 'csrs_*.sha256' -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"
    log_path="backups/deployments/$(date -u +%Y%m%dT%H%M%SZ)-${candidate:0:12}.log"
    printf 'candidate=%s\nprevious_commit=%s\nprevious_image=%s\nrollback_tag=%s\nbackup_manifest=%s\n' \
        "$candidate" "$previous_commit" "$previous_image" "$rollback_tag" "$backup_manifest" >"$log_path"
    chmod 600 "$log_path"
    echo "DEPLOYMENT_OK candidate=$candidate previous=$previous_commit log=$log_path"
}

while (($#)); do
    case "$1" in
        --candidate)
            (($# >= 2)) || die "Valeur manquante pour --candidate."
            candidate="$2"
            shift 2
            ;;
        --check)
            mode="check"
            shift
            ;;
        --apply)
            mode="apply"
            shift
            ;;
        --deploy-target)
            mode="deploy-target"
            shift
            ;;
        --previous-commit)
            previous_commit="$2"
            shift 2
            ;;
        --previous-image)
            previous_image="$2"
            shift 2
            ;;
        --previous-image-name)
            previous_image_name="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "Option inconnue: $1"
            ;;
    esac
done

if [[ "$mode" == "deploy-target" ]]; then
    deploy_target
    exit 0
fi

require_sha
cd "$repo"
require_clean_checkout
git fetch origin \
    '+refs/heads/main:refs/remotes/origin/main' \
    '+refs/heads/preprod:refs/remotes/origin/preprod'

[[ "$(git branch --show-current)" == "preprod" ]] || die "La promotion publique doit etre lancee depuis la branche preprod."
[[ "$(git rev-parse HEAD)" == "$candidate" ]] || die "HEAD ne correspond pas au candidat."
[[ "$(git rev-parse origin/preprod)" == "$candidate" ]] || die "origin/preprod ne correspond pas au candidat."
git merge-base --is-ancestor origin/main "$candidate" || die "main ne peut pas avancer en fast-forward vers ce candidat."
git diff --check origin/main.."$candidate"

if git grep -n -E '^(<<<<<<<|=======|>>>>>>>)' "$candidate" -- '*.org' '*.md'; then
    die "Des marqueurs de conflit subsistent dans la documentation."
fi
if git ls-tree -r --name-only "$candidate" | grep -E '(^|/)Exports/.*\.html$'; then
    die "Un export HTML genere est encore suivi par Git."
fi

[[ -f .env ]] || die ".env de preproduction absent."
project="$(env_value .env COMPOSE_PROJECT_NAME)"
port="$(env_value .env CSRS_PORT)"
host="$(env_value .env CSRS_HOST)"
[[ "$project" == "csrs_preprod" ]] || die "Projet de preproduction inattendu: $project"
[[ "$port" == "18008" ]] || die "Port de preproduction inattendu: $port"
[[ "$host" == "preprod.report.ent.koba.sarl" ]] || die "Hote de preproduction inattendu: $host"

# shellcheck source=scripts/lib/compose.sh
source scripts/lib/compose.sh
csrs_compose_command
source_compose=("${CSRS_COMPOSE[@]}" -p "$project" -f compose.yml)
source_web_id="$("${source_compose[@]}" ps -q web)"
[[ -n "$source_web_id" ]] || die "Conteneur web de preproduction absent."
source_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$source_web_id")"
[[ "$source_health" == "healthy" ]] || die "Preproduction non saine: $source_health"
source_revision="$(docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$source_web_id")"
[[ "$source_revision" == "$candidate" ]] || die "L'image de preproduction ne porte pas le SHA candidat."
curl --fail --silent --show-error --location --max-redirs 3 --output /dev/null "https://${host}/app/"

production_preflight

echo
echo "=== COMMITS A PROMOUVOIR ==="
git log --oneline origin/main.."$candidate"
echo
echo "=== RESUME DES FICHIERS ==="
git diff --stat origin/main.."$candidate"
echo
echo "=== MIGRATIONS ==="
git diff --name-only origin/main.."$candidate" | grep '/migrations/.*\.py$' || echo "Aucune migration."
echo
echo "CANDIDAT_PRET sha=$candidate preprod=https://${host}/ production=$production_ssh:$production_path"

if [[ "$mode" == "check" ]]; then
    echo "CHECK_ONLY_OK aucune branche distante ni service de production n'a ete modifie."
    exit 0
fi

expected_confirmation="PROMOUVOIR ${candidate:0:12}"
read -r -p "Saisir '${expected_confirmation}' pour continuer: " confirmation
[[ "$confirmation" == "$expected_confirmation" ]] || die "Confirmation incorrecte; promotion annulee."

git push origin "$candidate:refs/heads/main"

deployment_output="$(mktemp)"
trap 'rm -f "$deployment_output"' EXIT
set +e
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$production_ssh" \
    bash -s -- "$production_path" "$candidate" <<'REMOTE' | tee "$deployment_output"
set -euo pipefail
path="$1"
candidate="$2"
exec 9>/tmp/csrs-production-deploy.lock
flock -n 9 || { echo "ERREUR: un autre deploiement CSRS est en cours." >&2; exit 1; }
cd "$path"
[[ -z "$(git status --porcelain)" ]] || { echo "ERREUR: checkout de production non propre." >&2; exit 1; }

previous_commit="$(git rev-parse HEAD)"
project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n 1)"
web_id="$(docker compose -p "$project" -f compose.yml ps -q web)"
previous_image="$(docker inspect --format '{{.Image}}' "$web_id")"
previous_image_name="$(docker inspect --format '{{.Config.Image}}' "$web_id")"

echo "REMOTE_BACKUP_START"
./scripts/backup_db.sh </dev/null
echo "REMOTE_BACKUP_OK"
echo "REMOTE_GIT_SYNC_START"
git fetch origin refs/heads/main:refs/remotes/origin/main
[[ "$(git rev-parse origin/main)" == "$candidate" ]] || {
    echo "ERREUR: origin/main ne correspond pas au candidat apres promotion." >&2
    exit 1
}
git switch main
git merge --ff-only origin/main
[[ "$(git rev-parse HEAD)" == "$candidate" ]] || { echo "ERREUR: main local incorrect." >&2; exit 1; }
echo "REMOTE_GIT_SYNC_OK"
echo "REMOTE_DEPLOY_START"

CSRS_DEPLOY_LOCK_HELD=1 exec ./scripts/promote_production.sh \
    --deploy-target \
    --candidate "$candidate" \
    --previous-commit "$previous_commit" \
    --previous-image "$previous_image" \
    --previous-image-name "$previous_image_name"
REMOTE
deployment_status="${PIPESTATUS[0]}"
set -e
if ((deployment_status != 0)); then
    die "Le deploiement distant a echoue avec le statut $deployment_status."
fi
grep -F "DEPLOYMENT_OK candidate=$candidate " "$deployment_output" >/dev/null || \
    die "Le deploiement distant n'a pas emis le marqueur de succes attendu."
rm -f "$deployment_output"
trap - EXIT

tag="production-$(date -u +%Y%m%dT%H%M%SZ)"
if git tag -a "$tag" "$candidate" -m "Production CSRS $candidate" && git push origin "refs/tags/$tag"; then
    echo "TAG_PRODUCTION_OK $tag"
else
    echo "AVERTISSEMENT: le deploiement a reussi mais le tag $tag n'a pas pu etre publie." >&2
fi
echo "PROMOTION_OK main=$candidate production=$candidate"
