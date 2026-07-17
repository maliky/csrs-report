import { Link, useSearchParams } from "react-router-dom";
import type { Period } from "../../lib/api/types";
import styles from "./tasks.module.css";

export function PeriodNavigation({ period }: { period: Period }) {
  const [, setSearch] = useSearchParams();
  function switchMode(kind: "week" | "month") {
    setSearch(
      kind === "month"
        ? { month: period.start.slice(0, 7) }
        : { week: period.start },
    );
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
        <Link to={`?${period.previous_query}`} aria-label="Période précédente">
          ← <span>Précédente</span>
        </Link>
        <strong>{period.label}</strong>
        <Link to={`?${period.next_query}`} aria-label="Période suivante">
          <span>Suivante</span> →
        </Link>
      </nav>
    </>
  );
}
