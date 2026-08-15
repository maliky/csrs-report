import { DayPicker, type DateRange } from "@daypicker/react";
import { fr } from "@daypicker/react/locale";
import "@daypicker/react/style.css";
import {
  ArrowDownToLine,
  CalendarDays,
  CalendarRange,
  DoorOpen,
  FileText,
  LogOut,
  Plus,
  Save,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
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
  if (!start || !end) return "Choisissez une date de début et une date de fin.";
  const startDate = new Date(`${start}T12:00:00`);
  const endDate = new Date(`${end}T12:00:00`);
  const dayCount =
    Math.round((endDate.getTime() - startDate.getTime()) / 86400000) + 1;
  if (dayCount < 1) return "La date de fin doit suivre la date de début.";
  if (dayCount > 31)
    return "La période ne peut pas dépasser 31 jours inclusifs.";
  return "";
}

function dateFromIso(value: string): Date | undefined {
  const parts = value.split("-").map(Number);
  if (parts.length !== 3 || parts.some((part) => !Number.isInteger(part)))
    return undefined;
  const [year, month, day] = parts;
  const date = new Date(year, month - 1, day, 12);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  )
    return undefined;
  return date;
}

function useNarrowScreen(): boolean {
  const query = "(max-width: 720px)";
  const [matches, setMatches] = useState(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia(query).matches,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return matches;
}

function AgendaRangePicker({
  appliedStart,
  appliedEnd,
  onApply,
}: {
  appliedStart: string;
  appliedEnd: string;
  onApply: (start: string, end: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draftStart, setDraftStart] = useState(appliedStart);
  const [draftEnd, setDraftEnd] = useState(appliedEnd);
  const containerRef = useRef<HTMLDivElement>(null);
  const narrowScreen = useNarrowScreen();
  const completeRange = Boolean(draftStart && draftEnd);
  const invalidPeriod = completeRange
    ? periodValidation(draftStart, draftEnd)
    : "";
  const selectedRange: DateRange = {
    from: dateFromIso(draftStart),
    to: dateFromIso(draftEnd),
  };

  function focusTrigger() {
    document.getElementById("agenda-period-trigger")?.focus();
  }

  function cancel(restoreFocus = true) {
    setDraftStart(appliedStart);
    setDraftEnd(appliedEnd);
    setOpen(false);
    if (restoreFocus) window.setTimeout(focusTrigger, 0);
  }

  function openPicker() {
    setDraftStart(appliedStart);
    setDraftEnd(appliedEnd);
    setOpen(true);
  }

  function apply(start: string, end: string) {
    if (periodValidation(start, end)) return;
    onApply(start, end);
    setDraftStart(start);
    setDraftEnd(end);
    setOpen(false);
    window.setTimeout(focusTrigger, 0);
  }

  useEffect(() => {
    if (!open) return;
    containerRef.current
      ?.querySelector<HTMLButtonElement>(".rdp-day_button")
      ?.focus();
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) cancel(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      cancel();
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open, appliedStart, appliedEnd]);

  return (
    <div className={styles.periodPicker} ref={containerRef}>
      <div className={styles.periodPickerHeading}>
        <strong>Période du rapport</strong>
        <Button
          type="button"
          variant="quiet"
          className={styles.periodShortcut}
          onClick={() => {
            const [start, end] = defaultAgendaPeriod();
            apply(start, end);
          }}
        >
          <CalendarRange size={18} aria-hidden="true" /> Semaine prochaine
        </Button>
      </div>
      <Button
        id="agenda-period-trigger"
        type="button"
        variant="secondary"
        className={styles.periodRangeTrigger}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="agenda-period-popover"
        onClick={() => (open ? cancel(false) : openPicker())}
      >
        <CalendarDays size={20} aria-hidden="true" /> Du{" "}
        {formatDate(appliedStart)} au {formatDate(appliedEnd)}
      </Button>
      <small>31 jours inclusifs maximum</small>
      {open && (
        <div
          id="agenda-period-popover"
          className={styles.rangePopover}
          role="dialog"
          aria-modal="false"
          aria-labelledby="agenda-period-dialog-title"
        >
          <h2 id="agenda-period-dialog-title">Choisir la période</h2>
          <p className={styles.rangeInstruction}>
            Cliquez sur la date de début, puis sur la date de fin.
          </p>
          <DayPicker
            className={styles.rangeCalendar}
            mode="range"
            locale={fr}
            weekStartsOn={1}
            numberOfMonths={narrowScreen ? 1 : 2}
            defaultMonth={selectedRange.from}
            selected={selectedRange}
            max={30}
            resetOnSelect
            onSelect={(range) => {
              setDraftStart(range?.from ? localIsoDate(range.from) : "");
              setDraftEnd(range?.to ? localIsoDate(range.to) : "");
            }}
          />
          <p
            className={invalidPeriod ? styles.periodError : styles.rangeHint}
            role={invalidPeriod ? "alert" : "status"}
          >
            {invalidPeriod ||
              (!draftStart
                ? "Choisissez la date de début."
                : !draftEnd
                  ? `Début sélectionné : ${formatDate(draftStart)}. Choisissez maintenant la date de fin.`
                  : `Période sélectionnée : du ${formatDate(draftStart)} au ${formatDate(draftEnd)}.`)}
          </p>
          <div className={styles.rangeActions}>
            <Button type="button" variant="quiet" onClick={() => cancel()}>
              Annuler
            </Button>
            <Button
              type="button"
              disabled={!completeRange || Boolean(invalidPeriod)}
              onClick={() => apply(draftStart, draftEnd)}
            >
              Appliquer
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

type AgendaPeriodData = {
  preview: AgendaPreview;
  visits: VisitList;
  versions: AgendaVersions;
};

function useAgendaPeriodData(
  periodStart: string,
  periodEnd: string,
  agendaDirection: AgendaDirection,
) {
  const [data, setData] = useState<AgendaPeriodData | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const requestId = useRef(0);

  const reload = useCallback(async () => {
    const currentRequest = ++requestId.current;
    const periodQuery = `period_start=${periodStart}&period_end=${periodEnd}`;
    setLoading(true);
    setError(null);
    try {
      const [preview, visits, versions] = await Promise.all([
        apiFetch<AgendaPreview>(
          `/api/v1/agenda/preview/?${periodQuery}&agenda_direction=${agendaDirection}`,
        ),
        apiFetch<VisitList>(`/api/v1/visits/?${periodQuery}`),
        apiFetch<AgendaVersions>(`/api/v1/agenda/versions/?${periodQuery}`),
      ]);
      if (requestId.current !== currentRequest) return;
      setData({ preview, visits, versions });
    } catch (caught) {
      if (requestId.current !== currentRequest) return;
      setError(caught instanceof Error ? caught : new Error("Erreur inconnue"));
    } finally {
      if (requestId.current === currentRequest) setLoading(false);
    }
  }, [periodStart, periodEnd, agendaDirection]);

  useEffect(() => {
    void reload();
    return () => {
      requestId.current += 1;
    };
  }, [reload]);

  return { data, error, loading, reload };
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
  const periodData = useAgendaPeriodData(
    periodStart,
    periodEnd,
    agendaDirection,
  );
  const preview = periodData.data?.preview;
  const visits = periodData.data?.visits;
  const versions = periodData.data?.versions;
  const [majorEvents, setMajorEvents] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const invalidPeriod = periodValidation(periodStart, periodEnd);

  useEffect(() => {
    setMajorEvents(preview?.draft.major_events ?? "");
  }, [
    preview?.draft.major_events,
    preview?.draft.period_start,
    preview?.draft.period_end,
    preview?.draft.revision,
  ]);

  async function saveDraft(): Promise<void> {
    if (invalidPeriod) throw new Error(invalidPeriod);
    await apiFetch("/api/v1/agenda/draft/", {
      method: "PUT",
      body: JSON.stringify({
        period_start: periodStart,
        period_end: periodEnd,
        major_events: majorEvents,
        revision: preview?.draft.revision ?? 0,
      }),
    });
  }

  async function saveOnly() {
    setSaving(true);
    setError(null);
    setMessage("");
    try {
      await saveDraft();
      await periodData.reload();
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
      await periodData.reload();
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

  if (periodData.loading && !periodData.data)
    return <Skeleton label="Préparation de l’agenda" />;
  if (periodData.error && !periodData.data)
    return <ErrorState error={periodData.error} retry={periodData.reload} />;
  if (!preview || !visits || !versions)
    return (
      <ErrorState
        error={new Error("Les données de la période sont indisponibles.")}
        retry={periodData.reload}
      />
    );

  const snapshot = preview.snapshot;
  const dataMatchesSelection =
    snapshot.period_start === periodStart &&
    snapshot.period_end === periodEnd &&
    snapshot.agenda_direction === agendaDirection;
  const periodActionsDisabled =
    saving ||
    periodData.loading ||
    Boolean(periodData.error) ||
    !dataMatchesSelection ||
    Boolean(invalidPeriod);
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
        <AgendaRangePicker
          appliedStart={periodStart}
          appliedEnd={periodEnd}
          onApply={(start, end) => {
            setError(null);
            setMessage("");
            setPeriodStart(start);
            setPeriodEnd(end);
          }}
        />
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
      {periodData.loading && (
        <div className={styles.updateStatus} role="status">
          Mise à jour de l’agenda… Les dernières données restent disponibles.
        </div>
      )}
      {periodData.error && (
        <div className={styles.periodLoadError} role="alert">
          <span>
            Mise à jour impossible : {periodData.error.message} Le dernier
            agenda chargé reste affiché.
          </span>
          <Button variant="secondary" onClick={() => void periodData.reload()}>
            Réessayer
          </Button>
        </div>
      )}

      <div className={styles.twoColumns}>
        <VisitorPanel visits={visits.visits} reload={periodData.reload} />
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
              disabled={!dataMatchesSelection || Boolean(periodData.error)}
            />
          </div>
          <div className={styles.actions}>
            <Button
              variant="secondary"
              onClick={() => void saveOnly()}
              disabled={periodActionsDisabled}
            >
              <Save size={18} aria-hidden="true" /> Enregistrer le brouillon
            </Button>
            <div className={styles.generationControl}>
              <div className={styles.generationField}>
                <label htmlFor="agenda-direction">Direction de l’agenda</label>
                <select
                  id="agenda-direction"
                  value={agendaDirection}
                  disabled={saving || periodData.loading}
                  onChange={(event) =>
                    setAgendaDirection(event.target.value as AgendaDirection)
                  }
                >
                  <option value="programs">Direction des programmes</option>
                  <option value="administration">
                    Direction administrative
                  </option>
                </select>
              </div>
              <Button
                onClick={() => void generate(agendaDirection)}
                disabled={periodActionsDisabled}
              >
                <FileText size={18} aria-hidden="true" />{" "}
                {saving ? "Génération…" : "Générer le PDF"}
              </Button>
            </div>
          </div>
        </Card>
      </div>

      <section
        className={styles.preview}
        aria-labelledby="preview-title"
        aria-busy={periodData.loading}
      >
        <div className={styles.sectionHeading}>
          <div>
            <p className="eyebrow">Aperçu des données</p>
            <h2 id="preview-title">
              {snapshot.agenda_direction_label} · du{" "}
              {formatDate(snapshot.period_start)} au{" "}
              {formatDate(snapshot.period_end)}
            </h2>
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
      <VersionList versions={versions.versions} />
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
