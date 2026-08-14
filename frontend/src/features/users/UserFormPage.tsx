import {
  Check,
  Copy,
  KeyRound,
  Mail,
  Power,
  PowerOff,
  Save,
  UsersRound,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import {
  Button,
  ButtonLink,
  Card,
  ErrorState,
  FrenchDateInput,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import { ApiError, apiFetch } from "../../lib/api/client";
import type {
  CollaboratorManagement,
  ManagedUserDetail,
  Person,
  TemporaryPasswordResult,
  UserManagementOptions,
} from "../../lib/api/types";
import { useNavigate, useParams } from "../../lib/router";
import { useApi } from "../../lib/useApi";
import { TransferSelector, type TransferItem } from "./TransferSelector";
import styles from "./users.module.css";

type UserFormState = {
  email: string;
  login_alias: string;
  first_name: string;
  last_name: string;
  position: string;
  phone: string;
  agenda_direction: string;
  include_in_direction_agendas: boolean;
  unit_ids: number[];
  primary_unit_id: number | null;
  primary_supervisor_id: number | null;
  organization_effective_date: string;
};

export function UserFormPage({ mode }: { mode: "create" | "edit" }) {
  const { userId } = useParams();
  const options = useApi<UserManagementOptions>("/api/v1/users/options/");
  const user = useApi<ManagedUserDetail>(
    `/api/v1/users/${userId}/`,
    mode === "edit",
  );
  const collaborators = useApi<CollaboratorManagement>(
    `/api/v1/users/${userId}/collaborators/`,
    mode === "edit",
  );

  if (
    options.loading ||
    (mode === "edit" && (user.loading || collaborators.loading))
  )
    return <Skeleton label="Chargement de la fiche utilisateur" />;
  const loadError = options.error ?? user.error ?? collaborators.error;
  if (loadError || !options.data || (mode === "edit" && !user.data))
    return (
      <ErrorState
        error={loadError ?? new Error("Fiche utilisateur indisponible")}
        retry={() => {
          void options.reload();
          void user.reload();
          void collaborators.reload();
        }}
      />
    );

  return (
    <ManagedUserForm
      key={user.data?.state_token ?? "new-user"}
      mode={mode}
      options={options.data}
      user={user.data}
      collaborators={collaborators.data}
      onUserSaved={(saved) => {
        user.setData(saved);
        void collaborators.reload();
      }}
      onCollaboratorsSaved={collaborators.setData}
    />
  );
}

function ManagedUserForm({
  mode,
  options,
  user,
  collaborators,
  onUserSaved,
  onCollaboratorsSaved,
}: {
  mode: "create" | "edit";
  options: UserManagementOptions;
  user: ManagedUserDetail | null;
  collaborators: CollaboratorManagement | null;
  onUserSaved: (saved: ManagedUserDetail) => void;
  onCollaboratorsSaved: (saved: CollaboratorManagement) => void;
}) {
  const navigate = useNavigate();
  const [form, setForm] = useState<UserFormState>(() =>
    initialForm(options, user),
  );
  const [saving, setSaving] = useState(false);
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [copied, setCopied] = useState(false);
  const selectedUnits = options.units.filter((unit) =>
    form.unit_ids.includes(unit.id),
  );
  const availableUnits = options.units.filter(
    (unit) => !form.unit_ids.includes(unit.id),
  );
  const editable = user?.capabilities.edit ?? true;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const payload = {
        ...form,
        login_alias: form.login_alias || null,
        state_token: user?.state_token,
      };
      const saved = await apiFetch<ManagedUserDetail>(
        mode === "create" ? "/api/v1/users/" : `/api/v1/users/${user?.id}/`,
        {
          method: mode === "create" ? "POST" : "PATCH",
          body: JSON.stringify(payload),
        },
      );
      if (mode === "create") {
        navigate(`/administration/utilisateurs/${saved.id}`);
        return;
      }
      onUserSaved(saved);
      setSuccess("Compte enregistré.");
    } catch (caught) {
      setError(messageFrom(caught, "Le compte n’a pas pu être enregistré."));
    } finally {
      setSaving(false);
    }
  }

  async function accountAction(
    kind:
      "deactivate" | "reactivate" | "activation-link" | "temporary-password",
  ) {
    if (!user) return;
    if (
      kind === "deactivate" &&
      !window.confirm(
        "Désactiver ce compte ? La personne ne pourra plus se connecter, mais son historique sera conservé.",
      )
    )
      return;
    if (
      kind === "temporary-password" &&
      !window.confirm(
        "Générer un nouveau mot de passe temporaire ? L’ancien mot de passe cessera immédiatement de fonctionner.",
      )
    )
      return;
    setAction(kind);
    setError("");
    setSuccess("");
    try {
      if (kind === "temporary-password") {
        const result = await apiFetch<TemporaryPasswordResult>(
          `/api/v1/users/${user.id}/temporary-password/`,
          {
            method: "POST",
            body: JSON.stringify({ state_token: user.state_token }),
          },
        );
        setTemporaryPassword(result.temporary_password);
        setCopied(false);
        const refreshed = await apiFetch<ManagedUserDetail>(
          `/api/v1/users/${user.id}/`,
        );
        onUserSaved(refreshed);
        return;
      }
      const endpoint =
        kind === "activation-link"
          ? "activation-link"
          : kind === "deactivate"
            ? "deactivate"
            : "reactivate";
      const response = await apiFetch<ManagedUserDetail | { sent: number }>(
        `/api/v1/users/${user.id}/${endpoint}/`,
        {
          method: "POST",
          body: JSON.stringify({ state_token: user.state_token }),
        },
      );
      if (kind === "activation-link") {
        setSuccess("Lien d’activation envoyé.");
      } else {
        onUserSaved(response as ManagedUserDetail);
        setSuccess(
          kind === "deactivate" ? "Compte désactivé." : "Compte réactivé.",
        );
      }
    } catch (caught) {
      setError(messageFrom(caught, "L’action n’a pas pu être exécutée."));
    } finally {
      setAction("");
    }
  }

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Administration IT</p>
          <h1>{mode === "create" ? "Ajouter une personne" : user?.name}</h1>
          <p>
            Les changements d’unité et de responsable sont datés; les anciennes
            relations restent dans l’historique.
          </p>
        </div>
        <ButtonLink to="/administration/utilisateurs" variant="quiet">
          Retour à la liste
        </ButtonLink>
      </header>

      {success && (
        <p className="success-banner" role="status">
          {success}
        </p>
      )}
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}

      <form className="stack" onSubmit={(event) => void submit(event)}>
        <Card>
          <fieldset className={styles.fieldset} disabled={!editable || saving}>
            <legend>Identité</legend>
            <div className="form-grid">
              <div className="form-field">
                <label htmlFor="user-first-name">Prénom</label>
                <input
                  id="user-first-name"
                  value={form.first_name}
                  onChange={(event) =>
                    setForm({ ...form, first_name: event.target.value })
                  }
                  maxLength={150}
                />
              </div>
              <div className="form-field">
                <label htmlFor="user-last-name">Nom</label>
                <input
                  id="user-last-name"
                  value={form.last_name}
                  onChange={(event) =>
                    setForm({ ...form, last_name: event.target.value })
                  }
                  maxLength={150}
                />
              </div>
              <div className="form-field">
                <label htmlFor="user-email">Email</label>
                <input
                  id="user-email"
                  type="email"
                  required
                  value={form.email}
                  onChange={(event) =>
                    setForm({ ...form, email: event.target.value })
                  }
                  autoComplete="email"
                />
              </div>
              <div className="form-field">
                <label htmlFor="user-alias">Identifiant court</label>
                <input
                  id="user-alias"
                  value={form.login_alias}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      login_alias: event.target.value.toLowerCase(),
                    })
                  }
                  pattern="[a-z][a-z0-9_-]*"
                  maxLength={32}
                  autoComplete="username"
                />
              </div>
              <div className="form-field">
                <label htmlFor="user-position">Fonction</label>
                <input
                  id="user-position"
                  value={form.position}
                  onChange={(event) =>
                    setForm({ ...form, position: event.target.value })
                  }
                  maxLength={160}
                />
              </div>
              <div className="form-field">
                <label htmlFor="user-phone">Téléphone</label>
                <input
                  id="user-phone"
                  type="tel"
                  value={form.phone}
                  onChange={(event) =>
                    setForm({ ...form, phone: event.target.value })
                  }
                  maxLength={32}
                  autoComplete="tel"
                />
              </div>
            </div>
          </fieldset>
        </Card>

        <Card>
          <fieldset className={styles.fieldset} disabled={!editable || saving}>
            <legend>Agendas de direction</legend>
            <div className="form-grid">
              <div className="form-field">
                <label htmlFor="user-agenda-direction">
                  Direction de l’agenda
                </label>
                <select
                  id="user-agenda-direction"
                  value={form.agenda_direction}
                  onChange={(event) =>
                    setForm({ ...form, agenda_direction: event.target.value })
                  }
                >
                  <option value="">Non classée</option>
                  {options.agenda_directions.map((direction) => (
                    <option key={direction.value} value={direction.value}>
                      {direction.label}
                    </option>
                  ))}
                </select>
              </div>
              <label className={styles.checkboxField}>
                <input
                  type="checkbox"
                  checked={form.include_in_direction_agendas}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      include_in_direction_agendas: event.target.checked,
                    })
                  }
                />
                Inclure dans les agendas de direction
              </label>
            </div>
          </fieldset>
        </Card>

        <Card>
          <fieldset className={styles.fieldset} disabled={!editable || saving}>
            <legend>Organisation actuelle</legend>
            <TransferSelector
              legend="Unités actuelles"
              available={availableUnits.map(unitItem)}
              selected={selectedUnits.map(unitItem)}
              onAdd={(ids) =>
                setForm({ ...form, unit_ids: [...form.unit_ids, ...ids] })
              }
              onRemove={(ids) => {
                const remaining = form.unit_ids.filter(
                  (id) => !ids.includes(id),
                );
                setForm({
                  ...form,
                  unit_ids: remaining,
                  primary_unit_id: ids.includes(form.primary_unit_id ?? -1)
                    ? null
                    : form.primary_unit_id,
                  primary_supervisor_id: ids.includes(
                    form.primary_unit_id ?? -1,
                  )
                    ? null
                    : form.primary_supervisor_id,
                });
              }}
              disabled={!editable || saving}
            />
            <div className={`${styles.organizationFields} form-grid`}>
              <div className="form-field">
                <label htmlFor="user-primary-unit">Unité principale</label>
                <select
                  id="user-primary-unit"
                  value={form.primary_unit_id ?? ""}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      primary_unit_id: event.target.value
                        ? Number(event.target.value)
                        : null,
                      primary_supervisor_id: event.target.value
                        ? form.primary_supervisor_id
                        : null,
                    })
                  }
                >
                  <option value="">Aucune</option>
                  {selectedUnits.map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.code} — {unit.short_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="user-primary-supervisor">
                  Responsable principal
                </label>
                <select
                  id="user-primary-supervisor"
                  value={form.primary_supervisor_id ?? ""}
                  disabled={!form.primary_unit_id || !editable || saving}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      primary_supervisor_id: event.target.value
                        ? Number(event.target.value)
                        : null,
                    })
                  }
                >
                  <option value="">Aucun — racine de l’organigramme</option>
                  {options.users
                    .filter((candidate) => candidate.id !== user?.id)
                    .map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {candidate.name} —{" "}
                        {candidate.position || "sans fonction"}
                      </option>
                    ))}
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="user-effective-date">Date d’effet</label>
                <FrenchDateInput
                  id="user-effective-date"
                  required
                  value={form.organization_effective_date}
                  onValueChange={(value) =>
                    setForm({ ...form, organization_effective_date: value })
                  }
                />
              </div>
            </div>
          </fieldset>
        </Card>

        <div className="cluster">
          <Button disabled={saving || !editable}>
            <Save size={18} aria-hidden="true" />
            {saving ? "Enregistrement…" : "Enregistrer la fiche"}
          </Button>
          <ButtonLink to="/administration/utilisateurs" variant="quiet">
            Annuler
          </ButtonLink>
        </div>
      </form>

      {mode === "edit" && user && collaborators && (
        <TeamEditor
          key={collaborators.state_token}
          data={collaborators}
          today={options.today}
          disabled={!editable}
          onSaved={onCollaboratorsSaved}
        />
      )}

      {mode === "edit" && user && (
        <Card className={styles.accessCard}>
          <div>
            <h2>Accès au compte</h2>
            <p>
              Les droits techniques détaillés et les responsables secondaires
              restent dans l’administration avancée.
            </p>
            <div className="cluster">
              <StatusBadge status={user.is_active ? "completed" : "rejected"}>
                {user.is_active ? "Compte actif" : "Compte désactivé"}
              </StatusBadge>
              {user.password_change_required && (
                <StatusBadge status="submitted">
                  Mot de passe à changer
                </StatusBadge>
              )}
              {user.is_superuser && (
                <StatusBadge status="submitted">Superutilisateur</StatusBadge>
              )}
            </div>
          </div>
          <div className="cluster">
            {user.capabilities.send_activation && (
              <Button
                type="button"
                variant="secondary"
                disabled={Boolean(action)}
                onClick={() => void accountAction("activation-link")}
              >
                <Mail size={18} aria-hidden="true" /> Envoyer l’activation
              </Button>
            )}
            {user.capabilities.reset_password && (
              <Button
                type="button"
                variant="secondary"
                disabled={Boolean(action)}
                onClick={() => void accountAction("temporary-password")}
              >
                <KeyRound size={18} aria-hidden="true" /> Réinitialiser le mot
                de passe
              </Button>
            )}
            {user.capabilities.deactivate && (
              <Button
                type="button"
                variant="danger"
                disabled={Boolean(action)}
                onClick={() => void accountAction("deactivate")}
              >
                <PowerOff size={18} aria-hidden="true" /> Désactiver
              </Button>
            )}
            {user.capabilities.reactivate && (
              <Button
                type="button"
                disabled={Boolean(action)}
                onClick={() => void accountAction("reactivate")}
              >
                <Power size={18} aria-hidden="true" /> Réactiver
              </Button>
            )}
            <a
              className={styles.advancedLink}
              href={`/admin/accounts/user/${user.id}/change/`}
            >
              Administration avancée
            </a>
          </div>
        </Card>
      )}

      {temporaryPassword && (
        <div className={styles.modalBackdrop}>
          <section
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="temporary-password-title"
          >
            <h2 id="temporary-password-title">Mot de passe temporaire</h2>
            <p>
              Copiez-le maintenant et transmettez-le par un canal sûr. Il ne
              sera plus affiché après la fermeture.
            </p>
            <code className={styles.temporaryPassword}>
              {temporaryPassword}
            </code>
            <div className="cluster">
              <Button
                type="button"
                onClick={async () => {
                  await navigator.clipboard.writeText(temporaryPassword);
                  setCopied(true);
                }}
              >
                {copied ? (
                  <Check size={18} aria-hidden="true" />
                ) : (
                  <Copy size={18} aria-hidden="true" />
                )}
                {copied ? "Copié" : "Copier"}
              </Button>
              <Button
                type="button"
                variant="quiet"
                onClick={() => {
                  setTemporaryPassword("");
                  setCopied(false);
                }}
              >
                Fermer
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function TeamEditor({
  data,
  today,
  disabled,
  onSaved,
}: {
  data: CollaboratorManagement;
  today: string;
  disabled: boolean;
  onSaved: (saved: CollaboratorManagement) => void;
}) {
  const people = useMemo(
    () =>
      new Map(
        [...data.current, ...data.available].map((person) => [
          person.id,
          person,
        ]),
      ),
    [data],
  );
  const initialIds = useMemo(
    () => data.current.map((person) => person.id),
    [data],
  );
  const [selectedIds, setSelectedIds] = useState(initialIds);
  const [replacements, setReplacements] = useState<Record<number, number>>({});
  const [pendingRemoval, setPendingRemoval] = useState<number[]>([]);
  const [effectiveDate, setEffectiveDate] = useState(today);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const selected = selectedIds.map((id) => people.get(id)).filter(isPerson);
  const available = Array.from(people.values()).filter(
    (person) => !selectedIds.includes(person.id),
  );
  const removedIds = initialIds.filter((id) => !selectedIds.includes(id));
  const dirty =
    selectedIds.length !== initialIds.length ||
    selectedIds.some((id) => !initialIds.includes(id));

  function confirmRemoval() {
    if (pendingRemoval.some((id) => !replacements[id])) return;
    setSelectedIds((current) =>
      current.filter((id) => !pendingRemoval.includes(id)),
    );
    setPendingRemoval([]);
  }

  async function saveTeam() {
    setSaving(true);
    setError("");
    try {
      const saved = await apiFetch<CollaboratorManagement>(
        `/api/v1/users/${data.supervisor.id}/collaborators/`,
        {
          method: "PUT",
          body: JSON.stringify({
            collaborator_ids: selectedIds,
            replacements: removedIds.map((employeeId) => ({
              employee_id: employeeId,
              supervisor_id: replacements[employeeId],
            })),
            effective_date: effectiveDate,
            state_token: data.state_token,
          }),
        },
      );
      onSaved(saved);
    } catch (caught) {
      setError(messageFrom(caught, "L’équipe n’a pas pu être enregistrée."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className={styles.teamCard}>
      <div className={styles.sectionHeading}>
        <div>
          <h2>
            <UsersRound size={22} aria-hidden="true" /> Collaborateurs directs
          </h2>
          <p>
            Cette liste gère uniquement le responsable principal. Un responsable
            secondaire peut suivre et commenter, sans affecter, modifier,
            valider ou clore les tâches à la place du responsable principal.
          </p>
        </div>
        <div className="form-field">
          <label htmlFor="team-effective-date">Date d’effet</label>
          <FrenchDateInput
            id="team-effective-date"
            required
            value={effectiveDate}
            disabled={disabled || saving}
            onValueChange={setEffectiveDate}
          />
        </div>
      </div>
      <TransferSelector
        legend="Équipe directe"
        available={available.map(personItem)}
        selected={selected.map(personItem)}
        disabled={disabled || saving}
        onAdd={(ids) => {
          setSelectedIds([...selectedIds, ...ids]);
          setReplacements((current) => {
            const next = { ...current };
            ids.forEach((id) => delete next[id]);
            return next;
          });
        }}
        onRemove={(ids) => {
          const existingIds = ids.filter((id) => initialIds.includes(id));
          const unsavedIds = ids.filter((id) => !initialIds.includes(id));
          if (unsavedIds.length)
            setSelectedIds((current) =>
              current.filter((id) => !unsavedIds.includes(id)),
            );
          setPendingRemoval(existingIds);
          setReplacements((current) => {
            const next = { ...current };
            existingIds.forEach((id) => {
              if (!next[id]) next[id] = 0;
            });
            return next;
          });
        }}
      />
      <p className="muted">
        Ajouter une personne déjà rattachée ailleurs change son responsable
        principal et transfère ses tâches actives.
      </p>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      <Button
        type="button"
        disabled={!dirty || disabled || saving || !effectiveDate}
        onClick={() => void saveTeam()}
      >
        <Save size={18} aria-hidden="true" />
        {saving ? "Enregistrement…" : "Enregistrer l’équipe"}
      </Button>

      {pendingRemoval.length > 0 && (
        <div className={styles.modalBackdrop}>
          <section
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="replacement-title"
          >
            <h2 id="replacement-title">Choisir le nouveau responsable</h2>
            <p>
              Chaque collaborateur retiré doit rester rattaché à un responsable
              principal.
            </p>
            <div className="stack">
              {pendingRemoval.map((employeeId) => {
                const employee = people.get(employeeId);
                const choices = (
                  data.replacement_options[String(employeeId)] ?? []
                ).filter((candidate) => candidate.id !== data.supervisor.id);
                return (
                  <div className="form-field" key={employeeId}>
                    <label htmlFor={`replacement-${employeeId}`}>
                      Nouveau responsable de {employee?.name}
                    </label>
                    <select
                      id={`replacement-${employeeId}`}
                      required
                      value={replacements[employeeId] || ""}
                      onChange={(event) =>
                        setReplacements({
                          ...replacements,
                          [employeeId]: Number(event.target.value),
                        })
                      }
                    >
                      <option value="">Choisir</option>
                      {choices.map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          {candidate.name} —{" "}
                          {candidate.position || "sans fonction"}
                        </option>
                      ))}
                    </select>
                    {!choices.length && (
                      <small className="field-error">
                        Aucun responsable compatible. Corrigez d’abord l’unité
                        ou l’organigramme.
                      </small>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="cluster">
              <Button
                type="button"
                disabled={pendingRemoval.some((id) => !replacements[id])}
                onClick={confirmRemoval}
              >
                Confirmer la réaffectation
              </Button>
              <Button
                type="button"
                variant="quiet"
                onClick={() => setPendingRemoval([])}
              >
                Annuler
              </Button>
            </div>
          </section>
        </div>
      )}
    </Card>
  );
}

function initialForm(
  options: UserManagementOptions,
  user: ManagedUserDetail | null,
): UserFormState {
  return {
    email: user?.email ?? "",
    login_alias: user?.login_alias ?? "",
    first_name: user?.first_name ?? "",
    last_name: user?.last_name ?? "",
    position: user?.position ?? "",
    phone: user?.phone ?? "",
    agenda_direction: user?.agenda_direction ?? "",
    include_in_direction_agendas: user?.include_in_direction_agendas ?? true,
    unit_ids: user?.unit_ids ?? [],
    primary_unit_id: user?.primary_unit_id ?? null,
    primary_supervisor_id: user?.primary_supervisor?.id ?? null,
    organization_effective_date: options.today,
  };
}

function unitItem(unit: UserManagementOptions["units"][number]): TransferItem {
  return {
    id: unit.id,
    label: `${unit.code} — ${unit.short_name}`,
    description: unit.long_name,
  };
}

function personItem(person: Person): TransferItem {
  return { id: person.id, label: person.name, description: person.position };
}

function isPerson(person: Person | undefined): person is Person {
  return person !== undefined;
}

function messageFrom(caught: unknown, fallback: string) {
  return caught instanceof ApiError ? caught.message : fallback;
}
