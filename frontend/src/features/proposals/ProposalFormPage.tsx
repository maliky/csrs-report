import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "../../lib/router";
import type { PlanningOptions, Proposal } from "../../lib/api/types";
import { apiFetch } from "../../lib/api/client";
import { useApi } from "../../lib/useApi";
import {
  Button,
  ButtonLink,
  Card,
  ErrorState,
  FrenchDateInput,
  Skeleton,
} from "../../components/ui";

type WorkloadUnit = "days" | "hours";
const HOURS_PER_WORKDAY = 8;

function workloadInputFromDays(
  estimatedWorkDays: string,
  unit: WorkloadUnit,
): string {
  const days = Number.parseFloat(estimatedWorkDays);
  if (!Number.isFinite(days) || days <= 0) return "";
  if (unit === "hours") {
    return Math.max(1, Math.round(days * HOURS_PER_WORKDAY)).toString();
  }
  return Number(days).toString();
}

function estimatedWorkDaysFromInput(
  input: string,
  unit: WorkloadUnit,
): string | null {
  const parsed = Number.parseFloat(input);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  if (unit === "days") return parsed.toFixed(1);
  return (parsed / HOURS_PER_WORKDAY).toFixed(1);
}

export function ProposalFormPage({ mode }: { mode: "create" | "edit" }) {
  const { proposalId } = useParams();
  const options = useApi<PlanningOptions>("/api/v1/planning/options/");
  const proposal = useApi<Proposal>(
    `/api/v1/proposals/${proposalId}/`,
    mode === "edit",
  );
  if (options.loading || (mode === "edit" && proposal.loading))
    return <Skeleton label="Chargement du formulaire" />;
  if (options.error || !options.data)
    return (
      <ErrorState
        error={options.error ?? new Error("Options indisponibles")}
        retry={options.reload}
      />
    );
  if (mode === "edit" && (proposal.error || !proposal.data))
    return (
      <ErrorState
        error={proposal.error ?? new Error("Proposition indisponible")}
        retry={proposal.reload}
      />
    );
  if (mode === "edit" && !proposal.data?.capabilities.edit)
    return (
      <ErrorState
        error={new Error("Cette proposition ne peut plus être modifiée.")}
      />
    );
  return (
    <ProposalForm
      mode={mode}
      options={options.data}
      proposal={mode === "edit" ? (proposal.data ?? null) : null}
    />
  );
}

function ProposalForm({
  mode,
  options,
  proposal,
}: {
  mode: "create" | "edit";
  options: PlanningOptions;
  proposal: Proposal | null;
}) {
  const navigate = useNavigate();
  const calendarId = proposal?.calendar.id ?? options.defaults.calendar_id;
  const initialEstimatedWorkDays =
    proposal?.estimated_work_days ?? options.defaults.estimated_work_days;
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);
  const [workloadUnit, setWorkloadUnit] = useState<WorkloadUnit>("days");
  const [workloadInputValue, setWorkloadInputValue] = useState(() =>
    workloadInputFromDays(initialEstimatedWorkDays, "days"),
  );
  const [schedule, setSchedule] = useState({
    start_date: proposal?.start_date ?? options.defaults.start_date,
    due_date: proposal?.due_date ?? options.defaults.due_date,
    estimated_work_days: initialEstimatedWorkDays,
  });
  const [source, setSource] = useState<"workload" | "due">("workload");

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      try {
        const preview = await apiFetch<typeof schedule>(
          "/api/v1/planning/preview/",
          {
            method: "POST",
            body: JSON.stringify({
              calendar_id: calendarId,
              start_date: schedule.start_date,
              source,
              due_date: schedule.due_date,
              estimated_work_days: schedule.estimated_work_days,
            }),
          },
        );
        setSchedule(preview);
      } catch {
        /* The API returns precise field errors when the form is submitted. */
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [
    calendarId,
    schedule.start_date,
    source,
    source === "due" ? schedule.due_date : schedule.estimated_work_days,
  ]);

  useEffect(() => {
    const nextValue = workloadInputFromDays(
      schedule.estimated_work_days,
      workloadUnit,
    );
    if (source !== "workload" && nextValue !== workloadInputValue) {
      setWorkloadInputValue(nextValue);
    }
  }, [schedule.estimated_work_days, workloadUnit, workloadInputValue, source]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaveError(null);
    const form = new FormData(event.currentTarget);
    const payload = {
      title: form.get("title"),
      description: form.get("description"),
      action_id: form.get("action_id") ? Number(form.get("action_id")) : null,
      calendar_id: calendarId,
      start_date: schedule.start_date,
      due_date: schedule.due_date,
      estimated_work_days: schedule.estimated_work_days,
    };
    try {
      const saved = await apiFetch<Proposal>(
        mode === "create"
          ? "/api/v1/proposals/"
          : `/api/v1/proposals/${proposal?.id}/`,
        {
          method: mode === "create" ? "POST" : "PATCH",
          body: JSON.stringify(
            mode === "create"
              ? payload
              : { ...payload, revision: proposal?.revision },
          ),
        },
      );
      navigate(`/propositions/${saved.id}`);
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
          <p className="eyebrow">
            {mode === "create" ? "Nouvelle initiative" : "Correction"}
          </p>
          <h1>
            {mode === "create"
              ? "Proposer une tâche"
              : "Modifier la proposition"}
          </h1>
          <p>
            {mode === "create"
              ? "La proposition sera visible par votre responsable avant d'être intégrée à vos engagements."
              : "La proposition conserve son statut actuel jusqu'à une éventuelle resoumission."}
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
            <input
              id="title"
              name="title"
              required
              maxLength={180}
              defaultValue={proposal?.title ?? ""}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="description">Description</label>
            <textarea
              id="description"
              name="description"
              required
              defaultValue={proposal?.description ?? ""}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="action">
              Action institutionnelle{" "}
              <span className="muted">(facultative)</span>
            </label>
            <select
              id="action"
              name="action_id"
              defaultValue={proposal?.action?.id ?? ""}
            >
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
            <FrenchDateInput
              id="start"
              required
              value={schedule.start_date}
              onValueChange={(startDate) =>
                setSchedule({ ...schedule, start_date: startDate })
              }
            />
          </div>
          <div className="form-field">
            <label htmlFor="due">Fin prévue</label>
            <FrenchDateInput
              id="due"
              required
              value={schedule.due_date}
              onFocus={() => setSource("due")}
              onValueChange={(dueDate) => {
                setSource("due");
                setSchedule({ ...schedule, due_date: dueDate });
              }}
            />
          </div>
          <div className="form-field">
            <label htmlFor="workload-unit">Unité</label>
            <select
              id="workload-unit"
              value={workloadUnit}
              onChange={(event) => {
                const unit = event.target.value as WorkloadUnit;
                setSource("workload");
                setWorkloadUnit(unit);
                setWorkloadInputValue(
                  unit === "days"
                    ? workloadInputFromDays(
                        schedule.estimated_work_days,
                        unit,
                      )
                    : "",
                );
              }}
            >
              <option value="days">Jours</option>
              <option value="hours">Heures</option>
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="workload">
              {workloadUnit === "days"
                ? "Charge estimée (jours ouvrés)"
                : "Charge estimée (heures)"}
            </label>
            <input
              id="workload"
              type="number"
              min={workloadUnit === "days" ? "0.5" : "1"}
              step={workloadUnit === "days" ? "0.5" : "1"}
              required
              value={workloadInputValue}
              onFocus={(event) => {
                setSource("workload");
                event.currentTarget.select();
              }}
              onChange={(event) => {
                setSource("workload");
                const nextInput = event.target.value;
                const baseline = workloadInputFromDays(
                  schedule.estimated_work_days,
                  workloadUnit,
                );
                const nextInputValue =
                  nextInput.length > baseline.length &&
                  nextInput.startsWith(baseline)
                    ? nextInput.slice(baseline.length) || ""
                    : nextInput;
                setWorkloadInputValue(nextInputValue);
                const nextDays = estimatedWorkDaysFromInput(
                  nextInputValue,
                  workloadUnit,
                );
                if (nextDays === null) return;
                setSchedule((current) => ({
                  ...current,
                  estimated_work_days: nextDays,
                }));
              }}
            />
          </div>
          <div className="cluster wide">
            <Button disabled={saving}>
              {saving
                ? "Enregistrement…"
                : mode === "create"
                  ? "Soumettre"
                  : "Enregistrer les modifications"}
            </Button>
            <ButtonLink
              to={proposal ? `/propositions/${proposal.id}` : "/propositions"}
              variant="quiet"
            >
              Annuler
            </ButtonLink>
          </div>
        </form>
      </Card>
    </>
  );
}
