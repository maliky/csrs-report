import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "../../lib/router";
import type { Team, TeamNode } from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import { Button, EmptyState, ErrorState, Skeleton } from "../../components/ui";
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

function UserAvatar({
  avatar,
  name,
  className,
}: {
  avatar: string | null;
  name: string;
  className: string;
}) {
  const [imageError, setImageError] = useState(false);
  const initial = name.trim().slice(0, 1).toUpperCase() || "?";

  if (!avatar || imageError) {
    return <span className={className}>{initial}</span>;
  }

  return (
    <span className={className} aria-hidden="true">
      <img
        src={avatar}
        className={styles.avatarImage}
        alt=""
        onError={() => setImageError(true)}
      />
    </span>
  );
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
  depth,
}: {
  node: FilteredTeamNode;
  teamQuery: string;
  depth: number;
}) {
  const initiallyOpen = depth === 0;
  const [isOpen, setIsOpen] = useState(initiallyOpen);
  const employeePath = teamQuery
    ? `/equipe/${node.employee.id}/?${teamQuery}`
    : `/equipe/${node.employee.id}/`;

  return (
    <details
      className={`${styles.node} ${!node.matchesFilter ? styles.contextNode : ""}`}
      data-team-employee-id={node.employee.id}
      open={isOpen}
      onToggle={(event) => {
        setIsOpen(event.currentTarget.open);
      }}
    >
      <summary className={styles.summary}>
        <span className={styles.person}>
          <Link
            to={employeePath}
            className={styles.employeeLink}
            onClick={(event) => event.stopPropagation()}
          >
            <span className={styles._person}>
              <UserAvatar
                avatar={node.employee.avatar ?? null}
                name={node.employee.name}
                className={styles.avatar}
              />
              <span className={styles.identity}>
                <strong>{node.employee.name}</strong>
                <span>{node.employee.position || "Collaborateur"}</span>
              </span>
            </span>
          </Link>
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
