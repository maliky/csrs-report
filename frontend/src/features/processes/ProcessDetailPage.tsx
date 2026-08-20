import { Download, FileUp, Pencil, UserCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useParams } from "../../lib/router";
import {
  Button,
  ButtonLink,
  Card,
  ErrorState,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import type { ProcessDetail } from "../../lib/api/types";
import { apiFetch } from "../../lib/api/client";
import { formatDate, formatDateTime } from "../../lib/format";
import { useApi } from "../../lib/useApi";
import styles from "./processes.module.css";

const STEP_LABELS: Record<string, string> = {
  draft: "Brouillon",
  assistance: "Préparation",
  signature: "Décision DG",
  distribution: "Distribution",
  fleet: "Véhicule",
  completed: "Terminé",
  rejected: "Rejeté",
  abandoned: "Abandonné",
};

const ACTION_LABELS: Record<string, string> = {
  submit: "Soumettre à l'assistance",
  abandon: "Abandonner le brouillon",
  claim: "Prendre en charge",
  takeover: "Reprendre ce dossier",
  send_to_signature: "Transmettre au DG",
  request_correction: "Demander une correction",
  reject: "Rejeter définitivement",
  sign: "Signer et transmettre",
  complete_distribution: "Confirmer la distribution",
  complete_fleet: "Confirmer le véhicule prêt",
  place_legal_hold: "Suspendre la destruction",
  release_legal_hold: "Lever le gel juridique",
};

export function ProcessDetailPage() {
  const { processId } = useParams();
  const { data, error, loading, reload, setData } = useApi<ProcessDetail>(
    `/api/v1/processes/${processId}/`,
  );
  const [saving, setSaving] = useState(false);
  const [mutationError, setMutationError] = useState<Error | null>(null);
  const [note, setNote] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [checklist, setChecklist] = useState({
    accounting_copy: false,
    original_delivered: false,
    archive_copy: false,
  });

  if (loading) return <Skeleton label="Chargement du dossier" />;
  if (error || !data)
    return (
      <ErrorState
        error={error ?? new Error("Dossier indisponible")}
        retry={reload}
      />
    );

  async function act(action: string) {
    setSaving(true);
    setMutationError(null);
    try {
      setData(
        await apiFetch<ProcessDetail>(
          `/api/v1/processes/${data?.id}/actions/`,
          {
            method: "POST",
            body: JSON.stringify({
              revision: data?.revision,
              action,
              note,
              confirmation,
              checklist,
            }),
          },
        ),
      );
      setNote("");
      setConfirmation("");
    } catch (caught) {
      setMutationError(
        caught instanceof Error ? caught : new Error("Action non enregistrée"),
      );
    } finally {
      setSaving(false);
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMutationError(null);
    const form = new FormData(event.currentTarget);
    form.set("revision", String(data?.revision));
    try {
      await apiFetch(`/api/v1/processes/${data?.id}/documents/`, {
        method: "POST",
        body: form,
      });
      event.currentTarget.reset();
      await reload();
    } catch (caught) {
      setMutationError(
        caught instanceof Error ? caught : new Error("Pièce non déposée"),
      );
    } finally {
      setSaving(false);
    }
  }

  const needsReason = data.available_actions.some((action) =>
    [
      "takeover",
      "request_correction",
      "reject",
      "place_legal_hold",
      "release_legal_hold",
    ].includes(action),
  );
  const signing = data.available_actions.includes("sign");
  const distributing = data.available_actions.includes("complete_distribution");

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">
            {data.reference} · {data.mission_type_label}
          </p>
          <h1>{data.destination}</h1>
          <StatusBadge status={data.status}>{data.status_label}</StatusBadge>
        </div>
        <div className="cluster">
          {data.capabilities.edit && (
            <ButtonLink to="modifier" variant="secondary">
              <Pencil size={18} aria-hidden="true" /> Modifier
            </ButtonLink>
          )}
          {data.capabilities.export && (
            <a
              className={styles.exportButton}
              href={`/api/v1/processes/${data.id}/export/`}
            >
              <Download size={18} aria-hidden="true" /> Exporter l'audit
            </a>
          )}
          <ButtonLink to="/processus" variant="quiet">
            Retour
          </ButtonLink>
        </div>
      </header>
      <ol className={styles.steps} aria-label="Avancement du dossier">
        {[
          "draft",
          "assistance",
          "signature",
          "distribution",
          ...(data.mission.vehicle_required ? ["fleet"] : []),
          "completed",
        ].map((step) => (
          <li
            key={step}
            aria-current={data.current_step === step ? "step" : undefined}
            className={data.current_step === step ? styles.currentStep : ""}
          >
            {STEP_LABELS[step]}
          </li>
        ))}
      </ol>
      {mutationError && (
        <div className="error-banner" role="alert">
          {mutationError.message}
        </div>
      )}
      <dl className="details-grid">
        <div className="detail">
          <dt>Demandeur</dt>
          <dd>{data.initiator.name}</dd>
        </div>
        <div className="detail">
          <dt>Service</dt>
          <dd>{data.origin_unit.name}</dd>
        </div>
        <div className="detail">
          <dt>Échéance de l'étape</dt>
          <dd>{data.due_date ? formatDate(data.due_date) : "—"}</dd>
        </div>
        <div className="detail">
          <dt>Départ</dt>
          <dd>{formatDate(data.departure_date)}</dd>
        </div>
        <div className="detail">
          <dt>Retour</dt>
          <dd>{formatDate(data.return_date)}</dd>
        </div>
        <div className="detail">
          <dt>Prise en charge</dt>
          <dd>{data.claimed_by?.name ?? "File de service"}</dd>
        </div>
      </dl>
      <div className={styles.detailGrid}>
        <Card>
          <h2>Mission</h2>
          <p>{data.purpose}</p>
          <dl className={styles.compactDetails}>
            <div>
              <dt>Itinéraire</dt>
              <dd>{data.mission.itinerary || "—"}</dd>
            </div>
            <div>
              <dt>Transport</dt>
              <dd>{data.mission.transport_mode || "—"}</dd>
            </div>
            <div>
              <dt>Financement</dt>
              <dd>{data.mission.funding_source || "—"}</dd>
            </div>
            <div>
              <dt>Véhicule</dt>
              <dd>
                {data.mission.vehicle_required
                  ? data.mission.vehicle_details || "Demandé"
                  : "Non demandé"}
              </dd>
            </div>
          </dl>
          <h3>Participants</h3>
          <ul>
            {data.participants.map((person) => (
              <li key={person.id}>
                {person.name}
                {person.position ? ` — ${person.position}` : ""}
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h2>Pièces</h2>
          {data.documents.length ? (
            <ul className={styles.documents}>
              {data.documents.map((document) => (
                <li key={document.id}>
                  <span>
                    <strong>
                      {document.kind_label}
                      {document.active ? "" : " — version remplacée"}
                    </strong>
                    <small>
                      {document.name} · {(document.size / 1024).toFixed(0)} Kio
                      · antivirus {document.scan_status}
                    </small>
                  </span>
                  {document.download_url && (
                    <a href={document.download_url}>Télécharger</a>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Aucune pièce déposée.</p>
          )}
          {data.capabilities.upload && (
            <form className={styles.uploadForm} onSubmit={upload}>
              <div className="form-field">
                <label htmlFor="document-kind">Nature de la pièce</label>
                <select
                  id="document-kind"
                  name="kind"
                  required
                  defaultValue="terms_of_reference"
                >
                  <option value="terms_of_reference">
                    Termes de référence
                  </option>
                  <option value="invitation">Invitation</option>
                  <option value="ticket">Billet de transport</option>
                  <option value="order_draft">Projet d'ordre de mission</option>
                  <option value="other">Autre pièce</option>
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="document-file">
                  Fichier PDF, DOCX, JPG ou PNG
                </label>
                <input
                  id="document-file"
                  name="file"
                  type="file"
                  accept=".pdf,.docx,.jpg,.jpeg,.png"
                  required
                />
              </div>
              <Button disabled={saving}>
                <FileUp size={18} aria-hidden="true" /> Analyser et déposer
              </Button>
            </form>
          )}
        </Card>
      </div>
      {data.available_actions.length > 0 && (
        <Card className={styles.actionPanel}>
          <h2>
            <UserCheck size={22} aria-hidden="true" /> Action attendue
          </h2>
          {needsReason && (
            <div className="form-field">
              <label htmlFor="process-note">
                Motif obligatoire pour une reprise, une correction ou un rejet
              </label>
              <textarea
                id="process-note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </div>
          )}
          {signing && (
            <div className="form-field">
              <label htmlFor="signature-confirmation">
                Confirmation de signature
              </label>
              <input
                id="signature-confirmation"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder={`SIGNER ${data.reference}`}
                autoComplete="off"
              />
              <small>Saisissez exactement : SIGNER {data.reference}</small>
            </div>
          )}
          {distributing && (
            <fieldset className={styles.checklist}>
              <legend>Distribution effectuée</legend>
              {[
                ["accounting_copy", "Copie transmise à la comptabilité"],
                ["original_delivered", "Original remis au demandeur"],
                ["archive_copy", "Copie classée aux archives"],
              ].map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={checklist[key as keyof typeof checklist]}
                    onChange={(event) =>
                      setChecklist({
                        ...checklist,
                        [key]: event.target.checked,
                      })
                    }
                  />{" "}
                  {label}
                </label>
              ))}
            </fieldset>
          )}
          <div className="cluster">
            {data.available_actions.map((action) => (
              <Button
                key={action}
                variant={
                  ["abandon", "reject"].includes(action)
                    ? "danger"
                    : [
                          "request_correction",
                          "place_legal_hold",
                          "release_legal_hold",
                        ].includes(action)
                      ? "secondary"
                      : "primary"
                }
                disabled={
                  saving ||
                  ([
                    "takeover",
                    "request_correction",
                    "reject",
                    "place_legal_hold",
                    "release_legal_hold",
                  ].includes(action) &&
                    !note.trim()) ||
                  (action === "sign" &&
                    confirmation !== `SIGNER ${data.reference}`)
                }
                onClick={() => void act(action)}
              >
                {ACTION_LABELS[action] ?? action}
              </Button>
            ))}
          </div>
        </Card>
      )}
      <section className={styles.history}>
        <h2>Historique du dossier</h2>
        {data.events.map((event) => (
          <article className="activity" key={event.id}>
            <div className="activity-summary">
              <time>{formatDateTime(event.occurred_at)}</time>
              <span className="activity-author">{event.actor.name}</span>
              <span className="activity-meta">
                {STEP_LABELS[event.to_status] ?? event.to_status}
              </span>
            </div>
            <div className="activity-message">
              <strong>{ACTION_LABELS[event.kind] ?? event.kind}</strong>
              {event.message && <p>{event.message}</p>}
            </div>
          </article>
        ))}
      </section>
      {data.signature && (
        <p className={styles.signatureEvidence}>
          Signé dans CSRS Report par {data.signature.signer.name} le{" "}
          {formatDateTime(data.signature.signed_at)} · empreinte{" "}
          {data.signature.snapshot_sha256}
        </p>
      )}
    </>
  );
}
