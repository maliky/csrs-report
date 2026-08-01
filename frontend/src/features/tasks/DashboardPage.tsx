import { useLocation } from "../../lib/router";
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

export function DashboardPage() {
  const location = useLocation();
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
        <ButtonLink to="/propositions/nouvelle" variant="secondary">
          Proposer une tâche
        </ButtonLink>
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
          {data.tasks.length ? (
            <div className="grid">
              {data.tasks.map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="Aucune tâche sur cette période"
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
