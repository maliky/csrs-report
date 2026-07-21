# CSRS Report

Application Django responsive de suivi hebdomadaire des tâches du Centre Suisse
de Recherches Scientifiques en Côte d'Ivoire.

Le cycle métier est documenté dans
[`docs/task-lifecycle.org`](docs/task-lifecycle.org) et son rendu
[`docs/task-lifecycle.png`](docs/task-lifecycle.png).

## Stack Docker — parcours recommandé

Docker Compose démarre toute l'application :

| Service | Rôle |
| --- | --- |
| `db` | PostgreSQL 17 avec volume persistant |
| `web` | Django, migrations, fichiers statiques et Gunicorn |
| `notifier` | traitement périodique des notifications |

Le service Django se connecte automatiquement à PostgreSQL par le nom Compose
`db`. Il n'est pas nécessaire de lancer `manage.py runserver`.

### Prérequis

Sous Linux, installer Docker Engine et **Docker Compose v2**. Sur Ubuntu 24.04 :

```bash
sudo apt update
sudo apt install git docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
newgrp docker
docker compose version
```

Utiliser `docker compose` avec une espace, et non l'ancien `docker-compose`.

Sous Windows, installer Docker Desktop avec le moteur WSL2, activer
l'intégration avec une distribution Ubuntu, puis exécuter les commandes du
projet depuis le terminal WSL. Conserver de préférence le dépôt dans le système
de fichiers Linux, par exemple `~/CSRS/csrs_report`.

### 1. Configurer l'environnement

Depuis la racine du dépôt :

```bash
cp .env.example .env
chmod 600 .env
```

Dans `.env`, remplacer au minimum `DJANGO_SECRET_KEY` et `POSTGRES_PASSWORD`
par des secrets locaux. Pour un accès HTTP de développement, utiliser :

```dotenv
DJANGO_DEBUG=1
DJANGO_SECURE_SSL_REDIRECT=0
DJANGO_SECURE_HSTS_SECONDS=0
```

Le fichier `.env` ne doit jamais être ajouté à Git.

### 2. Démarrer le stack complet

```bash
docker compose -p csrs -f compose.yml up -d --build
docker compose -p csrs -f compose.yml ps
```

Attendre que `db` et `web` soient sains, puis ouvrir :

<http://127.0.0.1:18005/connexion/>

### 3. Charger les données d'illustration

```bash
./scripts/seed_pilot.sh
```

Le script demande un mot de passe pour les comptes métier et un mot de passe
distinct pour l'administrateur `dev`. Il exécute une simulation, puis charge 45
utilisateurs, 73 affectations et 42 propositions.

Se connecter avec l'alias `dg` et le mot de passe métier, ou avec `dev` et le
mot de passe administrateur. Les mots de passe ne sont pas conservés par le
script.

Le chargement utilise un conteneur Django ponctuel ; la commande `up -d` reste
nécessaire pour maintenir le site en fonctionnement.

## Commandes utiles

```bash
# Etat des services
docker compose -p csrs -f compose.yml ps

# Journaux Django
docker compose -p csrs -f compose.yml logs -f web

# Reconstruire après une modification
docker compose -p csrs -f compose.yml up -d --build

# Arrêter le stack en conservant la base
docker compose -p csrs -f compose.yml down

# Sauvegarder PostgreSQL
./scripts/backup_db.sh
```

Ne pas utiliser `docker compose down -v` sauf pour supprimer volontairement la
base de développement.

Pour actualiser uniquement les scénarios existants sans modifier les mots de
passe :

```bash
docker compose -p csrs -f compose.yml exec -T web \
  python manage.py seed_pilot_users --refresh-scenarios-only
```

## Développement natif — note

Le mode natif utilise SQLite par défaut et ne se connecte pas automatiquement au
PostgreSQL de Compose. Python 3.13 est la version de référence.

Sous Linux :

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

Sous Windows PowerShell :

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Puis :

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Le serveur natif est disponible sur <http://127.0.0.1:8000/>.

## Contrôles de développement

```bash
python -m pytest -m "not selenium"
python -m pytest -m selenium
python -m ruff format --check .
python -m ruff check .
python -m mypy accounts work config
python manage.py makemigrations --check --dry-run
```

## Déploiement HTTPS

Le modèle Nginx de `deploy/nginx/` publie Gunicorn à l'adresse
`https://csrs.koba.sarl` tout en conservant le port applicatif sur
`127.0.0.1:18005`. En production, utiliser `DJANGO_DEBUG=0`,
`DJANGO_SECURE_SSL_REDIRECT=1` et des secrets distincts du développement.
