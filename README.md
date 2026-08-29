# CSRS Report

Application Django responsive de suivi hebdomadaire des tâches du Centre Suisse de Recherches Scientifiques en Côte d'Ivoire.

Le [manuel utilisateur illustré](docs/MANUAL.org) factorise les procédures communes et décrit les parcours d'un collaborateur, d'un responsable intermédiaire, de la Direction générale, du secrétariat, des RH et de l'administrateur de l'organigramme.

## Stack Docker — parcours recommandé

Docker Compose démarre toute l'application :

| Service | Rôle |
| --- | --- |
| `db` | PostgreSQL 17 avec volume persistant |
| `web` | Django, migrations, fichiers statiques et Gunicorn |
| `notifier` | traitement périodique des notifications |

Le service Django se connecte automatiquement à PostgreSQL par le nom Compose `db`. Il n'est pas nécessaire de lancer `manage.py runserver`.

### Prérequis

Sous Linux, installer Docker Engine et **Docker Compose v2**, puis contrôler leur disponibilité :

```bash
docker --version
docker compose version
```

Depuis un clone neuf, initialiser la configuration locale puis démarrer les services :

```bash
./scripts/bootstrap_env.sh
docker compose -p csrs -f compose.yml up -d --build
```

Le script de bootstrap refuse d'écraser un fichier `.env` existant. Le port local par défaut est `127.0.0.1:18005`.

### Environnement Python local facultatif

Pour exécuter les contrôles ou déboguer Django sans conteneur, créer un environnement Python isolé. Python 3.13 est la version de référence :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Si `pyenv` est installé, `.python-version` peut aussi activer l'environnement `csrs`. Sans `DATABASE_URL`, Django utilise une base SQLite locale ignorée par Git. `python manage.py seed_demo` ajoute uniquement des données fictives.

## Contrôles de développement

```bash
python -m pytest -m "not selenium"
python -m pytest -m selenium
python -m ruff format --check .
python -m ruff check .
python -m mypy accounts work config
python manage.py makemigrations --check --dry-run
```

## Interface React principale

L'interface métier React est disponible sous `/app/` et constitue l'interface par défaut. La racine `/`, la connexion et l'activation d'un compte y conduisent automatiquement. Elle utilise la même session Django et les mêmes autorisations serveur que l'interface classique, dont le point d'entrée de secours reste disponible sous `/classique/`. L'administration Django continue de gérer les comptes, services, rôles et délégations.

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

Django reste donc responsable de l'authentification, des permissions, des règles métier, de l'audit et de la base. React présente les données et envoie les actions autorisées. Le client conserve les cookies de session et transmet le jeton CSRF pour les écritures. Le déploiement public CSRS sert React, l'API et la connexion sur la même origine à `https://csrs.koba.sarl/` et `https://179.237.107.40/`. La préproduction de release est séparée à `https://preprod.report.ent.koba.sarl/`.

Les principaux points d'entrée sont `frontend/src/lib/api/` pour le client et les types, `frontend/src/features/` pour les écrans métier, `api/urls.py` et `api/views.py` pour l'API, puis `work/services.py` et `access/services.py` pour les règles applicatives.

La navigation React utilise une barre latérale gauche. Elle est ouverte et rétractable sur ordinateur, avec préférence conservée dans le navigateur, et fermée par défaut sur téléphone. Dans le détail d'une tâche, déplacer le curseur affiche un aperçu D3 sans modifier la base. Le bouton d'enregistrement envoie ensuite la progression à Django; une baisse exige une observation. La réponse serveur actualise le pourcentage, l'historique et le graphique sans rechargement de page.

Le dashboard `/app/propositions` filtre par statut, collaborateur et période chevauchante. Une proposition validée mène à la progression de la tâche créée; une proposition soumise ou rejetée mène à son détail. L'auteur peut corriger ses propositions et resoumettre un rejet, tandis que les décisions restent réservées aux responsables autorisés. Les écritures utilisent toujours une révision optimiste et les erreurs API gardent une enveloppe JSON stable.

La synthèse `/app/equipe` reprend l'arbre dépliable de l'interface classique. Les branches du premier niveau sont ouvertes à l'arrivée et chargent une seule fois leurs tâches; les niveaux inférieurs restent fermés jusqu'à leur ouverture explicite. Les titres mènent au détail de progression. Le filtre segmenté `Tous / Avec tâches / Sans tâche` porte sur les tâches propres à chaque personne pour la période sélectionnée et conserve les ancêtres nécessaires à la lecture de la hiérarchie. Son état est conservé dans l'URL avec `tasks=with` ou `tasks=without`, y compris lors d'un changement de semaine ou de mois.

### Agendas de direction par période

Le compte fictif `secretariat_dg` ouvre `/app/agenda`, choisit une période inclusive de 31 jours maximum dans un calendrier unique, notifie l’arrivée d’un groupe de visiteurs avec un nombre obligatoire et des noms facultatifs, puis marque son départ. La période proposée par défaut est la semaine suivante. Un seul sélecteur `Direction de l’agenda` pilote l’aperçu et l’unique bouton `Générer le PDF`; le secrétariat produit ainsi séparément le rapport de la Direction des programmes et celui de la Direction administrative. Le DG peut consulter et réimprimer les versions archivées sans modifier le brouillon.

Le compte `rh` ouvre `/app/absences` et enregistre les congés, absences et missions avec l’agent et la période concernée. Les RH n’accèdent pas au rapport complet. Les événements majeurs, visites et indisponibilités sont partagés par les deux directions. Les PDF sont conservés dans le stockage privé déjà monté sur `/private-media` et ne sont jamais servis par WhiteNoise. Les noms facultatifs des visiteurs et les versions générées ne font l’objet d’aucune purge automatique tant que la durée institutionnelle de conservation n’a pas été confirmée.

Une tâche est retenue si son affectation a commencé au plus tard à la fin de la période et n’a pas été clôturée avant son début. Le classement de l’utilisateur détermine son agenda; une personne encore non classée apparaît dans les deux agendas avec un avertissement, sauf exclusion explicite par `include_in_direction_agendas`. Le DG est ainsi exclu des deux agendas. Le taux d’un agent est la moyenne de ses tâches retenues à la fin de la période et les services sans activité ne sont pas ajoutés au PDF. Chaque période et chaque direction possèdent une numérotation de versions indépendante. L’organigramme d’août 2026 qui fixe l’ordre des services se trouve dans [`docs/organogram.org`](docs/organogram.org).

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

Le serveur Vite transmet `/api/` à Django sur `127.0.0.1:8000`. Pour travailler sur l'interface avec les scénarios fictifs sans démarrer Django :

```bash
cd frontend
VITE_USE_MOCKS=true npm run dev
```

Ce parcours avec les mocks est le moyen le plus rapide de travailler sur React. Il ne nécessite aucun conteneur. Ouvrir impérativement `http://127.0.0.1:5173/app/` : la racine `http://127.0.0.1:5173/` ne contient pas l'application. Si Vite était déjà lancé, l'arrêter puis le redémarrer avec la variable `VITE_USE_MOCKS=true`.

Sous PowerShell, la commande équivalente est :

```powershell
cd frontend
$env:VITE_USE_MOCKS = "true"
npm run dev
```

Il permet de modifier les composants et scénarios de `frontend/src/mocks/`, mais ne valide ni les permissions réelles, ni les migrations, ni le backend.

Pour tester React contre le vrai backend, lancer la stack Docker sur le port attendu par le proxy Vite dans un premier terminal :

```bash
CSRS_PORT=8000 docker compose -p csrs -f compose.yml up -d --build
```

Sous PowerShell :

```powershell
$env:CSRS_PORT = "8000"
docker compose -p csrs -f compose.yml up -d --build
```

Lancer ensuite Vite sans mocks dans un second terminal :

```bash
cd frontend
npm run dev
```

Ouvrir `http://127.0.0.1:5173/app/`. Si aucune session n'existe, Vite transmet la redirection `/connexion/` à Django puis ramène le navigateur dans React après authentification. Les routes `/api`, `/connexion`, `/deconnexion`, `/admin` et `/static` restent ainsi sur la même origine visible par le navigateur. Utiliser le même nom d'hôte pendant toute la session : soit `127.0.0.1`, soit `localhost`, sans les mélanger.

Django peut aussi être lancé nativement, notamment pour déboguer le code Python :

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

### Windows avec PowerShell

Docker Desktop doit être démarré avec le moteur WSL 2. Depuis un clone neuf, PowerShell dispose des mêmes opérations que les scripts Bash :

```powershell
.\scripts\bootstrap_env.ps1
docker compose -p csrs -f compose.yml up -d --build
.\scripts\seed_pilot.ps1

cd frontend
npm ci
Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue
npm run dev
```

Le bootstrap PowerShell crée un `.env` local avec des secrets aléatoires, le port Django `8000`, HTTP sans redirection TLS et les origines `8000` et `5173` requises par Django et Vite. Il ne remplace jamais un `.env` existant. Ouvrir directement `http://localhost:5173/app/`; la connexion Django est affichée sur la même origine grâce au proxy Vite, puis renvoie vers React.

Après une modification de `vite.config.ts`, arrêter et relancer `npm run dev`. Si un `.env` a été créé avant l'ajout du script PowerShell, vérifier que `DJANGO_CSRF_TRUSTED_ORIGINS` contient aussi `http://localhost:5173` et `http://127.0.0.1:5173`.

`seed_pilot.ps1` demande les deux mots de passe sans les afficher, exécute la simulation puis le chargement réel et retire les variables de mot de passe de la session. `-DryRunOnly` limite l'exécution à la simulation. Si l'exécution des scripts locaux est bloquée, autoriser les scripts signés ou locaux pour le compte courant :

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Dans un terminal WSL, utiliser directement les scripts `.sh` et les commandes Linux. Il ne faut pas exécuter simultanément les bootstraps Bash et PowerShell : ils ciblent le même fichier `.env` et refusent tous deux de l'écraser.

Le contrat OpenAPI et les types TypeScript sont reproductibles :

```bash
pyenv activate csrs
python manage.py spectacular --file frontend/openapi.yml --validate
cd frontend
npm run types:generate
```

La référence complète des endpoints, des corps JSON, des erreurs, des sessions et du mécanisme CSRF se trouve dans [docs/api.md](docs/api.md).

La compilation Docker est multi-étape : Node produit les fichiers React, puis WhiteNoise les sert avec les autres fichiers statiques. Aucun changement Nginx n'est nécessaire pour `/app/`.

## Conteneurs et déploiement

Sous Linux ou WSL :

```bash
./scripts/bootstrap_env.sh
./scripts/deploy_preprod.sh
./scripts/backup_db.sh
```

Sous Windows PowerShell :

```powershell
.\scripts\bootstrap_env.ps1
.\scripts\deploy_preprod.ps1
.\scripts\backup_db.ps1
```

Les variantes PowerShell utilisent `docker compose` v2. Le script PowerShell de déploiement sert aux stacks Docker exécutées depuis Windows.

Le chargeur de population fictive exige temporairement deux variables distinctes, `CSRS_DEMO_PASSWORD` et `CSRS_ADMIN_PASSWORD`. Il accepte `--dry-run`, `--replace-legacy` et `--reset-password`. Ces variables ne doivent rester ni dans `.env` ni dans les conteneurs après le chargement.

`./scripts/seed_pilot.sh` demande les deux mots de passe sans les afficher, exécute d'abord une simulation annulée puis le chargement réel. L'option `--dry-run-only` limite le script à la simulation. Ce script complet sert à créer ou remplacer la population initiale; il ne doit pas être utilisé pour une simple actualisation périodique.

Sous PowerShell, les commandes équivalentes sont `.\scripts\seed_pilot.ps1` et `.\scripts\seed_pilot.ps1 -DryRunOnly`.

### Remettre les comptes d'un déploiement à l'état canonique

La cible canonique comprend les 40 alias de [`docs/organogram.org`](docs/organogram.org), le compte technique `dev` et le compte fonctionnel `secretariat_dg`. Le mode de nettoyage supprime tous les autres utilisateurs et l'ensemble des tâches, processus, agendas, visites, indisponibilités et délégations qui les référencent. Il reconstruit ensuite les scénarios pilotes et réinitialise les mots de passe des 42 comptes.

Depuis le checkout de chaque hôte Linux ou WSL :

```bash
./scripts/seed_pilot.sh --clean-accounts --dry-run-only
./scripts/seed_pilot.sh --clean-accounts
```

Sous PowerShell :

```powershell
.\scripts\seed_pilot.ps1 -CleanAccounts -DryRunOnly
.\scripts\seed_pilot.ps1 -CleanAccounts
```

La seconde commande rejoue la simulation, exige une sauvegarde vérifiée par le script de backup, puis demande de saisir exactement `SUPPRIMER` avant la transaction destructive. Le projet Docker Compose est lu dans le `.env` propre à l'hôte. Pour un appel direct exceptionnel, la commande Django réelle exige conjointement `--prune-noncanonical-users` et `--confirm-prune`; il ne faut pas contourner le script sur un déploiement contenant des données à sauvegarder.

### Actualiser les scénarios pilotes existants

Sur une base où les comptes pilotes existent déjà, `--refresh-scenarios-only` recale les données fictives sur les douze dernières semaines sans créer de compte ni modifier de mot de passe. La commande reconstruit les historiques, observations et caches des 73 affectations `PIL-*`, puis remet les 42 propositions pilotes dans leurs états de référence. Elle exige les 15 acteurs des scénarios, mais pas les variables de mot de passe.

Depuis le checkout de déploiement, avec un compte autorisé à utiliser Docker, sauvegarder la base puis exécuter d'abord la simulation transactionnelle :

```bash
./scripts/backup_db.sh

project="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env | tail -n 1)"
docker compose -p "$project" -f compose.yml exec -T web \
  python manage.py seed_pilot_users --refresh-scenarios-only --dry-run

docker compose -p "$project" -f compose.yml exec -T web \
  python manage.py seed_pilot_users --refresh-scenarios-only
```


Par défaut, l'application écoute sur `127.0.0.1:18005`. Les modèles de vhost se trouvent dans `deploy/nginx/`. Les sauvegardes validées par `pg_restore --list` sont conservées localement pendant 14 jours dans un dossier ignoré par Git. Aucun secret ni donnée personnelle réelle ne doit être ajouté au dépôt ou aux données de démonstration.
