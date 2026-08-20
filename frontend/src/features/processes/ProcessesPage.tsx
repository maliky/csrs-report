import { Clock3, FileCheck2, Plus } from "lucide-react";
import { Link, useSearchParams } from "../../lib/router";
import {
  ButtonLink,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import { formatDate } from "../../lib/format";
import type { ProcessList } from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import styles from "./processes.module.css";

export function ProcessesPage() {
  const [params, setParams] = useSearchParams();
  const box = params.get("box") === "mine" ? "mine" : "actionable";
  const { data, error, loading, reload } = useApi<ProcessList>(
    `/api/v1/processes/?box=${box}`,
  );

  if (loading) return <Skeleton label="Chargement des processus" />;
  if (error || !data)
    return (
      <ErrorState
        error={error ?? new Error("Processus indisponibles")}
        retry={reload}
      />
    );

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Circuits administratifs</p>
          <h1>Processus</h1>
          <p>
            Traitez les dossiers de votre file de service et suivez vos propres
            demandes.
          </p>
        </div>
        <ButtonLink to="nouveau/ordre-mission">
          <Plus size={18} aria-hidden="true" /> Nouvel ordre de mission
        </ButtonLink>
      </header>
      <div className={styles.counters} aria-label="Indicateurs des processus">
        <Card>
          <Clock3 aria-hidden="true" />
          <strong>{data.counters.pending}</strong>
          <span>Dossiers dans cette boîte</span>
        </Card>
        <Card>
          <FileCheck2 aria-hidden="true" />
          <strong>{data.counters.correction_returns}</strong>
          <span>Retours en correction</span>
        </Card>
      </div>
      <div
        className={styles.tabs}
        role="tablist"
        aria-label="Boîte de processus"
      >
        <button
          type="button"
          role="tab"
          aria-selected={box === "actionable"}
          onClick={() => setParams({ box: "actionable" })}
        >
          À traiter
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={box === "mine"}
          onClick={() => setParams({ box: "mine" })}
        >
          Mes dossiers
        </button>
      </div>
      {data.items.length === 0 ? (
        <EmptyState title="Aucun dossier dans cette boîte">
          {box === "actionable"
            ? "Aucune action ne vous attend actuellement."
            : "Créez un ordre de mission pour commencer."}
        </EmptyState>
      ) : (
        <div className="stack">
          {data.items.map((item) => (
            <Card key={item.id} className={styles.caseCard}>
              <div className={styles.caseHeading}>
                <div>
                  <p className="eyebrow">
                    {item.reference} · {item.mission_type_label}
                  </p>
                  <h2>
                    <Link to={`${item.id}`}>{item.destination}</Link>
                  </h2>
                </div>
                <StatusBadge status={item.status}>
                  {item.status_label}
                </StatusBadge>
              </div>
              <p>{item.purpose}</p>
              <div className={styles.meta}>
                <span>{item.initiator.name}</span>
                <span>{item.origin_unit.short_name}</span>
                <span>
                  {formatDate(item.departure_date)} –{" "}
                  {formatDate(item.return_date)}
                </span>
                {item.due_date && (
                  <span>À traiter avant le {formatDate(item.due_date)}</span>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
