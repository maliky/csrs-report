# API CSRS Report

Référence de l'API utilisée par l'interface React de CSRS Report.

- Version : `v1`
- Préfixe : `/api/v1/`
- Format : JSON
- Authentification : session Django
- Protection des écritures : jeton CSRF
- Schéma OpenAPI : `/api/v1/openapi/`
- Interface Swagger : `/api/v1/documentation/`

Le code Django et le schéma OpenAPI restent les sources de vérité. Cette référence décrit le comportement vérifié le 15 août 2026.

## Authentification et CSRF

L'utilisateur se connecte par la page Django `/connexion/`. L'API n'accepte pas de mot de passe ou de jeton JWT : le navigateur transmet le cookie de session avec chaque requête.

Après la connexion, appeler :

```http
GET /api/v1/session/
```

Cette requête vérifie la session existante, renvoie l'utilisateur et initialise le cookie `csrftoken`. Elle ne connecte pas un utilisateur anonyme.

Pour chaque `POST` ou `PATCH`, envoyer le jeton du cookie dans l'en-tête :

```http
X-CSRFToken: <valeur du cookie csrftoken>
Content-Type: application/json
```

Avec `fetch`, conserver la session de même origine :

```ts
await fetch("/api/v1/tasks/42/progress/", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRFToken": csrfToken,
  },
  body: JSON.stringify({
    revision: 3,
    entry_date: "2026-07-24",
    percentage: 75,
    note: "Livrable transmis.",
    blocked: false,
  }),
});
```

Le frontend du projet fournit déjà ce comportement dans `frontend/src/lib/api/client.ts`.

## Conventions

- Les dates utilisent `YYYY-MM-DD`.
- Les horodatages utilisent ISO 8601.
- Les charges en jours sont renvoyées sous forme de chaînes décimales, par exemple `"5"` ou `"2.5"`.
- Les identifiants sont des entiers.
- Une ressource non visible par l'utilisateur renvoie `404`, afin de ne pas révéler son existence.
- Les écritures sur une tâche ou une proposition utilisent une révision optimiste. Le client doit envoyer la dernière valeur `revision` reçue.
- Une écriture réussie incrémente généralement `revision`.
- Les `PATCH` actuels ne sont pas partiels : les champs métier obligatoires doivent être renvoyés avec leur valeur courante, même si un seul champ change.

### Période

Les endpoints de dashboard et d'équipe acceptent un paramètre facultatif :

| Paramètre | Format | Effet |
|---|---|---|
| `week` | `YYYY-MM-DD` | Semaine du lundi au dimanche contenant cette date |
| `month` | `YYYY-MM` | Mois civil demandé |

Sans paramètre valide, l'API utilise la semaine courante. Si `week` et `month` sont tous deux valides, `month` est prioritaire.

Exemples :

```http
GET /api/v1/dashboard/?week=2026-07-20
GET /api/v1/team/?month=2026-07
```

## Formats de réponse communs

### Person

```json
{
  "id": 8,
  "name": "Aïssata Koné",
  "position": "Directrice générale",
  "login_alias": "dg"
}
```

### Period

```json
{
  "kind": "week",
  "label": "semaine du 20/07/2026",
  "start": "2026-07-20",
  "end": "2026-07-26",
  "query": "week=2026-07-20",
  "previous_query": "week=2026-07-13",
  "next_query": "week=2026-07-27"
}
```

### TaskSummary

```json
{
  "id": 42,
  "revision": 3,
  "code": "TSK-0042",
  "title": "Préparer le rapport",
  "status": "active",
  "status_label": "En cours",
  "percentage": 50,
  "progress_delta": 10,
  "start_date": "2026-07-20",
  "today": "2026-07-24",
  "due_date": "2026-07-27",
  "workload": {
    "total": "5",
    "completed": "2.5",
    "remaining": "2.5"
  },
  "deadline_level": "normal",
  "blocked": false,
  "latest_note": "",
  "employee": {},
  "manager": {},
  "action": {
    "id": 12,
    "label": "ACT-12 — Rapport périodique"
  }
}
```

`employee` et `manager` suivent le format `Person`. `action` peut être `null`.

Valeurs possibles de `status` :

- `planned`
- `active`
- `awaiting_validation`
- `completed`
- `closed_early`

### TaskDetail

Le détail reprend les champs utiles de `TaskSummary` et ajoute :

```json
{
  "description": "Description complète.",
  "estimated_work_days": "5",
  "calendar": {
    "id": 1,
    "label": "Calendrier standard"
  },
  "chart": [],
  "activities": [],
  "capabilities": {
    "manage": true,
    "comment": true,
    "update_progress": true,
    "self_managed": false
  }
}
```

`chart` contient les points journaliers du graphique de progression. `activities` contient le journal visible des progressions, commentaires, changements de planification et transitions.

### Proposal

```json
{
  "id": 17,
  "revision": 1,
  "title": "Formaliser le tableau de priorités",
  "description": "Préparer une version arbitrée.",
  "status": "submitted",
  "status_label": "Soumise",
  "start_date": "2026-07-20",
  "due_date": "2026-07-27",
  "estimated_work_days": "5",
  "action": null,
  "calendar": {
    "id": 1,
    "label": "Calendrier standard"
  },
  "employee": {},
  "accepted_assignment_id": null,
  "decision_note": "",
  "created_at": "2026-07-24T09:00:00+00:00",
  "can_review": false,
  "capabilities": {
    "edit": true,
    "resubmit": false,
    "review": false
  }
}
```

Valeurs possibles de `status` : `submitted`, `accepted`, `rejected`.

## Liste des endpoints

| Méthode | URL | Fonction |
|---|---|---|
| `GET` | `/api/v1/session/` | Session, utilisateur, CSRF et capacités |
| `POST` | `/api/v1/session/logout/` | Déconnexion |
| `GET` | `/api/v1/dashboard/` | Tâches de l'utilisateur pour une période |
| `GET` | `/api/v1/planning/options/` | Employés, actions, calendriers et valeurs par défaut |
| `POST` | `/api/v1/planning/preview/` | Calcul de l'échéance ou de la charge |
| `POST` | `/api/v1/tasks/` | Création et affectation d'une tâche |
| `GET` | `/api/v1/tasks/{id}/` | Détail d'une tâche visible |
| `PATCH` | `/api/v1/tasks/{id}/` | Modification complète des champs éditables |
| `POST` | `/api/v1/tasks/{id}/progress/` | Enregistrement de la progression |
| `POST` | `/api/v1/tasks/{id}/observations/` | Ajout d'une observation |
| `POST` | `/api/v1/tasks/{id}/transition/` | Validation, rejet ou clôture anticipée |
| `GET` | `/api/v1/proposals/` | Propositions regroupées par rôle |
| `POST` | `/api/v1/proposals/` | Création d'une proposition |
| `GET` | `/api/v1/proposals/{id}/` | Détail d'une proposition visible |
| `PATCH` | `/api/v1/proposals/{id}/` | Modification complète d'une proposition |
| `POST` | `/api/v1/proposals/{id}/decision/` | Acceptation ou rejet par un responsable |
| `POST` | `/api/v1/proposals/{id}/resubmit/` | Resoumission par l'auteur |
| `GET` | `/api/v1/team/` | Arbre d'équipe et nombre de tâches sur la période |
| `GET` | `/api/v1/team/{id}/` | Tâches visibles d'un collaborateur |
| `GET`, `POST` | `/api/v1/visits/` | Visites de la période demandée et notification d'une arrivée |
| `POST` | `/api/v1/visits/{id}/departure/` | Notification du départ d'un groupe de visiteurs |
| `GET`, `POST` | `/api/v1/availability/` | Indisponibilités de la semaine et nouvelle déclaration RH |
| `PATCH` | `/api/v1/availability/{id}/` | Correction d'une indisponibilité avec contrôle de révision |
| `POST` | `/api/v1/availability/{id}/cancel/` | Annulation motivée d'une indisponibilité |
| `GET` | `/api/v1/agenda/preview/` | Brouillon et synthèse non figée d'une période et d'une direction |
| `PUT` | `/api/v1/agenda/draft/` | Enregistrement des événements majeurs du brouillon |
| `GET`, `POST` | `/api/v1/agenda/versions/` | Archives visibles ou génération d'une version PDF figée |
| `GET` | `/api/v1/agenda/versions/{id}/pdf/` | Téléchargement privé d'une version PDF |

## Session

### `GET /api/v1/session/`

Réponse `200` :

```json
{
  "user": {},
  "csrf_token": "<token>",
  "capabilities": {
    "create_task": true,
    "create_proposal": true,
    "view_team": true,
    "self_assign": false,
    "admin": false
  }
}
```

Réponse `401` si aucune session authentifiée n'existe.

### `POST /api/v1/session/logout/`

Aucun corps. Réponse `204` sans contenu. La session courante est supprimée.

## Dashboard et équipe

### `GET /api/v1/dashboard/`

Accepte `week` ou `month`.

Réponse `200` :

```json
{
  "period": {},
  "today": "2026-07-24",
  "tasks": []
}
```

Les éléments de `tasks` suivent le format `TaskSummary`.

### `GET /api/v1/team/`

Accepte `week` ou `month`. Chaque nœud contient les tâches propres à la personne pour cette période, sans additionner celles des descendants.

```json
{
  "period": {},
  "nodes": [
    {
      "employee": {},
      "task_count": 2,
      "children": []
    }
  ]
}
```

### `GET /api/v1/team/{id}/`

Accepte `week` ou `month`.

```json
{
  "period": {},
  "employee": {},
  "tasks": []
}
```

Un utilisateur sans visibilité sur le collaborateur reçoit `404`.

## Planification

### `GET /api/v1/planning/options/`

Renvoie uniquement les employés affectables par l'utilisateur et les actions et calendriers actifs.

```json
{
  "employees": [],
  "actions": [],
  "calendars": [],
  "defaults": {
    "calendar_id": 1,
    "start_date": "2026-07-24",
    "due_date": "2026-07-30",
    "estimated_work_days": "5"
  }
}
```

### `POST /api/v1/planning/preview/`

Ce calcul ne sauvegarde rien et ne répartit pas la charge entre les membres d'une équipe.

Calculer l'échéance depuis une charge :

```json
{
  "calendar_id": 1,
  "source": "workload",
  "start_date": "2026-07-24",
  "estimated_work_days": "5"
}
```

Calculer la charge depuis une échéance :

```json
{
  "calendar_id": 1,
  "source": "due",
  "start_date": "2026-07-24",
  "due_date": "2026-07-30"
}
```

Réponse `200` :

```json
{
  "start_date": "2026-07-24",
  "due_date": "2026-07-30",
  "estimated_work_days": "5"
}
```

`start_date` doit être un jour ouvré du calendrier sélectionné.

## Tâches

### `POST /api/v1/tasks/`

Crée une tâche et son affectation. L'employé doit faire partie des personnes que l'utilisateur courant peut gérer.

```json
{
  "title": "Préparer le rapport mensuel",
  "description": "Consolider les contributions des services.",
  "employee_id": 8,
  "action_id": 12,
  "calendar_id": 1,
  "start_date": "2026-07-24",
  "due_date": "2026-07-30",
  "estimated_work_days": "5"
}
```

Champs facultatifs :

- `action_id` : entier ou `null`;
- `calendar_id` : le calendrier par défaut est utilisé s'il est absent.

Réponse `201` : `TaskDetail`.

### `GET /api/v1/tasks/{id}/`

Réponse `200` : `TaskDetail`.

Réponse `404` si la tâche n'existe pas ou n'est pas visible.

### `PATCH /api/v1/tasks/{id}/`

Le corps doit contenir tous les champs ci-dessous. Cet endpoint n'accepte pas encore un véritable patch partiel.

```json
{
  "revision": 3,
  "title": "Préparer le rapport trimestriel",
  "description": "Description mise à jour.",
  "action_id": 12,
  "start_date": "2026-07-24",
  "due_date": "2026-07-30",
  "estimated_work_days": "5"
}
```

`action_id` peut être `null`. Son omission supprime également l'action de la tâche. Le calendrier d'une tâche ne peut pas être changé par cet endpoint.

Réponse `200` : `TaskDetail` avec une révision incrémentée.

### `POST /api/v1/tasks/{id}/progress/`

```json
{
  "revision": 3,
  "entry_date": "2026-07-24",
  "percentage": 75,
  "note": "Livrable transmis.",
  "blocked": false
}
```

- `percentage` est compris entre 0 et 100.
- Pour un utilisateur ordinaire, il évolue par pas de 5.
- `note` est facultatif, sauf lors d'une baisse de progression ou si `blocked` vaut `true`.
- Un employé ne peut saisir que la date du jour; un responsable autorisé peut corriger une autre date.
- À `100`, le statut devient `awaiting_validation`.

Réponse `200` : `TaskDetail`.

### `POST /api/v1/tasks/{id}/observations/`

```json
{
  "revision": 4,
  "message": "Le point sera présenté au prochain comité."
}
```

Réponse `200` : `TaskDetail`.

### `POST /api/v1/tasks/{id}/transition/`

Validation d'une tâche terminée à 100 % :

```json
{
  "revision": 5,
  "transition": "validate",
  "reason": ""
}
```

Rejet de la demande de validation :

```json
{
  "revision": 5,
  "transition": "reject",
  "reason": "Le livrable doit être corrigé."
}
```

Clôture anticipée :

```json
{
  "revision": 5,
  "transition": "close_early",
  "reason": "L'activité est annulée."
}
```

`reason` est obligatoire pour `reject` et `close_early`. Ces transitions sont réservées à un responsable autorisé. Réponse `200` : `TaskDetail`.

## Propositions

### `GET /api/v1/proposals/`

```json
{
  "own": [],
  "reviewable": [],
  "read_only": []
}
```

- `own` : propositions de l'utilisateur;
- `reviewable` : propositions sur lesquelles il peut décider;
- `read_only` : propositions visibles sans droit de décision.

Chaque élément suit le format `Proposal`.

### `POST /api/v1/proposals/`

L'auteur doit être rattaché à un service à la date de début.

```json
{
  "title": "Préparer une nouvelle procédure",
  "description": "Formaliser et faire valider la procédure.",
  "action_id": null,
  "calendar_id": 1,
  "start_date": "2026-07-24",
  "due_date": "2026-07-30",
  "estimated_work_days": "5"
}
```

`action_id` et `calendar_id` sont facultatifs. Réponse `201` : `Proposal`.

### `GET /api/v1/proposals/{id}/`

Réponse `200` : `Proposal`.

Réponse `404` si la proposition n'existe pas ou n'est pas visible.

### `PATCH /api/v1/proposals/{id}/`

Seul l'auteur peut modifier une proposition `submitted` ou `rejected`. Le corps complet est obligatoire :

```json
{
  "revision": 2,
  "title": "Préparer la procédure mise à jour",
  "description": "Description corrigée.",
  "action_id": null,
  "calendar_id": 1,
  "start_date": "2026-07-24",
  "due_date": "2026-07-30",
  "estimated_work_days": "5"
}
```

`calendar_id` est facultatif et conserve le calendrier actuel s'il est absent. L'omission de `action_id` supprime l'action. Réponse `200` : `Proposal`.

### `POST /api/v1/proposals/{id}/decision/`

Acceptation :

```json
{
  "revision": 1,
  "decision": "accept",
  "reason": ""
}
```

Rejet :

```json
{
  "revision": 1,
  "decision": "reject",
  "reason": "Préciser le résultat attendu."
}
```

Le motif est obligatoire pour un rejet. L'acceptation crée une affectation et renseigne `accepted_assignment_id`. Réponse `200` : `Proposal`.

### `POST /api/v1/proposals/{id}/resubmit/`

Seul l'auteur peut resoumettre une proposition rejetée.

```json
{
  "revision": 3
}
```

Réponse `200` : `Proposal` avec le statut `submitted`.

## Agendas par période et direction

Les listes de visites et l'agenda utilisent les paramètres facultatifs `period_start=YYYY-MM-DD` et `period_end=YYYY-MM-DD`. Sans ces paramètres, l'API propose le lundi au dimanche de la semaine suivante. La période est inclusive et limitée à 31 jours. L'aperçu utilise aussi `agenda_direction=programs` ou `agenda_direction=administration`, avec `programs` par défaut. La liste RH des indisponibilités conserve son paramètre hebdomadaire `week=YYYY-MM-DD`.

Les routes de visite et de préparation sont réservées au secrétariat DG, les indisponibilités aux RH, et les archives au secrétariat DG et au DG. Une ressource hors autorisation répond `404` afin de ne pas révéler son existence.

### Visiteurs

`POST /api/v1/visits/` exige `party_size` et accepte `visitor_names`, une liste facultative dont la taille ne peut pas dépasser le nombre déclaré. `POST /api/v1/visits/{id}/departure/` exige la `revision` courante.

### Congés, absences et missions

`POST /api/v1/availability/` reçoit `employee_id`, `kind` (`leave`, `absence` ou `mission`), `start_date`, `end_date` et une `note` facultative. La correction ajoute `revision`; l'annulation ajoute `revision` et `reason`. Deux indisponibilités actives ne peuvent pas se chevaucher pour un agent.

### Aperçu, génération et archives

`GET /api/v1/agenda/preview/?period_start=2026-08-17&period_end=2026-08-23&agenda_direction=programs` agrège les événements majeurs, les arrivées et départs, les indisponibilités et les tâches retenues pour la période. Une affectation est retenue si elle a commencé au plus tard à la fin de la période et n'a pas été clôturée avant son début. Les utilisateurs de la direction choisie et les utilisateurs non classés sont inclus, à moins que leur champ `include_in_direction_agendas` soit désactivé. Les tâches sont regroupées par service puis par agent avec progression, variation et dernière observation de la période.

`PUT /api/v1/agenda/draft/` enregistre `period_start`, `period_end`, `major_events` et la `revision` attendue. Le brouillon est partagé par les deux directions pour une même période.

`POST /api/v1/agenda/versions/` reçoit `period_start`, `period_end` et `agenda_direction`. Il crée une version immuable contenant un instantané JSON, des empreintes SHA-256 et un PDF A4 dans le stockage privé. La numérotation est indépendante pour chaque combinaison période et direction; une génération ultérieure ne modifie jamais les versions précédentes. `GET /api/v1/agenda/versions/` accepte les mêmes filtres de période et un filtre facultatif de direction; sans filtre de période, il renvoie les archives visibles.

## Erreurs

Toutes les erreurs API utilisent la même enveloppe :

```json
{
  "error": {
    "code": "validation_error",
    "message": "Ce champ est obligatoire.",
    "fields": {
      "due_date": [
        "Ce champ est obligatoire."
      ]
    }
  }
}
```

| HTTP | `error.code` | Signification |
|---|---|---|
| `400` | `validation_error` | Corps ou règle métier invalide |
| `401` | `not_authenticated` | Session absente ou expirée |
| `403` | `forbidden` | Action interdite |
| `404` | `not_found` | Ressource absente ou non visible |
| `409` | `stale_revision` | La ressource a changé depuis sa lecture |
| `500` | `server_error` | Erreur serveur inattendue |

En cas de conflit de révision :

```json
{
  "error": {
    "code": "stale_revision",
    "message": "Cette ressource a été modifiée depuis son chargement.",
    "fields": {
      "revision": [
        "4"
      ]
    }
  }
}
```

Le client doit recharger la ressource, présenter les nouvelles données puis laisser l'utilisateur recommencer sa modification.

## Vérification et génération du contrat

Depuis `csrs_report` :

```bash
pyenv activate csrs
pytest -q tests/test_api.py
python manage.py spectacular \
  --file frontend/openapi.yml \
  --validate \
  --fail-on-warn

cd frontend
npm run types:generate
```

Fichiers liés :

- `api/urls.py` : routes;
- `api/serializers.py` : corps des requêtes;
- `api/views.py` : permissions et orchestration;
- `api/presenters.py` : réponses JSON;
- `api/exceptions.py` : format des erreurs;
- `frontend/src/lib/api/types.ts` : types utilisés par React;
- `frontend/src/lib/api/client.ts` : session, CSRF et traitement des erreurs.
