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
  Skeleton,
} from "../../components/ui";
import { apiFetch, ApiError } from "../../lib/api/client";
import type {
  AgendaPreview,
  AgendaVersions,
  Session,
  VisitList,
  VisitorVisit,
} from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import styles from "./agenda.module.css";

function isoWeekStart(value = new Date()): string {
  const day = (value.getDay() + 6) % 7;
  const monday = new Date(
    value.getFullYear(),
    value.getMonth(),
    value.getDate() - day,
  );
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}`;
}

function formatMoment(value: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
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
  const [week, setWeek] = useState(isoWeekStart);
  const preview = useApi<AgendaPreview>(`/api/v1/agenda/preview/?week=${week}`);
  const visits = useApi<VisitList>(`/api/v1/visits/?week=${week}`);
  const versions = useApi<AgendaVersions>(
    `/api/v1/agenda/versions/?week=${week}`,
  );
  const [majorEvents, setMajorEvents] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    setMajorEvents(preview.data?.draft.major_events ?? "");
  }, [preview.data?.draft.major_events, week]);

  async function saveDraft(): Promise<void> {
    await apiFetch("/api/v1/agenda/draft/", {
      method: "PUT",
      body: JSON.stringify({
        week_start: week,
        major_events: majorEvents,
        revision: preview.data?.draft.revision ?? 0,
      }),
    });
    await preview.reload();
  }

  async function generate() {
    setSaving(true);
    setError(null);
    setMessage("");
    try {
      await saveDraft();
      await apiFetch("/api/v1/agenda/versions/", {
        method: "POST",
        body: JSON.stringify({ week_start: week }),
      });
      await versions.reload();
      setMessage("La nouvelle version PDF est archivée et prête à imprimer.");
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
          <h1>Agenda hebdomadaire</h1>
          <p>
            Enregistrez les visiteurs, contrôlez la synthèse puis figez une
            version PDF imprimable.
          </p>
        </div>
        <label className={styles.weekPicker}>
          Semaine
          <input
            type="date"
            value={week}
            onChange={(event) =>
              setWeek(isoWeekStart(new Date(`${event.target.value}T12:00:00`)))
            }
          />
        </label>
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
            <Button variant="secondary" onClick={() => void saveDraft()}>
              <Save size={18} aria-hidden="true" /> Enregistrer le brouillon
            </Button>
            <Button onClick={() => void generate()} disabled={saving}>
              <FileText size={18} aria-hidden="true" />{" "}
              {saving ? "Génération…" : "Générer le PDF"}
            </Button>
          </div>
        </Card>
      </div>

      <section className={styles.preview} aria-labelledby="preview-title">
        <div className={styles.sectionHeading}>
          <div>
            <p className="eyebrow">Aperçu des données</p>
            <h2 id="preview-title">
              Semaine du {snapshot.week_start} au {snapshot.week_end}
            </h2>
          </div>
        </div>
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
          <EmptyState title="Aucune activité pour cette semaine">
            Les rubriques de contexte seront tout de même présentes dans le PDF.
          </EmptyState>
        ) : (
          <div className={styles.unitGrid}>
            {snapshot.units.map((unit) => (
              <Card key={unit.id}>
                <h3>{unit.name}</h3>
                {unit.employees.map((employee) => (
                  <div className={styles.employee} key={employee.person.id}>
                    <strong>{employee.person.name}</strong>
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
                    formatMoment(visit.arrived_at)}
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
                  Semaine du {version.week_start} — version {version.version}
                </strong>
                <small>
                  Générée par {version.generated_by.name} le{" "}
                  {formatMoment(version.generated_at)}
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
          <p>Consultez et réimprimez les versions hebdomadaires figées.</p>
        </div>
      </header>
      <VersionList versions={versions.data.versions} />
    </>
  );
}
