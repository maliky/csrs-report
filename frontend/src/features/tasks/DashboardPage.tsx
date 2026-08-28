import { FileText } from "lucide-react";
import { useLocation } from "../../lib/router";
import { useState } from "react";
import type { Dashboard } from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import {
  ButtonLink,
  EmptyState,
  ErrorState,
  Skeleton,
} from "../../components/ui";
import { PeriodNavigation } from "./PeriodNavigation";
import { TaskCard } from "./TaskCard";
import styles from "./tasks.module.css";

export function DashboardPage() {
  const location = useLocation();
  const [showArchived, setShowArchived] = useState(false);
  const { data, error, loading, reload } = useApi<Dashboard>(
    `/api/v1/dashboard/${location.search}`,
  );
  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Tableau de bord personnel</p>
          <h1>Mes tâches</h1>
          <p>
            Une vue claire des engagements, de leur progression réelle et de la
            charge restante.
          </p>
        </div>
        <div className="cluster">
          <ButtonLink to="/propositions/nouvelle" variant="secondary">
            Proposer une tâche
          </ButtonLink>
          <ButtonLink to="/profil">
            <FileText size={18} aria-hidden="true" /> Modifier mon cahier des
            charges
          </ButtonLink>
        </div>
      </header>
      {loading && (
        <div className="grid" aria-label="Chargement des tâches">
          <Skeleton />
          <Skeleton />
          <Skeleton />
        </div>
      )}
      {error && <ErrorState error={error} retry={reload} />}
      {data && (
        <>
          <PeriodNavigation period={data.period} />
          {data.tasks.some((task) =>
            ["completed", "closed_early"].includes(task.status),
          ) && (
            <label className={styles.finishedFilter}>
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(event) => setShowArchived(event.target.checked)}
              />
              Afficher les tâches terminées
            </label>
          )}
          {data.tasks.some(
            (task) =>
              showArchived ||
              !["completed", "closed_early"].includes(task.status),
          ) ? (
            <div className="grid">
              {data.tasks
                .filter(
                  (task) =>
                    showArchived ||
                    !["completed", "closed_early"].includes(task.status),
                )
                .map((task) => (
                  <TaskCard key={task.id} task={task} />
                ))}
            </div>
          ) : (
            <EmptyState
              title="Aucune tâche en cours sur cette période"
              action={
                <ButtonLink to="/propositions/nouvelle">
                  Proposer une tâche
                </ButtonLink>
              }
            >
              Vous pouvez changer de période ou proposer un nouvel engagement.
            </EmptyState>
          )}
        </>
      )}
    </>
  );
}
