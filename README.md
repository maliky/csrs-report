# CSRS Report

Application Django responsive de suivi hebdomadaire des tâches du Centre Suisse de Recherches Scientifiques en Côte d'Ivoire.

Le cycle métier est documenté dans [`docs/task-lifecycle.org`](docs/task-lifecycle.org) et son rendu [`docs/task-lifecycle.png`](docs/task-lifecycle.png).

## Développement local

Créer d'abord un environnement Python isolé. Python 3.13 est la version de
référence :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Si `pyenv` est installé, `.python-version` peut aussi activer l'environnement
`csrs`. Sans `DATABASE_URL`, Django utilise une base SQLite locale ignorée par
Git. `python manage.py seed_demo` ajoute uniquement des données fictives.

Contrôles :

```bash
pytest -m "not selenium"
pytest -m selenium
ruff format --check .
ruff check .
mypy accounts work config
python manage.py makemigrations --check --dry-run
```

## Interface React progressive

L'interface métier React est disponible sous `/app/`. Elle utilise la même
session Django et les mêmes autorisations serveur que l'interface classique,
qui reste accessible à la racine. L'administration Django continue de gérer
les comptes, services, rôles et délégations.

### Avec quoi React interagit

React n'accède jamais directement à PostgreSQL. Le parcours d'une action est :

```text
navigateur React (/app/)
  -> requête JSON /api/v1/
  -> session et protection CSRF Django
  -> vues API Django
  -> services métier work/ et access/
  -> base configurée (PostgreSQL en preproduction, SQLite local par défaut)
```

Django reste donc responsable de l'authentification, des permissions, des
règles métier, de l'audit et de la base. React présente les données et envoie
les actions autorisées. Le client conserve les cookies de session et transmet
le jeton CSRF pour les écritures. En preproduction, React, l'API et la page de
connexion sont servis par la même origine `https://psiaka.koba.sarl/`.

Les principaux points d'entrée sont `frontend/src/lib/api/` pour le client et
les types, `frontend/src/features/` pour les écrans métier, `api/urls.py` et
`api/views.py` pour l'API, puis `work/services.py` et `access/services.py` pour
les règles applicatives.

La navigation React utilise une barre latérale gauche. Elle est ouverte et
rétractable sur ordinateur, avec préférence conservée dans le navigateur, et
fermée par défaut sur téléphone. Dans le détail d'une tâche, déplacer le
curseur affiche un aperçu D3 sans modifier la base. Le bouton d'enregistrement
envoie ensuite la progression à Django; une baisse exige une observation. La
réponse serveur actualise le pourcentage, l'historique et le graphique sans
rechargement de page.

### Deux modes de développement React

Le frontend demande Node 24 (version indiquée dans `frontend/.node-version`) :

```bash
cd frontend
npm ci
npm run dev
npm test
npm run build-storybook
npm run build
```

Le serveur Vite transmet `/api/` à Django sur `127.0.0.1:8000`. Pour travailler
sur l'interface avec les scénarios fictifs sans démarrer Django :

```bash
cd frontend
VITE_USE_MOCKS=true npm run dev
```

Ce parcours avec les mocks est le moyen le plus rapide de travailler sur React.
Il ne nécessite aucun conteneur. Ouvrir impérativement
`http://127.0.0.1:5173/app/` : la racine `http://127.0.0.1:5173/` ne contient
pas l'application. Si Vite était déjà lancé, l'arrêter puis le redémarrer avec
la variable `VITE_USE_MOCKS=true`.

Sous PowerShell, la commande équivalente est :

```powershell
cd frontend
$env:VITE_USE_MOCKS = "true"
npm run dev
```

Il permet de modifier les composants et scénarios de `frontend/src/mocks/`,
mais ne valide ni les permissions réelles, ni les migrations, ni le backend.

Pour tester React contre le vrai backend, lancer la stack Docker sur le port
attendu par le proxy Vite dans un premier terminal :

```bash
CSRS_PORT=8000 docker compose -p csrs -f compose.yml up -d --build
```

Sous PowerShell :

```powershell
$env:CSRS_PORT = "8000"
docker compose -p csrs -f compose.yml up -d --build
```

Se connecter d'abord sur `http://127.0.0.1:8000/connexion/`, puis lancer Vite
sans mocks dans un second terminal :

```bash
cd frontend
npm run dev
```

Ouvrir ensuite `http://127.0.0.1:5173/app/`. Vite sert React et transmet les
requêtes `/api/` à Django dans le conteneur sur le port 8000.

Django peut aussi être lancé nativement, notamment pour déboguer le code
Python :

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Le contrat OpenAPI et les types TypeScript sont reproductibles :

```bash
pyenv activate csrs
python manage.py spectacular --file frontend/openapi.yml --validate
cd frontend
npm run types:generate
```

La compilation Docker est multi-étape : Node produit les fichiers React, puis
WhiteNoise les sert avec les autres fichiers statiques. Aucun changement Nginx
n'est nécessaire pour `/app/`.

## Git et preproduction psiaka

La branche de travail et de preproduction de l'étudiant est `psiaka`. La
branche `dev` reste la branche d'intégration : l'administrateur y fusionne les
changements validés après revue. Depuis la machine locale :

```bash
git clone ssh://psiaka@tuvs.koba.sarl/home/jil/git/csrs_report.git
cd csrs_report
git switch --track origin/psiaka
git pull --ff-only
# modifier et tester
git add .
git commit -m "description claire"
git push origin psiaka
```

Dans le compte serveur `psiaka`, mettre à jour la copie de preproduction :

```bash
cd /srv/apps/psiaka/app
git switch psiaka
git pull --ff-only
```

Ce pull actualise uniquement les fichiers dans le checkout. Il ne modifie pas
les conteneurs déjà en cours. Après revue du commit, l'administrateur lance :

```bash
cd /srv/apps/psiaka/app
./scripts/deploy_preprod.sh
```

Le script exécute `docker-compose up -d --build`. Docker réutilise ses couches
en cache. Si le frontend a changé, l'étape Node relance `npm run build`; elle ne
relance `npm ci` que si `package.json` ou `package-lock.json` a changé. Le bundle
produit est copié dans `static/react` de la nouvelle image, puis servi par le
conteneur web avec WhiteNoise. Aucune copie manuelle dans un conteneur en cours
n'est nécessaire.

Le site est publié sur `https://psiaka.koba.sarl/`. Le code Python et les
assets React sont intégrés dans l'image. Le compte `psiaka` n'est volontairement
pas membre du groupe `docker` : lui-même pousse et tire les commits, puis un
administrateur contrôle et exécute le déploiement.

Le développeur travaille et teste normalement sur sa machine, pousse ses
commits sur la branche `psiaka`, puis informe l'administrateur du serveur en
précisant le commit, les migrations éventuelles et les contrôles exécutés.
L'administrateur revoit les changements, actualise la preproduction depuis
`psiaka`, effectue le redéploiement puis fusionne les changements validés vers
`dev`. Une modification n'est donc pas visible sur le site public
immédiatement après le push. L'étudiant ne pousse pas directement sur `dev`.

Pour reprendre dans `psiaka` les changements ajoutés entre-temps à `dev` :

```bash
git fetch origin
git switch psiaka
git merge origin/dev
git push origin psiaka
```

La preproduction contient des comptes fictifs, notamment `dev`, `dg` et les
comptes de la hiérarchie pilote. Leurs mots de passe ne sont pas versionnés :
sur le serveur, ils sont indiqués dans le guide privé
`/home/psiaka/CSRS_README.org`. Ces identifiants sont réservés aux essais et ne
doivent jamais être réutilisés en production.

## Conteneurs et déploiement

```bash
./scripts/bootstrap_env.sh
./scripts/deploy_preprod.sh
./scripts/backup_db.sh
```

Le chargeur de population fictive exige temporairement deux variables distinctes, `CSRS_DEMO_PASSWORD` et `CSRS_ADMIN_PASSWORD`. Il accepte `--dry-run`, `--replace-legacy` et `--reset-password`. Ces variables ne doivent rester ni dans `.env` ni dans les conteneurs après le chargement.

`./scripts/seed_pilot.sh` demande les deux mots de passe sans les afficher, exécute d'abord une simulation annulée puis le chargement réel. L'option `--dry-run-only` limite le script à la simulation.

Pour actualiser uniquement les 73 scénarios et leurs conversations sur une base où les 16 comptes historiques existent déjà, sans créer les comptes d'extension ni demander ou modifier un mot de passe :

```bash
docker-compose -p "$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env)" -f compose.yml exec -T web python manage.py seed_pilot_users --refresh-scenarios-only
```

Par défaut, l'application écoute sur `127.0.0.1:18005`. La preproduction
`psiaka` utilise `CSRS_PORT=18006` et le projet `csrs_psiaka`. Les modèles de
vhost se trouvent dans `deploy/nginx/`. Les sauvegardes validées par
`pg_restore --list` sont conservées localement pendant 14 jours dans un dossier
ignoré par Git. Aucun secret ni donnée personnelle réelle ne doit être ajouté
au dépôt ou aux données de démonstration.
