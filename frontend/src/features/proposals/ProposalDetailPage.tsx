import { CircleCheckBig, Pencil, RotateCcw, XCircle } from "lucide-react";
import { useState } from "react";
import { useParams } from "../../lib/router";
import type { Proposal } from "../../lib/api/types";
import { apiFetch } from "../../lib/api/client";
import { useApi } from "../../lib/useApi";
import { dayCount, formatDate } from "../../lib/format";
import {
  Button,
  ButtonLink,
  Card,
  ErrorState,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import styles from "./proposals.module.css";

export function ProposalDetailPage() {
  const { proposalId } = useParams();
  const { data, error, loading, reload, setData } = useApi<Proposal>(
    `/api/v1/proposals/${proposalId}/`,
  );
  const [saving, setSaving] = useState(false);
  const [mutationError, setMutationError] = useState<Error | null>(null);
  const [reason, setReason] = useState("");

  if (loading) return <Skeleton label="Chargement de la proposition" />;
  if (error || !data)
    return (
      <ErrorState
        error={error ?? new Error("Proposition indisponible")}
        retry={reload}
      />
    );

  async function mutate(path: string, body: object) {
    setSaving(true);
    setMutationError(null);
    try {
      setData(
        await apiFetch<Proposal>(path, {
          method: "POST",
          body: JSON.stringify(body),
        }),
      );
      setReason("");
    } catch (caught) {
      setMutationError(
        caught instanceof Error ? caught : new Error("Action non enregistrée"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Proposition de {data.employee.name}</p>
          <h1>{data.title}</h1>
          <StatusBadge status={data.status}>{data.status_label}</StatusBadge>
        </div>
        <div className="cluster">
          {data.capabilities.edit && (
            <ButtonLink to="modifier" variant="secondary">
              <Pencil size={18} aria-hidden="true" /> Modifier
            </ButtonLink>
          )}
          {data.accepted_assignment_id !== null && (
            <ButtonLink to={`/taches/${data.accepted_assignment_id}`}>
              Voir la progression
            </ButtonLink>
          )}
          <ButtonLink to="/propositions" variant="quiet">
            Retour
          </ButtonLink>
        </div>
      </header>
      {mutationError && (
        <div className="error-banner" role="alert">
          {mutationError.message}
        </div>
      )}
      <dl className="details-grid">
        <div className="detail">
          <dt>Date de début</dt>
          <dd>{formatDate(data.start_date)}</dd>
        </div>
        <div className="detail">
          <dt>Fin prévue</dt>
          <dd>{formatDate(data.due_date)}</dd>
        </div>
        <div className="detail">
          <dt>Charge estimée</dt>
          <dd>{dayCount(data.estimated_work_days)}</dd>
        </div>
      </dl>
      <Card className={styles.detailCard}>
        <h2>Description</h2>
        <p>{data.description}</p>
        <p className="muted">
          {data.action
            ? `Action institutionnelle : ${data.action.label}`
            : "Sans action institutionnelle"}
        </p>
      </Card>
      {data.decision_note && (
        <div className="error-banner">
          <strong>Motif de la décision</strong>
          <p>{data.decision_note}</p>
        </div>
      )}
      {data.capabilities.resubmit && (
        <div className={styles.detailActions}>
          <Button
            disabled={saving}
            onClick={() =>
              void mutate(`/api/v1/proposals/${data.id}/resubmit/`, {
                revision: data.revision,
              })
            }
          >
            <RotateCcw size={18} aria-hidden="true" /> Corriger et resoumettre
          </Button>
        </div>
      )}
      {data.capabilities.review && (
        <Card className={styles.reviewPanel}>
          <h2>Décision</h2>
          <div className="form-field">
            <label htmlFor="decision-reason">Motif en cas de rejet</label>
            <input
              id="decision-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
          <div className={styles.decisionActions}>
            <Button
              disabled={saving}
              onClick={() =>
                void mutate(`/api/v1/proposals/${data.id}/decision/`, {
                  revision: data.revision,
                  decision: "accept",
                  reason: "",
                })
              }
            >
              <CircleCheckBig size={18} aria-hidden="true" /> Valider
            </Button>
            <Button
              variant="danger"
              disabled={saving || !reason.trim()}
              onClick={() =>
                void mutate(`/api/v1/proposals/${data.id}/decision/`, {
                  revision: data.revision,
                  decision: "reject",
                  reason,
                })
              }
            >
              <XCircle size={18} aria-hidden="true" /> Rejeter
            </Button>
          </div>
        </Card>
      )}
    </>
  );
}
