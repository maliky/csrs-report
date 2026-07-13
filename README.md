# CSRS Report

Application Django responsive de suivi hebdomadaire des tâches du Centre Suisse de Recherches Scientifiques en Côte d'Ivoire.

Le cycle métier est documenté dans [`docs/task-lifecycle.puml`](docs/task-lifecycle.puml) et son rendu [`docs/task-lifecycle.svg`](docs/task-lifecycle.svg).

## Développement local

```bash
pyenv activate csrs
python -m pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Le virtualenv `csrs` utilise Python 3.13.2 et `.python-version` l'active automatiquement dans ce dépôt. Sans `DATABASE_URL`, Django utilise une base SQLite locale ignorée par Git. `python manage.py seed_demo` ajoute uniquement des comptes et tâches fictifs, sans mot de passe utilisable.

Contrôles :

```bash
pytest -m "not selenium"
pytest -m selenium
ruff format --check .
ruff check .
mypy accounts work config
python manage.py makemigrations --check --dry-run
```

## Conteneurs et déploiement

```bash
./scripts/bootstrap_env.sh
docker-compose -p csrs -f compose.yml up -d --build
docker-compose -p csrs -f compose.yml exec web python manage.py createsuperuser
./scripts/backup_db.sh
```

Le chargeur de population fictive exige temporairement deux variables distinctes, `CSRS_DEMO_PASSWORD` et `CSRS_ADMIN_PASSWORD`. Il accepte `--dry-run`, `--replace-legacy` et `--reset-password`. Ces variables ne doivent rester ni dans `.env` ni dans les conteneurs après le chargement.

`./scripts/seed_pilot.sh` demande les deux mots de passe sans les afficher, exécute d'abord une simulation annulée puis le chargement réel. L'option `--dry-run-only` limite le script à la simulation.

L'application écoute uniquement sur `127.0.0.1:18005`. Le modèle du vhost HTTPS se trouve dans `deploy/nginx/`. Les sauvegardes validées par `pg_restore --list` sont conservées localement pendant 14 jours dans un dossier ignoré par Git. Aucun secret ni donnée personnelle réelle ne doit être ajouté au dépôt ou aux données de démonstration.
