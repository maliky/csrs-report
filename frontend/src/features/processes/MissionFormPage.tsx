import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "../../lib/router";
import {
  Button,
  ButtonLink,
  Card,
  ErrorState,
  FrenchDateInput,
  Skeleton,
} from "../../components/ui";
import type { MissionOptions, ProcessDetail } from "../../lib/api/types";
import { apiFetch } from "../../lib/api/client";
import { useApi } from "../../lib/useApi";
import styles from "./processes.module.css";

export function MissionFormPage({ mode }: { mode: "create" | "edit" }) {
  const { processId } = useParams();
  const options = useApi<MissionOptions>(
    "/api/v1/processes/mission-orders/options/",
  );
  const process = useApi<ProcessDetail>(
    `/api/v1/processes/${processId}/`,
    mode === "edit",
  );
  if (options.loading || (mode === "edit" && process.loading))
    return <Skeleton label="Chargement du formulaire de mission" />;
  if (options.error || !options.data)
    return (
      <ErrorState
        error={options.error ?? new Error("Options indisponibles")}
        retry={options.reload}
      />
    );
  if (mode === "edit" && (process.error || !process.data))
    return (
      <ErrorState
        error={process.error ?? new Error("Dossier indisponible")}
        retry={process.reload}
      />
    );
  if (mode === "edit" && !process.data?.capabilities.edit)
    return (
      <ErrorState error={new Error("Ce dossier ne peut plus être modifié.")} />
    );
  return (
    <MissionForm mode={mode} options={options.data} process={process.data} />
  );
}

function MissionForm({
  mode,
  options,
  process,
}: {
  mode: "create" | "edit";
  options: MissionOptions;
  process: ProcessDetail | null;
}) {
  const navigate = useNavigate();
  const [missionType, setMissionType] = useState(
    process?.mission_type ?? "domestic",
  );
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<Error | null>(null);
  const initialParticipants = new Set(
    process?.participants.map((person) => person.id) ?? [],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaveError(null);
    const form = new FormData(event.currentTarget);
    const payload = {
      mission_type: missionType,
      destination: form.get("destination"),
      purpose: form.get("purpose"),
      itinerary: form.get("itinerary"),
      transport_mode: form.get("transport_mode"),
      transport_company: form.get("transport_company"),
      departure_date: form.get("departure_date"),
      return_date: form.get("return_date"),
      funding_source: form.get("funding_source"),
      costs_covered: form.get("costs_covered"),
      vehicle_required: form.get("vehicle_required") === "on",
      vehicle_details: form.get("vehicle_details"),
      official_number: form.get("official_number"),
      participant_ids:
        missionType === "domestic"
          ? form.getAll("participant_ids").map(Number)
          : [],
    };
    try {
      const saved = await apiFetch<ProcessDetail>(
        mode === "create"
          ? "/api/v1/processes/mission-orders/"
          : `/api/v1/processes/${process?.id}/`,
        {
          method: mode === "create" ? "POST" : "PATCH",
          body: JSON.stringify(
            mode === "edit"
              ? { ...payload, revision: process?.revision }
              : payload,
          ),
        },
      );
      navigate(`/processus/${saved.id}`);
    } catch (caught) {
      setSaveError(
        caught instanceof Error ? caught : new Error("Dossier non enregistré"),
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
            {mode === "create" ? "Nouveau dossier" : process?.reference}
          </p>
          <h1>
            {mode === "create"
              ? "Préparer une demande de mission"
              : "Modifier le brouillon"}
          </h1>
          <p>
            Enregistrez d'abord le brouillon. Les pièces seront ajoutées depuis
            le dossier avant sa soumission.
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
          <fieldset className={`${styles.choiceGroup} wide`}>
            <legend>Type de mission</legend>
            <label>
              <input
                type="radio"
                name="mission_type"
                value="domestic"
                checked={missionType === "domestic"}
                onChange={() => setMissionType("domestic")}
              />{" "}
              Mission nationale
            </label>
            <label>
              <input
                type="radio"
                name="mission_type"
                value="international"
                checked={missionType === "international"}
                onChange={() => setMissionType("international")}
              />{" "}
              Mission internationale
            </label>
          </fieldset>
          <div className="form-field wide">
            <label htmlFor="destination">Destination</label>
            <input
              id="destination"
              name="destination"
              required
              maxLength={220}
              defaultValue={process?.destination ?? ""}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="purpose">Motif de la mission</label>
            <textarea
              id="purpose"
              name="purpose"
              required
              defaultValue={process?.purpose ?? ""}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="itinerary">Itinéraire</label>
            <textarea
              id="itinerary"
              name="itinerary"
              defaultValue={process?.mission.itinerary ?? ""}
            />
          </div>
          <div className="form-field">
            <label htmlFor="departure">Date de départ</label>
            <FrenchDateInput
              id="departure"
              name="departure_date"
              required
              defaultValue={process?.departure_date ?? ""}
            />
          </div>
          <div className="form-field">
            <label htmlFor="return">Date de retour</label>
            <FrenchDateInput
              id="return"
              name="return_date"
              required
              defaultValue={process?.return_date ?? ""}
            />
          </div>
          <div className="form-field">
            <label htmlFor="transport-mode">Mode de transport</label>
            <input
              id="transport-mode"
              name="transport_mode"
              defaultValue={process?.mission.transport_mode ?? ""}
            />
          </div>
          <div className="form-field">
            <label htmlFor="transport-company">Compagnie de transport</label>
            <input
              id="transport-company"
              name="transport_company"
              defaultValue={process?.mission.transport_company ?? ""}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="funding">Source de financement</label>
            <input
              id="funding"
              name="funding_source"
              defaultValue={process?.mission.funding_source ?? ""}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="costs">Frais pris en charge</label>
            <textarea
              id="costs"
              name="costs_covered"
              defaultValue={process?.mission.costs_covered ?? ""}
            />
          </div>
          {missionType === "domestic" && (
            <fieldset className={`${styles.participants} wide`}>
              <legend>Participants internes</legend>
              <p className="muted">
                Le demandeur est toujours ajouté automatiquement.
              </p>
              {options.participants.map((person) => (
                <label key={person.id}>
                  <input
                    type="checkbox"
                    name="participant_ids"
                    value={person.id}
                    defaultChecked={initialParticipants.has(person.id)}
                  />
                  <span>
                    {person.name}
                    <small>{person.position}</small>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          <label className={`${styles.checkbox} wide`}>
            <input
              type="checkbox"
              name="vehicle_required"
              defaultChecked={process?.mission.vehicle_required ?? false}
            />
            Un véhicule de service doit être préparé
          </label>
          <div className="form-field wide">
            <label htmlFor="vehicle-details">Précisions pour le véhicule</label>
            <textarea
              id="vehicle-details"
              name="vehicle_details"
              defaultValue={process?.mission.vehicle_details ?? ""}
            />
          </div>
          {mode === "edit" && (
            <div className="form-field wide">
              <label htmlFor="official-number">
                Numéro officiel <span className="muted">(facultatif)</span>
              </label>
              <input
                id="official-number"
                name="official_number"
                maxLength={80}
                defaultValue={process?.mission.official_number ?? ""}
              />
            </div>
          )}
          <div className="cluster wide">
            <Button disabled={saving}>
              {saving ? "Enregistrement…" : "Enregistrer le brouillon"}
            </Button>
            <ButtonLink
              to={process ? `/processus/${process.id}` : "/processus"}
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
