import { Link, useSearchParams } from "../../lib/router";
import type { Period } from "../../lib/api/types";
import styles from "./tasks.module.css";

export function PeriodNavigation({
  period,
  preserveParams = [],
}: {
  period: Period;
  preserveParams?: string[];
}) {
  const [search, setSearch] = useSearchParams();

  function preserve(query: string) {
    const next = new URLSearchParams(query);
    for (const key of preserveParams) {
      const values = search.getAll(key);
      next.delete(key);
      for (const value of values) next.append(key, value);
    }
    return next;
  }

  function switchMode(kind: "week" | "month") {
    const next = preserve("");
    next.set(
      kind === "month" ? "month" : "week",
      kind === "month" ? period.start.slice(0, 7) : period.start,
    );
    setSearch(next);
  }
  return (
    <>
      <div className={styles.periodModes} aria-label="Type de période">
        <button
          type="button"
          className={period.kind === "week" ? styles.selected : ""}
          onClick={() => switchMode("week")}
        >
          Semaine
        </button>
        <button
          type="button"
          className={period.kind === "month" ? styles.selected : ""}
          onClick={() => switchMode("month")}
        >
          Mois
        </button>
      </div>
      <nav className={styles.period} aria-label="Changer de période">
        <Link
          to={`?${preserve(period.previous_query)}`}
          aria-label="Période précédente"
        >
          ← <span>Précédente</span>
        </Link>
        <strong>{period.label}</strong>
        <Link
          to={`?${preserve(period.next_query)}`}
          aria-label="Période suivante"
        >
          <span>Suivante</span> →
        </Link>
      </nav>
    </>
  );
}
