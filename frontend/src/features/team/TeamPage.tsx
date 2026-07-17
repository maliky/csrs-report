import { Link, useLocation } from "react-router-dom";
import type { Team, TeamNode } from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui";
import { PeriodNavigation } from "../tasks/PeriodNavigation";
import styles from "./team.module.css";

export function TeamPage() {
  const location = useLocation();
  const { data, error, loading, reload } = useApi<Team>(
    `/api/v1/team/${location.search}`,
  );
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
          <h1>Mon équipe</h1>
          <p>
            Les sous-équipes restent repliées. Les données détaillées ne sont
            chargées qu'à l'ouverture d'un collaborateur.
          </p>
        </div>
      </header>
      <PeriodNavigation period={data.period} />
      {data.nodes.length ? (
        <div className={styles.tree}>
          {data.nodes.map((node) => (
            <TeamTreeNode
              key={node.employee.id}
              node={node}
              query={location.search}
            />
          ))}
        </div>
      ) : (
        <EmptyState title="Aucun collaborateur visible">
          Votre périmètre d'équipe ne contient personne pour cette période.
        </EmptyState>
      )}
    </>
  );
}

function TeamTreeNode({ node, query }: { node: TeamNode; query: string }) {
  return (
    <details className={styles.node}>
      <summary className={styles.summary}>
        <span className={styles.person}>
          <span className={styles.avatar} aria-hidden="true">
            {node.employee.name.slice(0, 1).toUpperCase()}
          </span>
          <span>
            <strong>{node.employee.name}</strong>
            <br />
            <span className="muted">
              {node.employee.position || "Collaborateur"} · {node.task_count}{" "}
              tâche{node.task_count > 1 ? "s" : ""}
            </span>
          </span>
        </span>
        <Link
          className={styles.link}
          to={`/equipe/${node.employee.id}${query}`}
          onClick={(event) => event.stopPropagation()}
        >
          Voir la progression
        </Link>
      </summary>
      {node.children.length > 0 && (
        <div className={styles.children}>
          {node.children.map((child) => (
            <TeamTreeNode key={child.employee.id} node={child} query={query} />
          ))}
        </div>
      )}
    </details>
  );
}
