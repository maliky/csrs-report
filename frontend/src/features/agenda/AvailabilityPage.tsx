import { CalendarOff, Pencil, Plus, XCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  FrenchDateInput,
  Skeleton,
} from "../../components/ui";
import { apiFetch, ApiError } from "../../lib/api/client";
import type {
  AvailabilityOptions,
  StaffAvailability,
} from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import { formatDate } from "../../lib/format";
import styles from "./agenda.module.css";

function currentWeek(): string {
  const now = new Date();
  const offset = (now.getDay() + 6) % 7;
  const monday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - offset,
  );
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}`;
}

export function AvailabilityPage() {
  const [week, setWeek] = useState(currentWeek);
  const availability = useApi<AvailabilityOptions>(
    `/api/v1/availability/?week=${week}`,
  );
  const [editing, setEditing] = useState<StaffAvailability | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);

  if (availability.loading)
    return <Skeleton label="Chargement des indisponibilités" />;
  if (availability.error || !availability.data)
    return (
      <ErrorState
        error={
          availability.error ?? new Error("Indisponibilités indisponibles")
        }
        retry={availability.reload}
      />
    );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = {
      employee_id: Number(form.get("employee_id")),
      kind: form.get("kind"),
      start_date: form.get("start_date"),
      end_date: form.get("end_date"),
      note: form.get("note"),
    };
    try {
      await apiFetch(
        editing
          ? `/api/v1/availability/${editing.id}/`
          : "/api/v1/availability/",
        {
          method: editing ? "PATCH" : "POST",
          body: JSON.stringify(
            editing ? { ...payload, revision: editing.revision } : payload,
          ),
        },
      );
      setEditing(null);
      formElement.reset();
      await availability.reload();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("Enregistrement impossible", 0, "unknown"),
      );
    } finally {
      setSaving(false);
    }
  }

  async function cancel(item: StaffAvailability) {
    const reason = window.prompt("Motif de l’annulation");
    if (!reason) return;
    await apiFetch(`/api/v1/availability/${item.id}/cancel/`, {
      method: "POST",
      body: JSON.stringify({ revision: item.revision, reason }),
    });
    await availability.reload();
  }

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Ressources humaines</p>
          <h1>Absences et missions</h1>
          <p>
            Déclarez les congés, absences et missions qui alimenteront l’agenda
            de direction.
          </p>
        </div>
        <label className={styles.weekPicker}>
          Semaine
          <FrenchDateInput required value={week} onValueChange={setWeek} />
        </label>
      </header>
      {error && (
        <div className="error-banner" role="alert">
          {error.message}
        </div>
      )}
      <Card>
        <h2>
          <CalendarOff size={21} aria-hidden="true" />{" "}
          {editing ? "Corriger l’indisponibilité" : "Nouvelle indisponibilité"}
        </h2>
        <form
          className="form-grid"
          onSubmit={submit}
          key={editing?.id ?? "new"}
        >
          <div className="form-field">
            <label htmlFor="employee">Agent</label>
            <select
              id="employee"
              name="employee_id"
              required
              defaultValue={editing?.employee.id}
            >
              {availability.data.employees.map((employee) => (
                <option value={employee.id} key={employee.id}>
                  {employee.name} — {employee.position}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="kind">Nature</label>
            <select id="kind" name="kind" required defaultValue={editing?.kind}>
              {availability.data.kinds.map((kind) => (
                <option value={kind.value} key={kind.value}>
                  {kind.label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="start-date">Début</label>
            <FrenchDateInput
              id="start-date"
              name="start_date"
              required
              defaultValue={editing?.start_date ?? week}
            />
          </div>
          <div className="form-field">
            <label htmlFor="end-date">Fin</label>
            <FrenchDateInput
              id="end-date"
              name="end_date"
              required
              defaultValue={editing?.end_date ?? week}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="availability-note">
              Observation <span className="muted">(facultative)</span>
            </label>
            <textarea
              id="availability-note"
              name="note"
              defaultValue={editing?.note}
            />
          </div>
          <div className={`${styles.actions} wide`}>
            <Button disabled={saving}>
              <Plus size={18} aria-hidden="true" />{" "}
              {saving
                ? "Enregistrement…"
                : editing
                  ? "Enregistrer la correction"
                  : "Ajouter"}
            </Button>
            {editing && (
              <Button
                type="button"
                variant="quiet"
                onClick={() => setEditing(null)}
              >
                Annuler la correction
              </Button>
            )}
          </div>
        </form>
      </Card>
      <section className={styles.versions}>
        <div className={styles.sectionHeading}>
          <div>
            <p className="eyebrow">Semaine sélectionnée</p>
            <h2>Indisponibilités déclarées</h2>
          </div>
        </div>
        {availability.data.items.length === 0 ? (
          <EmptyState title="Aucune indisponibilité">
            Aucun congé, absence ou mission ne couvre cette semaine.
          </EmptyState>
        ) : (
          <div className="stack">
            {availability.data.items.map((item) => (
              <Card className={styles.version} key={item.id}>
                <div>
                  <strong>
                    {item.employee.name} — {item.kind_label}
                  </strong>
                  <small>
                    Du {formatDate(item.start_date)} au{" "}
                    {formatDate(item.end_date)}
                    {item.note ? ` — ${item.note}` : ""}
                  </small>
                </div>
                <div className={styles.actions}>
                  <Button variant="secondary" onClick={() => setEditing(item)}>
                    <Pencil size={17} aria-hidden="true" /> Corriger
                  </Button>
                  <Button variant="danger" onClick={() => void cancel(item)}>
                    <XCircle size={17} aria-hidden="true" /> Annuler
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
