import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import type { PlanningOptions, Proposal } from "../../lib/api/types";
import { apiFetch } from "../../lib/api/client";
import { useApi } from "../../lib/useApi";
import {
  Button,
  ButtonLink,
  Card,
  ErrorState,
  Skeleton,
} from "../../components/ui";

export function ProposalFormPage() {
  const {
    data: options,
    error,
    loading,
    reload,
  } = useApi<PlanningOptions>("/api/v1/planning/options/");
  if (loading) return <Skeleton label="Chargement du formulaire" />;
  if (error || !options)
    return (
      <ErrorState
        error={error ?? new Error("Options indisponibles")}
        retry={reload}
      />
    );
  return <ProposalForm options={options} />;
}

function ProposalForm({ options }: { options: PlanningOptions }) {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);
  const [schedule, setSchedule] = useState(options.defaults);
  const [source, setSource] = useState<"workload" | "due">("workload");
  useEffect(() => {
    const timer = window.setTimeout(async () => {
      try {
        const preview = await apiFetch<typeof schedule>(
          "/api/v1/planning/preview/",
          {
            method: "POST",
            body: JSON.stringify({
              calendar_id: options.defaults.calendar_id,
              start_date: schedule.start_date,
              source,
              due_date: schedule.due_date,
              estimated_work_days: schedule.estimated_work_days,
            }),
          },
        );
        setSchedule({ ...schedule, ...preview });
      } catch {
        /* The API returns precise field errors when the form is submitted. */
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [
    schedule.start_date,
    source === "due" ? schedule.due_date : schedule.estimated_work_days,
  ]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaveError(null);
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<Proposal>("/api/v1/proposals/", {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"),
          description: form.get("description"),
          action_id: form.get("action_id")
            ? Number(form.get("action_id"))
            : null,
          calendar_id: options.defaults.calendar_id,
          start_date: schedule.start_date,
          due_date: schedule.due_date,
          estimated_work_days: schedule.estimated_work_days,
        }),
      });
      navigate("/propositions");
    } catch (caught) {
      setSaveError(
        caught instanceof Error
          ? caught
          : new Error("Proposition non enregistrée"),
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Nouvelle initiative</p>
          <h1>Proposer une tâche</h1>
          <p>
            La proposition sera visible par votre responsable avant d'être
            intégrée à vos engagements.
          </p>
        </div>
      </header>
      {saveError && (
        <div className="error-banner" role="alert">
          {saveError.message}
        </div>
      )}
      <Card>
        <form className="form-grid" onSubmit={submit}>
          <div className="form-field wide">
            <label htmlFor="title">Nom court</label>
            <input id="title" name="title" required maxLength={180} />
          </div>
          <div className="form-field wide">
            <label htmlFor="description">Description</label>
            <textarea id="description" name="description" required />
          </div>
          <div className="form-field wide">
            <label htmlFor="action">
              Action institutionnelle{" "}
              <span className="muted">(facultative)</span>
            </label>
            <select id="action" name="action_id">
              <option value="">Sans action institutionnelle</option>
              {options.actions.map((action) => (
                <option key={action.id} value={action.id}>
                  {action.label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="start">Date de début</label>
            <input
              id="start"
              type="date"
              required
              value={schedule.start_date}
              onChange={(event) =>
                setSchedule({ ...schedule, start_date: event.target.value })
              }
            />
          </div>
          <div className="form-field">
            <label htmlFor="due">Fin prévue</label>
            <input
              id="due"
              type="date"
              required
              value={schedule.due_date}
              onFocus={() => setSource("due")}
              onChange={(event) => {
                setSource("due");
                setSchedule({ ...schedule, due_date: event.target.value });
              }}
            />
          </div>
          <div className="form-field">
            <label htmlFor="workload">Charge estimée</label>
            <input
              id="workload"
              type="number"
              min="0.1"
              step="0.1"
              required
              value={schedule.estimated_work_days}
              onFocus={() => setSource("workload")}
              onChange={(event) => {
                setSource("workload");
                setSchedule({
                  ...schedule,
                  estimated_work_days: event.target.value,
                });
              }}
            />
          </div>
          <div className="cluster wide">
            <Button disabled={saving}>{saving ? "Envoi…" : "Soumettre"}</Button>
            <ButtonLink to="/propositions" variant="quiet">
              Annuler
            </ButtonLink>
          </div>
        </form>
      </Card>
    </>
  );
}
