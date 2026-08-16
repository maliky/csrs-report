import { useLocation, useParams } from "../../lib/router";
import type { TeamEmployee } from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import {
  ButtonLink,
  EmptyState,
  ErrorState,
  Card,
  Skeleton,
} from "../../components/ui";
import { PeriodNavigation } from "../tasks/PeriodNavigation";
import { TaskCard } from "../tasks/TaskCard";

export function EmployeePage() {
  const { employeeId } = useParams();
  const location = useLocation();
  const { data, error, loading, reload } = useApi<TeamEmployee>(
    `/api/v1/team/${employeeId}/${location.search}`,
  );
  if (loading) return <Skeleton label="Chargement du collaborateur" />;
  if (error || !data)
    return (
      <ErrorState
        error={error ?? new Error("Collaborateur indisponible")}
        retry={reload}
      />
    );
  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Progression et charge</p>
          <h1>{data.employee.name}</h1>
          <p>{data.employee.position || "Collaborateur"}</p>
        </div>
        <ButtonLink to={`/equipe${location.search}`} variant="quiet">
          Retour à l'équipe
        </ButtonLink>
      </header>
      <Card>
        <h2>Informations collaborateur</h2>
        <dl className="details-grid">
          <div className="detail">
            <dt>Prénom</dt>
            <dd>{data.employee.first_name || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Nom</dt>
            <dd>{data.employee.last_name || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Identifiant</dt>
            <dd>{data.employee.login_alias || "—"}</dd>
          </div>
          <div className="detail">
            <dt>E-mail</dt>
            <dd>{data.employee.email || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Téléphone</dt>
            <dd>{data.employee.phone || "—"}</dd>
          </div>
        </dl>
      </Card>
      <Card>
        <h2>Cahier des charges</h2>
        <p style={{ whiteSpace: "pre-wrap" }}>
          {data.employee.terms_of_reference || "Aucun cahier des charges saisi."}
        </p>
      </Card>
      <PeriodNavigation period={data.period} />
      {data.tasks.length ? (
        <div className="grid">
          {data.tasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
        </div>
      ) : (
        <EmptyState title="Aucune tâche sur cette période">
          Changez de période pour consulter d'autres engagements.
        </EmptyState>
      )}
    </>
  );
}
