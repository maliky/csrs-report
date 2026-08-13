import {
  ArrowDownToLine,
  DoorOpen,
  FileText,
  LogOut,
  Plus,
  Save,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
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
  AgendaDirection,
  AgendaPreview,
  AgendaVersions,
  Session,
  VisitList,
  VisitorVisit,
} from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import { formatDate, formatDateTime } from "../../lib/format";
import styles from "./agenda.module.css";

function localIsoDate(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function addDays(value: Date, days: number): Date {
  return new Date(
    value.getFullYear(),
    value.getMonth(),
    value.getDate() + days,
  );
}

function defaultAgendaPeriod(value = new Date()): [string, string] {
  const dayFromMonday = (value.getDay() + 6) % 7;
  const nextMonday = addDays(value, 7 - dayFromMonday);
  return [localIsoDate(nextMonday), localIsoDate(addDays(nextMonday, 6))];
}

function periodValidation(start: string, end: string): string {
  const startDate = new Date(`${start}T12:00:00`);
  const endDate = new Date(`${end}T12:00:00`);
  const dayCount =
    Math.round((endDate.getTime() - startDate.getTime()) / 86400000) + 1;
  if (dayCount < 1) return "La date de fin doit suivre la date de début.";
  if (dayCount > 31)
    return "La période ne peut pas dépasser 31 jours inclusifs.";
  return "";
}

export function AgendaPage() {
  const session = useApi<Session>("/api/v1/session/");
  if (session.loading) return <Skeleton label="Chargement de l’agenda" />;
  if (session.error || !session.data)
    return (
      <ErrorState
        error={session.error ?? new Error("Session indisponible")}
        retry={session.reload}
      />
    );
  if (!session.data.capabilities.view_weekly_agenda)
    return (
      <ErrorState
        error={new Error("Cet agenda n’est pas accessible avec votre rôle.")}
      />
    );
  return session.data.capabilities.prepare_weekly_agenda ? (
    <SecretaryAgenda />
  ) : (
    <AgendaArchives />
  );
}

function SecretaryAgenda() {
  const initialPeriod = defaultAgendaPeriod();
  const [periodStart, setPeriodStart] = useState(initialPeriod[0]);
  const [periodEnd, setPeriodEnd] = useState(initialPeriod[1]);
  const [agendaDirection, setAgendaDirection] =
    useState<AgendaDirection>("programs");
  const periodQuery = `period_start=${periodStart}&period_end=${periodEnd}`;
  const preview = useApi<AgendaPreview>(
    `/api/v1/agenda/preview/?${periodQuery}&agenda_direction=${agendaDirection}`,
  );
  const visits = useApi<VisitList>(`/api/v1/visits/?${periodQuery}`);
  const versions = useApi<AgendaVersions>(
    `/api/v1/agenda/versions/?${periodQuery}`,
  );
  const [majorEvents, setMajorEvents] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const invalidPeriod = periodValidation(periodStart, periodEnd);

  useEffect(() => {
    setMajorEvents(preview.data?.draft.major_events ?? "");
  }, [preview.data?.draft.major_events, periodStart, periodEnd]);

  async function saveDraft(): Promise<void> {
    if (invalidPeriod) throw new Error(invalidPeriod);
    await apiFetch("/api/v1/agenda/draft/", {
      method: "PUT",
      body: JSON.stringify({
        period_start: periodStart,
        period_end: periodEnd,
        major_events: majorEvents,
        revision: preview.data?.draft.revision ?? 0,
      }),
    });
    await preview.reload();
  }

  async function saveOnly() {
    setSaving(true);
    setError(null);
    setMessage("");
    try {
      await saveDraft();
      setMessage("Le brouillon partagé par les deux agendas est enregistré.");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError(
              caught instanceof Error
                ? caught.message
                : "Enregistrement impossible",
              0,
              "unknown",
            ),
      );
    } finally {
      setSaving(false);
    }
  }

  async function generate(direction: AgendaDirection) {
    setSaving(true);
    setError(null);
    setMessage("");
    try {
      await saveDraft();
      await apiFetch("/api/v1/agenda/versions/", {
        method: "POST",
        body: JSON.stringify({
          period_start: periodStart,
          period_end: periodEnd,
          agenda_direction: direction,
        }),
      });
      await versions.reload();
      const label =
        direction === "programs"
          ? "Direction des programmes"
          : "Direction administrative";
      setMessage(
        `La nouvelle version PDF « ${label} » est archivée et prête à imprimer.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("Génération impossible", 0, "unknown"),
      );
    } finally {
      setSaving(false);
    }
  }

  if (preview.loading || visits.loading || versions.loading)
    return <Skeleton label="Préparation de l’agenda" />;
  if (preview.error || !preview.data)
    return (
      <ErrorState
        error={preview.error ?? new Error("Aperçu indisponible")}
        retry={preview.reload}
      />
    );

  const snapshot = preview.data.snapshot;
  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Rapport de direction</p>
          <h1>Agendas de direction</h1>
          <p>
            Choisissez une période, contrôlez chaque synthèse puis générez les
            deux PDF indépendamment.
          </p>
        </div>
        <div className={styles.periodPicker}>
          <label>
            Début
            <FrenchDateInput
              required
              value={periodStart}
              onValueChange={setPeriodStart}
            />
          </label>
          <label>
            Fin
            <FrenchDateInput
              required
              value={periodEnd}
              onValueChange={setPeriodEnd}
            />
          </label>
          {invalidPeriod && <span role="alert">{invalidPeriod}</span>}
        </div>
      </header>
      {error && (
        <div className="error-banner" role="alert">
          {error.message}
        </div>
      )}
      {message && (
        <div className={styles.success} role="status">
          {message}
        </div>
      )}

      <div className={styles.twoColumns}>
        <VisitorPanel
          visits={visits.data?.visits ?? []}
          reload={async () => {
            await visits.reload();
            await preview.reload();
          }}
        />
        <Card>
          <h2>Événements majeurs</h2>
          <div className="form-field">
            <label htmlFor="major-events">
              Éléments à faire apparaître en tête du rapport
            </label>
            <textarea
              id="major-events"
              value={majorEvents}
              onChange={(event) => setMajorEvents(event.target.value)}
              placeholder="Saisir RAS ou les événements marquants…"
            />
          </div>
          <div className={styles.actions}>
            <Button
              variant="secondary"
              onClick={() => void saveOnly()}
              disabled={saving || Boolean(invalidPeriod)}
            >
              <Save size={18} aria-hidden="true" /> Enregistrer le brouillon
            </Button>
            <Button
              onClick={() => void generate("programs")}
              disabled={saving || Boolean(invalidPeriod)}
            >
              <FileText size={18} aria-hidden="true" />{" "}
              {saving ? "Génération…" : "Générer — Direction des programmes"}
            </Button>
            <Button
              onClick={() => void generate("administration")}
              disabled={saving || Boolean(invalidPeriod)}
            >
              <FileText size={18} aria-hidden="true" />{" "}
              {saving ? "Génération…" : "Générer — Direction administrative"}
            </Button>
          </div>
        </Card>
      </div>

      <section className={styles.preview} aria-labelledby="preview-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className="eyebrow">Aperçu des données</p>
            <h2 id="preview-title">
              {snapshot.agenda_direction_label} · du{" "}
              {formatDate(snapshot.period_start)} au{" "}
              {formatDate(snapshot.period_end)}
            </h2>
          </div>
          <div
            className={styles.directionPicker}
            role="group"
            aria-label="Agenda affiché"
          >
            <Button
              variant={agendaDirection === "programs" ? "primary" : "secondary"}
              onClick={() => setAgendaDirection("programs")}
            >
              Direction des programmes
            </Button>
            <Button
              variant={
                agendaDirection === "administration" ? "primary" : "secondary"
              }
              onClick={() => setAgendaDirection("administration")}
            >
              Direction administrative
            </Button>
          </div>
        </div>
        {snapshot.unclassified_users.length > 0 && (
          <div className={styles.warning} role="status">
            <strong>Personnes non classées :</strong>{" "}
            {snapshot.unclassified_users
              .map((person) => person.name)
              .join(", ")}
            . Leurs tâches sont incluses dans les deux agendas.
          </div>
        )}
        <div className={styles.summaryGrid}>
          <Summary
            title="Arrivées"
            value={snapshot.arrivals.reduce(
              (sum, item) => sum + item.party_size,
              0,
            )}
          />
          <Summary
            title="Départs"
            value={snapshot.departures.reduce(
              (sum, item) => sum + item.party_size,
              0,
            )}
          />
          <Summary
            title="Congés, absences et missions"
            value={snapshot.availability.length}
          />
          <Summary
            title="Services avec activité"
            value={snapshot.units.length}
          />
        </div>
        {snapshot.units.length === 0 ? (
          <EmptyState title="Aucune tâche sur cette période">
            Les rubriques de contexte seront tout de même présentes dans le PDF.
          </EmptyState>
        ) : (
          <div className={styles.unitGrid}>
            {snapshot.units.map((unit) => (
              <Card key={unit.id}>
                <h3>{unit.name}</h3>
                {unit.employees.map((employee) => (
                  <div className={styles.employee} key={employee.person.id}>
                    <strong>
                      {employee.person.name}
                      {employee.unclassified && " — non classé"}
                    </strong>
                    <span>{employee.completion_rate}% en moyenne</span>
                    <ul>
                      {employee.tasks.map((task) => (
                        <li key={task.id}>
                          {task.title} — <strong>{task.percentage}%</strong> (
                          {task.progress_delta >= 0 ? "+" : ""}
                          {task.progress_delta} pt)
                          {task.observation && (
                            <small>{task.observation}</small>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </Card>
            ))}
          </div>
        )}
      </section>
      <VersionList versions={versions.data?.versions ?? []} />
    </>
  );
}

function VisitorPanel({
  visits,
  reload,
}: {
  visits: VisitorVisit[];
  reload: () => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function addVisit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const names = String(form.get("names") ?? "")
      .split(/[\n,]/)
      .map((name) => name.trim())
      .filter(Boolean);
    try {
      await apiFetch("/api/v1/visits/", {
        method: "POST",
        body: JSON.stringify({
          party_size: Number(form.get("party_size")),
          visitor_names: names,
        }),
      });
      formElement.reset();
      await reload();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Enregistrement impossible",
      );
    } finally {
      setSaving(false);
    }
  }
  async function depart(visit: VisitorVisit) {
    await apiFetch(`/api/v1/visits/${visit.id}/departure/`, {
      method: "POST",
      body: JSON.stringify({ revision: visit.revision }),
    });
    await reload();
  }
  return (
    <Card>
      <h2>
        <DoorOpen size={21} aria-hidden="true" /> Visiteurs
      </h2>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <form className={styles.visitForm} onSubmit={addVisit}>
        <div className="form-field">
          <label htmlFor="party-size">Nombre arrivé</label>
          <input
            id="party-size"
            name="party_size"
            type="number"
            min="1"
            max="999"
            defaultValue="1"
            required
          />
        </div>
        <div className="form-field">
          <label htmlFor="visitor-names">
            Noms <span className="muted">(facultatifs)</span>
          </label>
          <textarea
            id="visitor-names"
            name="names"
            placeholder="Un nom par ligne"
          />
        </div>
        <Button disabled={saving}>
          <Plus size={18} aria-hidden="true" /> Notifier l’arrivée
        </Button>
      </form>
      <h3>Visites en cours</h3>
      <ul className={styles.visits}>
        {visits
          .filter((visit) => !visit.departed_at)
          .map((visit) => (
            <li key={visit.id}>
              <span>
                <strong>{visit.party_size}</strong> visiteur
                {visit.party_size > 1 ? "s" : ""}
                <small>
                  {visit.visitor_names.join(", ") ||
                    formatDateTime(visit.arrived_at)}
                </small>
              </span>
              <Button variant="secondary" onClick={() => void depart(visit)}>
                <LogOut size={17} aria-hidden="true" /> Marquer le départ
              </Button>
            </li>
          ))}
      </ul>
    </Card>
  );
}

function Summary({ title, value }: { title: string; value: number }) {
  return (
    <Card className={styles.summary}>
      <strong>{value}</strong>
      <span>{title}</span>
    </Card>
  );
}

function VersionList({ versions }: { versions: AgendaVersions["versions"] }) {
  return (
    <section className={styles.versions}>
      <div className={styles.sectionHeading}>
        <div>
          <p className="eyebrow">Documents figés</p>
          <h2>Versions archivées</h2>
        </div>
      </div>
      {versions.length === 0 ? (
        <EmptyState title="Aucune version générée">
          La première version apparaîtra ici après génération.
        </EmptyState>
      ) : (
        <div className="stack">
          {versions.map((version) => (
            <Card className={styles.version} key={version.id}>
              <div>
                <strong>
                  {version.agenda_direction_label} · du{" "}
                  {formatDate(version.period_start)} au{" "}
                  {formatDate(version.period_end)} — version {version.version}
                </strong>
                <small>
                  Générée par {version.generated_by.name} le{" "}
                  {formatDateTime(version.generated_at)}
                </small>
              </div>
              <a
                className={styles.download}
                href={version.pdf_url}
                target="_blank"
                rel="noreferrer"
              >
                <ArrowDownToLine size={18} aria-hidden="true" /> Ouvrir le PDF
              </a>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}

function AgendaArchives() {
  const versions = useApi<AgendaVersions>("/api/v1/agenda/versions/");
  if (versions.loading)
    return <Skeleton label="Chargement des agendas archivés" />;
  if (versions.error || !versions.data)
    return (
      <ErrorState
        error={versions.error ?? new Error("Archives indisponibles")}
        retry={versions.reload}
      />
    );
  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Rapport de direction</p>
          <h1>Agendas archivés</h1>
          <p>
            Consultez et réimprimez les versions figées par période et par
            direction.
          </p>
        </div>
      </header>
      <VersionList versions={versions.data.versions} />
    </>
  );
}
