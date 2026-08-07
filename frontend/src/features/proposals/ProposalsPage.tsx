import { CircleCheckBig, Filter, RotateCcw, XCircle } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "../../lib/router";
import type { Proposal, ProposalGroups } from "../../lib/api/types";
import { apiFetch } from "../../lib/api/client";
import { useApi } from "../../lib/useApi";
import { dayCount, formatDate } from "../../lib/format";
import {
  Button,
  ButtonLink,
  Card,
  EmptyState,
  ErrorState,
  FrenchDateInput,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import styles from "./proposals.module.css";

const STATUS_OPTIONS = [
  { value: "submitted", label: "Soumises" },
  { value: "accepted", label: "Validées" },
  { value: "rejected", label: "Rejetées" },
] as const;
const ALL_STATUSES = STATUS_OPTIONS.map((option) => option.value);

type Filters = {
  statuses: string[];
  employee: string;
  start: string;
  end: string;
};

function filtersFromParams(params: URLSearchParams): Filters {
  const requested = (params.get("status") ?? "")
    .split(",")
    .filter((status) => ALL_STATUSES.includes(status as never));
  return {
    statuses: requested.length ? requested : [...ALL_STATUSES],
    employee: params.get("employee") ?? "",
    start: params.get("start") ?? "",
    end: params.get("end") ?? "",
  };
}

export function ProposalsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState(() => filtersFromParams(searchParams));
  const [filterError, setFilterError] = useState("");
  const { data, error, loading, reload } =
    useApi<ProposalGroups>("/api/v1/proposals/");

  useEffect(() => {
    setDraft(filtersFromParams(searchParams));
  }, [searchParams]);

  const applied = filtersFromParams(searchParams);
  const collaborators = useMemo(() => {
    if (!data) return [];
    const people = new Map<number, Proposal["employee"]>();
    for (const proposal of [...data.own, ...data.reviewable, ...data.read_only])
      people.set(proposal.employee.id, proposal.employee);
    return [...people.values()].sort((left, right) =>
      left.name.localeCompare(right.name, "fr"),
    );
  }, [data]);

  if (loading) return <Skeleton label="Chargement des propositions" />;
  if (error || !data)
    return (
      <ErrorState
        error={error ?? new Error("Propositions indisponibles")}
        retry={reload}
      />
    );

  function matches(proposal: Proposal) {
    return (
      applied.statuses.includes(proposal.status) &&
      (!applied.employee ||
        proposal.employee.id === Number(applied.employee)) &&
      (!applied.start || proposal.due_date >= applied.start) &&
      (!applied.end || proposal.start_date <= applied.end)
    );
  }

  const groups = {
    reviewable: data.reviewable.filter(matches),
    own: data.own.filter(matches),
    read_only: data.read_only.filter(matches),
  };
  const total =
    data.own.length + data.reviewable.length + data.read_only.length;
  const visibleTotal =
    groups.own.length + groups.reviewable.length + groups.read_only.length;

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (draft.start && draft.end && draft.start > draft.end) {
      setFilterError("Le début de la période doit précéder sa fin.");
      return;
    }
    setFilterError("");
    const next = new URLSearchParams();
    if (draft.statuses.length !== ALL_STATUSES.length)
      next.set("status", draft.statuses.join(","));
    if (draft.employee) next.set("employee", draft.employee);
    if (draft.start) next.set("start", draft.start);
    if (draft.end) next.set("end", draft.end);
    setSearchParams(next);
  }

  function resetFilters() {
    setFilterError("");
    setDraft({
      statuses: [...ALL_STATUSES],
      employee: "",
      start: "",
      end: "",
    });
    setSearchParams(new URLSearchParams());
  }

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Initiatives et validation</p>
          <h1>Propositions de tâches</h1>
          <p>
            Suivez les propositions soumises, en attente de décision, validées
            ou rejetées.
          </p>
        </div>
        <ButtonLink to="nouvelle">Nouvelle proposition</ButtonLink>
      </header>
      {total > 0 && (
        <form className={styles.filters} onSubmit={applyFilters}>
          <fieldset className={styles.statusFilters}>
            <legend>Statut</legend>
            {STATUS_OPTIONS.map((option) => (
              <label key={option.value}>
                <input
                  type="checkbox"
                  checked={draft.statuses.includes(option.value)}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...draft.statuses, option.value]
                      : draft.statuses.filter(
                          (status) => status !== option.value,
                        );
                    if (next.length) setDraft({ ...draft, statuses: next });
                  }}
                />
                {option.label}
              </label>
            ))}
          </fieldset>
          <div className="form-field">
            <label htmlFor="proposal-employee">Collaborateur</label>
            <select
              id="proposal-employee"
              value={draft.employee}
              onChange={(event) =>
                setDraft({ ...draft, employee: event.target.value })
              }
            >
              <option value="">Tous les collaborateurs</option>
              {collaborators.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="proposal-start">Période à partir du</label>
            <FrenchDateInput
              id="proposal-start"
              value={draft.start}
              onValueChange={(start) => setDraft({ ...draft, start })}
            />
          </div>
          <div className="form-field">
            <label htmlFor="proposal-end">Période jusqu'au</label>
            <FrenchDateInput
              id="proposal-end"
              value={draft.end}
              onValueChange={(end) => setDraft({ ...draft, end })}
            />
          </div>
          <div className={styles.filterActions}>
            <Button>
              <Filter size={18} aria-hidden="true" /> Appliquer
            </Button>
            <Button type="button" variant="quiet" onClick={resetFilters}>
              <RotateCcw size={18} aria-hidden="true" /> Réinitialiser
            </Button>
          </div>
          {filterError && (
            <p className={styles.filterError} role="alert">
              {filterError}
            </p>
          )}
        </form>
      )}
      {!total && (
        <EmptyState
          title="Aucune proposition"
          action={<ButtonLink to="nouvelle">Proposer une tâche</ButtonLink>}
        >
          Les propositions que vous soumettez apparaîtront ici.
        </EmptyState>
      )}
      {total > 0 && !visibleTotal && (
        <EmptyState
          title="Aucun résultat"
          action={
            <Button type="button" variant="quiet" onClick={resetFilters}>
              Réinitialiser les filtres
            </Button>
          }
        >
          Aucune proposition ne correspond aux critères appliqués.
        </EmptyState>
      )}
      {visibleTotal > 0 && (
        <p className={styles.resultCount} role="status">
          {visibleTotal} proposition{visibleTotal > 1 ? "s" : ""} affichée
          {visibleTotal > 1 ? "s" : ""}
        </p>
      )}
      <ProposalSection
        title="À examiner"
        items={groups.reviewable}
        reload={reload}
      />
      <ProposalSection
        title="Mes propositions"
        items={groups.own}
        reload={reload}
      />
      <ProposalSection
        title="Visibles dans mon périmètre"
        items={groups.read_only}
        reload={reload}
      />
    </>
  );
}

function ProposalSection({
  title,
  items,
  reload,
}: {
  title: string;
  items: Proposal[];
  reload: () => Promise<void>;
}) {
  if (!items.length) return null;
  return (
    <section className={styles.section}>
      <h2>
        {title} <span className="muted">({items.length})</span>
      </h2>
      <div className="grid">
        {items.map((item) => (
          <ProposalCard key={item.id} proposal={item} reload={reload} />
        ))}
      </div>
    </section>
  );
}

function ProposalCard({
  proposal,
  reload,
}: {
  proposal: Proposal;
  reload: () => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [saving, setSaving] = useState(false);
  const target =
    proposal.accepted_assignment_id !== null
      ? `/taches/${proposal.accepted_assignment_id}`
      : `/propositions/${proposal.id}`;

  async function decide(decision: "accept" | "reject") {
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/proposals/${proposal.id}/decision/`, {
        method: "POST",
        body: JSON.stringify({
          revision: proposal.revision,
          decision,
          reason: decision === "reject" ? reason : "",
        }),
      });
      await reload();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught
          : new Error("Décision non enregistrée"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className={styles.proposal}>
      <header className={styles.header}>
        <div>
          <h3>
            <Link
              to={target}
              className={styles.cardLink}
              aria-label={`Ouvrir ${proposal.title}`}
            >
              {proposal.title}
            </Link>
          </h3>
          <span className="muted">{proposal.employee.name}</span>
        </div>
        <StatusBadge status={proposal.status}>
          {proposal.status_label}
        </StatusBadge>
      </header>
      <p>{proposal.description}</p>
      <div className={styles.meta}>
        <span>Début {formatDate(proposal.start_date)}</span>
        <span>Fin {formatDate(proposal.due_date)}</span>
        <span>{dayCount(proposal.estimated_work_days)}</span>
      </div>
      {proposal.decision_note && (
        <p className="error-banner">{proposal.decision_note}</p>
      )}
      {error && (
        <p className="error-banner" role="alert">
          {error.message}
        </p>
      )}
      {proposal.capabilities.review && (
        <div className={styles.decision}>
          <div className="form-field">
            <label htmlFor={`reason-${proposal.id}`}>
              Motif en cas de rejet
            </label>
            <input
              id={`reason-${proposal.id}`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
          <div className={styles.decisionActions}>
            <Button disabled={saving} onClick={() => void decide("accept")}>
              <CircleCheckBig size={18} aria-hidden="true" /> Valider
            </Button>
            <Button
              variant="danger"
              disabled={saving || !reason.trim()}
              onClick={() => void decide("reject")}
            >
              <XCircle size={18} aria-hidden="true" /> Rejeter
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
