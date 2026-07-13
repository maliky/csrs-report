# Historique JSON des progressions

La route authentifiée `GET /taches/<id>/progression.json` applique exactement la
même autorisation de lecture que la page de détail. Elle ne contient ni note, ni
auteur, ni autre donnée personnelle.

Chaque ligne correspond à un jour ouvrable. Une saisie réelle porte
`observed: true`; un jour sans saisie reporte la dernière valeur connue avec
`observed: false`. Avant la première saisie, la valeur vaut 0 %. Une tâche ouverte
s'étend jusqu'à la vraie date du jour. Une tâche terminée ou clôturée s'arrête à
`completed_at`.

```json
{
  "task_id": 31,
  "start_date": "2026-05-04",
  "day": "2026-05-05",
  "due_date": "2026-05-20",
  "planned_work_days": 12.0,
  "elapsed_work_days": 1,
  "remaining_schedule_days": 11.0,
  "overdue_days": 0.0,
  "percentage": 15,
  "observed": true
}
```

Dans Observable, après avoir ouvert une session sur le même domaine :

```js
const history = await d3.json("https://csrs.koba.sarl/taches/31/progression.json");

Plot.plot({
  y: {domain: [0, 100], label: "Réalisation (%)"},
  x: {label: "Jours ouvrés écoulés"},
  marks: [
    Plot.lineY(history, {
      x: "elapsed_work_days",
      y: "percentage",
      curve: "monotone-x"
    }),
    Plot.dot(history, {
      x: "elapsed_work_days",
      y: "percentage",
      fill: d => d.observed ? "#006b54" : "white",
      stroke: "#006b54"
    })
  ]
})
```

L'authentification par cookie peut empêcher un notebook Observable public de lire
la route. Pour travailler hors du site, copier manuellement un extrait JSON sans
donnée personnelle plutôt que de rendre la route publique.
