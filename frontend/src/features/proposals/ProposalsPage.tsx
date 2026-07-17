import { useState } from "react";
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
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import styles from "./proposals.module.css";

export function ProposalsPage() {
  const { data, error, loading, reload } =
    useApi<ProposalGroups>("/api/v1/proposals/");
  if (loading) return <Skeleton label="Chargement des propositions" />;
  if (error || !data)
    return (
      <ErrorState
        error={error ?? new Error("Propositions indisponibles")}
        retry={reload}
      />
    );
  const hasAny =
    data.own.length + data.reviewable.length + data.read_only.length > 0;
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
      {!hasAny && (
        <EmptyState
          title="Aucune proposition"
          action={<ButtonLink to="nouvelle">Proposer une tâche</ButtonLink>}
        >
          Les propositions que vous soumettez apparaîtront ici.
        </EmptyState>
      )}
      <ProposalSection
        title="À examiner"
        items={data.reviewable}
        review
        reload={reload}
      />
      <ProposalSection
        title="Mes propositions"
        items={data.own}
        reload={reload}
      />
      <ProposalSection
        title="Visibles dans mon périmètre"
        items={data.read_only}
        reload={reload}
      />
    </>
  );
}

function ProposalSection({
  title,
  items,
  review = false,
  reload,
}: {
  title: string;
  items: Proposal[];
  review?: boolean;
  reload: () => Promise<void>;
}) {
  if (!items.length) return null;
  return (
    <section className={styles.section}>
      <h2>{title}</h2>
      <div className="grid">
        {items.map((item) => (
          <ProposalCard
            key={item.id}
            proposal={item}
            review={review}
            reload={reload}
          />
        ))}
      </div>
    </section>
  );
}

function ProposalCard({
  proposal,
  review,
  reload,
}: {
  proposal: Proposal;
  review: boolean;
  reload: () => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [saving, setSaving] = useState(false);
  async function decide(decision: "accept" | "reject") {
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/proposals/${proposal.id}/decision/`, {
        method: "POST",
        body: JSON.stringify({ revision: proposal.revision, decision, reason }),
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
          <h3>{proposal.title}</h3>
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
      {review && proposal.can_review && (
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
          <Button disabled={saving} onClick={() => void decide("accept")}>
            Valider
          </Button>
          <Button
            variant="danger"
            disabled={saving || !reason.trim()}
            onClick={() => void decide("reject")}
          >
            Rejeter
          </Button>
        </div>
      )}
    </Card>
  );
}
