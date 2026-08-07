import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "../../lib/router";
import type { PlanningOptions, TaskDetail } from "../../lib/api/types";
import { apiFetch, ApiError } from "../../lib/api/client";
import { useApi } from "../../lib/useApi";
import {
  Button,
  ButtonLink,
  Card,
  ErrorState,
  FrenchDateInput,
  Skeleton,
} from "../../components/ui";

export function TaskFormPage({ mode }: { mode: "create" | "edit" }) {
  const { taskId } = useParams();
  const options = useApi<PlanningOptions>("/api/v1/planning/options/");
  const task = useApi<TaskDetail>(`/api/v1/tasks/${taskId}/`, mode === "edit");
  if (options.loading || (mode === "edit" && task.loading))
    return <Skeleton label="Chargement du formulaire" />;
  if (options.error || !options.data)
    return (
      <ErrorState
        error={options.error ?? new Error("Options indisponibles")}
        retry={options.reload}
      />
    );
  if (mode === "edit" && (task.error || !task.data))
    return (
      <ErrorState
        error={task.error ?? new Error("Tâche indisponible")}
        retry={task.reload}
      />
    );
  return (
    <TaskForm
      mode={mode}
      options={options.data}
      task={mode === "edit" ? task.data : null}
    />
  );
}

function TaskForm({
  mode,
  options,
  task,
}: {
  mode: "create" | "edit";
  options: PlanningOptions;
  task: TaskDetail | null;
}) {
  const navigate = useNavigate();
  const initial = task ?? options.defaults;
  const calendarId = task?.calendar.id ?? options.defaults.calendar_id;
  const [schedule, setSchedule] = useState({
    start_date: initial.start_date,
    due_date: initial.due_date,
    estimated_work_days:
      "estimated_work_days" in initial
        ? initial.estimated_work_days
        : options.defaults.estimated_work_days,
  });
  const [source, setSource] = useState<"workload" | "due">("workload");
  const [error, setError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);

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
        /* Field validation is shown after submit; keep editing responsive. */
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [
    schedule.start_date,
    source === "due" ? schedule.due_date : schedule.estimated_work_days,
  ]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const payload = {
      title: form.get("title"),
      description: form.get("description"),
      action_id: form.get("action_id") ? Number(form.get("action_id")) : null,
      start_date: schedule.start_date,
      due_date: schedule.due_date,
      estimated_work_days: schedule.estimated_work_days,
    };
    try {
      const saved =
        mode === "create"
          ? await apiFetch<TaskDetail>("/api/v1/tasks/", {
              method: "POST",
              body: JSON.stringify({
                ...payload,
                employee_id: Number(form.get("employee_id")),
                calendar_id: calendarId,
              }),
            })
          : await apiFetch<TaskDetail>(`/api/v1/tasks/${task?.id}/`, {
              method: "PATCH",
              body: JSON.stringify({ ...payload, revision: task?.revision }),
            });
      navigate(`/taches/${saved.id}`);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("Échec de l'enregistrement", 0, "unknown"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Planification</p>
          <h1>
            {mode === "create" ? "Affecter une tâche" : "Modifier la tâche"}
          </h1>
          <p>
            La date de fin et la charge sont synchronisées à partir du
            calendrier de travail.
          </p>
        </div>
      </header>
      {error && (
        <div className="error-banner" role="alert">
          {error.message}
        </div>
      )}
      <Card>
        <form className="form-grid" onSubmit={onSubmit}>
          <div className="form-field wide">
            <label htmlFor="title">Nom court</label>
            <input
              id="title"
              name="title"
              required
              maxLength={180}
              defaultValue={task?.title ?? ""}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="description">Description</label>
            <textarea
              id="description"
              name="description"
              required
              defaultValue={task?.description ?? ""}
            />
          </div>
          {mode === "create" && (
            <div className="form-field">
              <label htmlFor="employee">Collaborateur</label>
              <select id="employee" name="employee_id" required>
                {options.employees.map((employee) => (
                  <option value={employee.id} key={employee.id}>
                    {employee.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="form-field">
            <label htmlFor="action">
              Action institutionnelle{" "}
              <span className="muted">(facultative)</span>
            </label>
            <select
              id="action"
              name="action_id"
              defaultValue={task?.action?.id ?? ""}
            >
              <option value="">Sans action institutionnelle</option>
              {options.actions.map((action) => (
                <option value={action.id} key={action.id}>
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
            <label htmlFor="workload">Charge estimée (jours ouvrés)</label>
            <input
              id="workload"
              type="number"
              min="0.1"
              step="0.1"
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
            <Button disabled={saving}>
              {saving ? "Enregistrement…" : "Enregistrer"}
            </Button>
            <ButtonLink to={task ? `/taches/${task.id}` : "/"} variant="quiet">
              Annuler
            </ButtonLink>
          </div>
        </form>
      </Card>
    </>
  );
}
