import { AlertTriangle, ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "../../lib/router";
import type {
  TaskSummary,
  Team,
  TeamEmployee,
  TeamNode,
} from "../../lib/api/types";
import { dayCount, formatDate } from "../../lib/format";
import { useApi } from "../../lib/useApi";
import {
  AlertBadge,
  Button,
  EmptyState,
  ErrorState,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import { PeriodNavigation } from "../tasks/PeriodNavigation";
import styles from "./team.module.css";

type TaskFilter = "all" | "with" | "without";
type FilteredTeamNode = Omit<TeamNode, "children"> & {
  children: FilteredTeamNode[];
  matchesFilter: boolean;
};

const TASK_FILTERS: { value: TaskFilter; label: string }[] = [
  { value: "all", label: "Tous" },
  { value: "with", label: "Avec tâches" },
  { value: "without", label: "Sans tâche" },
];

function selectedTaskFilter(params: URLSearchParams): TaskFilter {
  const value = params.get("tasks");
  return value === "with" || value === "without" ? value : "all";
}

function filterTeamNodes(
  nodes: TeamNode[],
  filter: TaskFilter,
): FilteredTeamNode[] {
  return nodes.flatMap((node) => {
    const children = filterTeamNodes(node.children, filter);
    const matchesFilter =
      filter === "all" ||
      (filter === "with" ? node.task_count > 0 : node.task_count === 0);
    return matchesFilter || children.length
      ? [{ ...node, children, matchesFilter }]
      : [];
  });
}

export function TeamPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const taskFilter = selectedTaskFilter(searchParams);
  const apiParams = new URLSearchParams(searchParams);
  apiParams.delete("tasks");
  const apiQuery = apiParams.toString();
  const { data, error, loading, reload } = useApi<Team>(
    `/api/v1/team/${apiQuery ? `?${apiQuery}` : ""}`,
  );
  const filteredNodes = useMemo(
    () => filterTeamNodes(data?.nodes ?? [], taskFilter),
    [data, taskFilter],
  );

  function setTaskFilter(filter: TaskFilter) {
    const next = new URLSearchParams(searchParams);
    if (filter === "all") next.delete("tasks");
    else next.set("tasks", filter);
    setSearchParams(next);
  }

  if (loading) return <Skeleton label="Chargement de l'équipe" />;
  if (error || !data)
    return (
      <ErrorState
        error={error ?? new Error("Équipe indisponible")}
        retry={reload}
      />
    );
  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Vue managériale</p>
          <h1>Synthèse de l'équipe</h1>
          <p>Engagements des collaborateurs sur la période sélectionnée.</p>
        </div>
      </header>
      <PeriodNavigation period={data.period} preserveParams={["tasks"]} />
      {data.nodes.length > 0 && (
        <div
          className={styles.filters}
          role="group"
          aria-label="Filtrer les collaborateurs"
        >
          {TASK_FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              data-task-filter={option.value}
              aria-pressed={taskFilter === option.value}
              onClick={() => setTaskFilter(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
      {filteredNodes.length > 0 ? (
        <div className={styles.tree} key={taskFilter}>
          {filteredNodes.map((node) => (
            <TeamTreeNode
              key={node.employee.id}
              node={node}
              teamQuery={searchParams.toString()}
              periodQuery={data.period.query}
              depth={0}
            />
          ))}
        </div>
      ) : data.nodes.length > 0 ? (
        <EmptyState
          title="Aucun collaborateur correspondant"
          action={
            <Button variant="quiet" onClick={() => setTaskFilter("all")}>
              Afficher tous les collaborateurs
            </Button>
          }
        >
          Aucun collaborateur ne correspond à ce filtre sur la période.
        </EmptyState>
      ) : (
        <EmptyState title="Aucun collaborateur visible">
          Votre périmètre d'équipe ne contient personne pour cette période.
        </EmptyState>
      )}
    </>
  );
}

function TeamTreeNode({
  node,
  teamQuery,
  periodQuery,
  depth,
}: {
  node: FilteredTeamNode;
  teamQuery: string;
  periodQuery: string;
  depth: number;
}) {
  const initiallyOpen = depth === 0;
  const [isOpen, setIsOpen] = useState(initiallyOpen);
  const [hasOpened, setHasOpened] = useState(initiallyOpen);
  const employeePath = teamQuery
    ? `/equipe/${node.employee.id}/?${teamQuery}`
    : `/equipe/${node.employee.id}/`;
  const profile = useApi<TeamEmployee>(
    `/api/v1/team/${node.employee.id}/?${periodQuery}`,
    hasOpened && node.task_count > 0,
  );

  return (
    <details
      className={`${styles.node} ${!node.matchesFilter ? styles.contextNode : ""}`}
      data-team-employee-id={node.employee.id}
      open={isOpen}
      onToggle={(event) => {
        setIsOpen(event.currentTarget.open);
        if (event.currentTarget.open) setHasOpened(true);
      }}
    >
      <summary className={styles.summary}>
        <span className={styles.person}>
          <span className={styles.avatar} aria-hidden="true">
            {node.employee.name.slice(0, 1).toUpperCase()}
          </span>
          <span className={styles.identity}>
            <Link
              to={employeePath}
              className={styles.employeeLink}
              onClick={(event) => event.stopPropagation()}
            >
              <strong>{node.employee.name}</strong>
            </Link>
            <span>{node.employee.position || "Collaborateur"}</span>
          </span>
        </span>
        <span className={styles.summaryMeta}>
          <span className={styles.taskCount}>
            {node.task_count} tâche{node.task_count > 1 ? "s" : ""}
          </span>
          <ChevronDown
            className={styles.chevron}
            size={20}
            aria-hidden="true"
          />
        </span>
      </summary>
      <div className={styles.content}>
        {hasOpened && (
          <TeamProfile
            employeeName={node.employee.name}
            expectedTaskCount={node.task_count}
            data={profile.data}
            error={profile.error}
            loading={profile.loading}
            retry={profile.reload}
          />
        )}
        {node.children.length > 0 && (
          <section className={styles.subteam}>
            <h2>
              Sous-équipe · {node.children.length} collaborateur
              {node.children.length > 1 ? "s" : ""}
            </h2>
            <div className={styles.children}>
              {node.children.map((child) => (
                <TeamTreeNode
                  key={child.employee.id}
                  node={child}
                  teamQuery={teamQuery}
                  periodQuery={periodQuery}
                  depth={depth + 1}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </details>
  );
}

function TeamProfile({
  employeeName,
  expectedTaskCount,
  data,
  error,
  loading,
  retry,
}: {
  employeeName: string;
  expectedTaskCount: number;
  data: TeamEmployee | null;
  error: Error | null;
  loading: boolean;
  retry: () => Promise<void>;
}) {
  const employee = data?.employee;
  if (expectedTaskCount === 0)
    return (
      <p className={styles.profileStatus}>Aucune tâche sur cette période.</p>
    );
  if (loading || (!data && !error))
    return <Skeleton label={`Chargement des tâches de ${employeeName}`} />;
  if (error || !data)
    return (
      <div className={styles.profileError} role="alert">
        <AlertTriangle size={20} aria-hidden="true" />
        <span>{error?.message ?? "Profil indisponible"}</span>
        <Button variant="quiet" onClick={() => void retry()}>
          Réessayer
        </Button>
      </div>
    );
  if (!data.tasks.length)
    return (
      <p className={styles.profileStatus}>Aucune tâche sur cette période.</p>
    );
  return (
    <section
      className={styles.profile}
      aria-label={`Tâches de ${employeeName}`}
    >
      <h2>Profil collaborateur</h2>
      <div className={styles.profileDetails}>
        <dl className="details-grid">
          <div className="detail">
            <dt>Prénom</dt>
            <dd>{employee?.first_name || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Nom</dt>
            <dd>{employee?.last_name || "—"}</dd>
          </div>
          <div className="detail">
            <dt>E-mail</dt>
            <dd>{employee?.email || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Téléphone</dt>
            <dd>{employee?.phone || "—"}</dd>
          </div>
        </dl>
      </div>
      <h3>Cahier des charges</h3>
      <p className={styles.profileTor}>
        {employee?.terms_of_reference || "Aucun cahier des charges saisi."}
      </p>
      <h2>Profil des tâches</h2>
      <div className={styles.tasks}>
        {data.tasks.map((task) => (
          <TeamTaskProfile key={task.id} task={task} />
        ))}
      </div>
    </section>
  );
}

function TeamTaskProfile({ task }: { task: TaskSummary }) {
  return (
    <article className={styles.taskProfile} data-team-task-id={task.id}>
      <header className={styles.taskHeader}>
        <div>
          <span className={styles.taskCode}>{task.code}</span>
          <h3>
            <Link to={`/taches/${task.id}`}>{task.title}</Link>
          </h3>
        </div>
        <div className={styles.badges}>
          {task.blocked && <AlertBadge>Point d'attention</AlertBadge>}
          <StatusBadge status={task.status}>{task.status_label}</StatusBadge>
        </div>
      </header>
      <div className={styles.progressMeta}>
        <strong>{task.percentage} % réalisé</strong>
        <span>{dayCount(task.workload.remaining)} restants</span>
      </div>
      <div
        className={styles.meter}
        role="progressbar"
        aria-label={`Progression de ${task.title}`}
        aria-valuenow={task.percentage}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span style={{ width: `${task.percentage}%` }} />
      </div>
      <div className={styles.taskDates}>
        <span>Début {formatDate(task.start_date)}</span>
        <span>Fin prévue {formatDate(task.due_date)}</span>
      </div>
    </article>
  );
}
