# Instructions de travail

Ces directives s'appliquent a tout le depot `csrs_report` et restent volontairement independantes du langage ou du framework.

## Source fonctionnelle

- Lire `DEV.org` avant toute modification importante.
- L'application et sa documentation utilisateur sont principalement en francais.
- Distinguer les besoins confirmes, les hypotheses et les questions encore ouvertes.
- Ne pas transformer une hypothese de `DEV.org` en contrainte technique sans decision explicite.

## Methode de developpement

- Commencer par les cas d'usage minimaux, les roles, les regles d'autorisation et les contraintes d'interface.
- Ajouter ou adapter les tests avec chaque comportement fonctionnel.
- Preferer de petits changements verificables a des refontes larges.
- Documenter les decisions d'architecture qui engagent durablement le projet.
- Dans les fichiers `.org` et `.md`, ne pas envelopper manuellement le texte : conserver chaque paragraphe et chaque element de liste sur une seule ligne logique, sans modifier les blocs de code, tableaux, titres ou autres structures.
- Conserver des migrations de base de donnees reproductibles et versionnees.
- Garder le projet executable dans des conteneurs sans rendre le code dependant d'un poste de travail particulier.

## Interface

- Concevoir d'abord une interface web responsive utilisable sur ordinateur et telephone.
- Prioriser une saisie quotidienne courte, des libelles simples, de grands controles tactiles et des retours visuels clairs.
- Ne pas supposer que les utilisateurs maitrisent l'informatique.
- Verifier la navigation au clavier, le contraste, les messages d'erreur et les tailles d'ecran etroites.
- Reporter les fonctions PWA, hors ligne ou natives tant que le MVP responsive n'est pas valide.

## Donnees et securite

- Ne jamais committer de secret, mot de passe, jeton, cle privee ou donnees personnelles reelles.
- Appliquer les autorisations cote serveur; masquer un element dans l'interface ne constitue pas une autorisation.
- Conserver un historique auditable des affectations, validations et changements de progression.
- Eviter les mises a jour silencieuses qui ecrasent les observations d'un autre utilisateur.
- Minimiser les donnees personnelles et documenter leur duree de conservation.
- Toute integration email ou SMS doit avoir des limites, des reprises sur erreur et des journaux qui n'exposent pas les codes de verification.

## Verification et exploitation

- Tester les regles metier et les permissions avant les details visuels.
- Verifier les migrations sur une base vide et sur une base contenant des donnees de test.
- Ne pas modifier Nginx, DNS, Certbot ou le service de production sans demande explicite.
- Pour le futur deploiement, verifier dans l'ordre DNS, service applicatif, port local, vhost Nginx, `nginx -t`, puis certificat TLS.
- Aucun certificat ne doit etre demande avant que `csrs.koba.sarl` resolve vers ce serveur et que le vhost HTTP fonctionne.
- La preproduction etudiante utilise `psiaka.koba.sarl`, le projet Compose `csrs_psiaka` et le port local `18006`. Le compte `psiaka` ne doit pas recevoir l'acces au groupe `docker`; un administrateur execute le deploiement apres revue.
