# Calendrier ouvrable versionné

Chaque affectation conserve son `WorkCalendar`. Modifier le calendrier par défaut
ne recalcule donc jamais silencieusement une ancienne tâche. Dès qu'une version est
utilisée, ses jours deviennent en lecture seule; l'administrateur crée une nouvelle
version pour corriger ou compléter l'année.

La version initiale 2026 applique le
[décret ivoirien n° 2011-371](https://www.fonctionpublique.gouv.ci/assets/rubriques/_documentation/D_2011_371_04.11_.11_Jours_Feries_.pdf).
Les dates mobiles déjà annoncées ont été vérifiées sur les publications officielles
du Gouvernement : Aïd el-Fitr le 20 mars 2026 et Tabaski le 27 mai 2026. Le
lendemain de la Nuit du Destin, le 16 mars 2026, est également inclus.

Le lendemain du Maouloud est initialisé au 26 août 2026 selon la date annuelle de
référence. Comme toute fête lunaire future, il doit être comparé à l'annonce
officielle lorsqu'elle paraît; une correction passe par une nouvelle version du
calendrier, pas par la modification d'une version déjà utilisée.

La règle de calcul reste volontairement explicite : la date de début est le point
zéro, puis la charge compte les jours ouvrables qui suivent. Une charge décimale
est arrondie au jour ouvrable supérieur pour déterminer l'échéance; par exemple
`2,5` jours place l'échéance sur le troisième jour ouvrable après le début.
