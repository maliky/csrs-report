import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { TaskDetail } from "../../lib/api/types";
import { apiFetch } from "../../lib/api/client";
import { useApi } from "../../lib/useApi";
import { dayCount, formatDate, formatDateTime } from "../../lib/format";
import {
  Button,
  ButtonLink,
  Card,
  ErrorState,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import { ProgressChart } from "./ProgressChart";
import styles from "./tasks.module.css";

export function TaskDetailPage() {
  const { taskId } = useParams();
  const endpoint = `/api/v1/tasks/${taskId}/`;
  const { data, error, loading, reload, setData } =
    useApi<TaskDetail>(endpoint);
  const [mutationError, setMutationError] = useState<Error | null>(null);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  async function mutate(path: string, body: object) {
    setSaving(true);
    setMutationError(null);
    try {
      setData(
        await apiFetch<TaskDetail>(path, {
          method: "POST",
          body: JSON.stringify(body),
        }),
      );
    } catch (caught) {
      setMutationError(
        caught instanceof Error
          ? caught
          : new Error("Échec de l'enregistrement"),
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Skeleton label="Chargement de la tâche" />;
  if (error || !data)
    return (
      <ErrorState
        error={error ?? new Error("Tâche indisponible")}
        retry={reload}
      />
    );
  return (
    <>
      <header className={styles.detailHeader}>
        <div>
          <p className="eyebrow">{data.code}</p>
          <h1>{data.title}</h1>
          <div className="cluster">
            <StatusBadge status={data.status}>{data.status_label}</StatusBadge>
            <strong>{data.percentage} % réalisé</strong>
          </div>
        </div>
        <div className="cluster">
          {data.capabilities.manage && (
            <ButtonLink to="modifier" variant="secondary">
              Modifier
            </ButtonLink>
          )}
          <Button variant="quiet" onClick={() => navigate(-1)}>
            Retour
          </Button>
        </div>
      </header>
      {mutationError && (
        <div className="error-banner" role="alert">
          <strong>Modification non enregistrée.</strong> {mutationError.message}{" "}
          <Button variant="quiet" onClick={() => void reload()}>
            Actualiser
          </Button>
        </div>
      )}
      <dl className="details-grid">
        <div className="detail">
          <dt>Date de début</dt>
          <dd>{formatDate(data.start_date)}</dd>
        </div>
        <div className="detail">
          <dt>Date du jour</dt>
          <dd>{formatDate(data.today)}</dd>
        </div>
        <div className="detail">
          <dt>Fin prévue</dt>
          <dd>{formatDate(data.due_date)}</dd>
        </div>
        <div className="detail">
          <dt>Charge initiale</dt>
          <dd>{dayCount(data.workload.total)}</dd>
        </div>
        <div className="detail">
          <dt>Charge réalisée</dt>
          <dd>{dayCount(data.workload.completed)}</dd>
        </div>
        <div className="detail">
          <dt>Charge restante</dt>
          <dd>{dayCount(data.workload.remaining)}</dd>
        </div>
      </dl>
      <div className={styles.detailColumns} style={{ marginTop: "1.5rem" }}>
        <div className="stack">
          <Card>
            <h2>Progression dans le temps</h2>
            <ProgressChart points={data.chart} today={data.today} />
          </Card>
          <Card>
            <h2>Description</h2>
            <p>{data.description}</p>
            {data.action && (
              <p className="muted">
                Action institutionnelle : {data.action.label}
              </p>
            )}
          </Card>
          <Card>
            <h2>Conversation et observations</h2>
            {data.activities.length ? (
              <div>
                {data.activities.map((activity) => (
                  <article className="activity" key={activity.id}>
                    <time dateTime={activity.occurred_at}>
                      {formatDateTime(activity.occurred_at)}
                    </time>
                    <span className="activity-meta">
                      {activity.actor_short_name} ·{" "}
                      {activity.kind === "progress"
                        ? "Progression"
                        : "Observation"}
                      {activity.percentage_after !== null
                        ? ` ${activity.percentage_after} %`
                        : ""}
                    </span>
                    <div>{activity.message}</div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">Aucune observation pour le moment.</p>
            )}
          </Card>
        </div>
        <aside
          className={`${styles.sticky} stack`}
          aria-label="Actions sur la tâche"
        >
          {data.capabilities.update_progress && (
            <ProgressForm
              task={data}
              saving={saving}
              submit={(body) =>
                mutate(`/api/v1/tasks/${data.id}/progress/`, body)
              }
            />
          )}
          {data.capabilities.comment && (
            <ObservationForm
              task={data}
              saving={saving}
              submit={(body) =>
                mutate(`/api/v1/tasks/${data.id}/observations/`, body)
              }
            />
          )}
          {data.capabilities.manage && (
            <TransitionActions
              task={data}
              saving={saving}
              submit={(body) =>
                mutate(`/api/v1/tasks/${data.id}/transition/`, body)
              }
            />
          )}
        </aside>
      </div>
    </>
  );
}

function ProgressForm({
  task,
  saving,
  submit,
}: {
  task: TaskDetail;
  saving: boolean;
  submit: (body: object) => Promise<void>;
}) {
  const [percentage, setPercentage] = useState(task.percentage);
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void submit({
      revision: task.revision,
      entry_date: task.today,
      percentage,
      note: form.get("note"),
      blocked: form.get("blocked") === "on",
    });
  }
  return (
    <Card>
      <form className="stack" onSubmit={onSubmit}>
        <div>
          <p className="eyebrow">Mise à jour quotidienne</p>
          <h2>Progression</h2>
        </div>
        <label className="legend" htmlFor="percentage">
          Avancement <span className="progress-value">{percentage} %</span>
        </label>
        <input
          className="progress-input"
          id="percentage"
          type="range"
          min="0"
          max="100"
          step="5"
          value={percentage}
          onChange={(event) => setPercentage(Number(event.target.value))}
        />
        <div className="form-field">
          <label htmlFor="progress-note">Observation</label>
          <textarea
            id="progress-note"
            name="note"
            placeholder="Résultat obtenu, difficulté ou prochaine étape"
          />
        </div>
        <label>
          <input type="checkbox" name="blocked" />{" "}
          {task.capabilities.self_managed
            ? "Signaler un point d'attention"
            : "Je suis bloqué"}
        </label>
        <Button disabled={saving}>Enregistrer la progression</Button>
      </form>
    </Card>
  );
}

function ObservationForm({
  task,
  saving,
  submit,
}: {
  task: TaskDetail;
  saving: boolean;
  submit: (body: object) => Promise<void>;
}) {
  const [message, setMessage] = useState("");
  return (
    <Card>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          void submit({ revision: task.revision, message }).then(() =>
            setMessage(""),
          );
        }}
      >
        <h2>Ajouter une observation</h2>
        <div className="form-field">
          <label htmlFor="observation">Message</label>
          <textarea
            id="observation"
            required
            value={message}
            onChange={(event) => setMessage(event.target.value)}
          />
        </div>
        <Button variant="secondary" disabled={saving}>
          Publier
        </Button>
      </form>
    </Card>
  );
}

function TransitionActions({
  task,
  saving,
  submit,
}: {
  task: TaskDetail;
  saving: boolean;
  submit: (body: object) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  return (
    <Card>
      <div className={styles.actions}>
        <h2>Décision</h2>
        {task.status === "awaiting_validation" && (
          <>
            <Button
              disabled={saving}
              onClick={() =>
                void submit({
                  revision: task.revision,
                  transition: "validate",
                  reason: "",
                })
              }
            >
              Valider l'achèvement
            </Button>
            <div className="form-field">
              <label htmlFor="decision-reason">Motif</label>
              <textarea
                id="decision-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
            <Button
              variant="secondary"
              disabled={saving || !reason.trim()}
              onClick={() =>
                void submit({
                  revision: task.revision,
                  transition: "reject",
                  reason,
                })
              }
            >
              Demander une reprise
            </Button>
          </>
        )}
        {task.status !== "closed_early" && task.status !== "completed" && (
          <>
            <div className="form-field">
              <label htmlFor="close-reason">Motif de clôture anticipée</label>
              <textarea
                id="close-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </div>
            <Button
              variant="danger"
              disabled={saving || !reason.trim()}
              onClick={() =>
                void submit({
                  revision: task.revision,
                  transition: "close_early",
                  reason,
                })
              }
            >
              Clôturer avant achèvement
            </Button>
          </>
        )}
      </div>
    </Card>
  );
}
