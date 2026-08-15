import {
  Filter,
  PowerOff,
  RotateCcw,
  Trash2,
  UserRoundPlus,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  Button,
  ButtonLink,
  EmptyState,
  ErrorState,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import type {
  ManagedUserSummary,
  UserBulkActionResult,
  UserManagementOptions,
  UserManagementPage as UserManagementResponse,
} from "../../lib/api/types";
import { apiFetch } from "../../lib/api/client";
import { Link, useSearchParams } from "../../lib/router";
import { useApi } from "../../lib/useApi";
import styles from "./users.module.css";

type FilterDraft = { q: string; state: string; unit: string };
type BatchAction = "deactivate" | "delete";

function draftFrom(params: URLSearchParams): FilterDraft {
  return {
    q: params.get("q") ?? "",
    state: params.get("state") ?? "",
    unit: params.get("unit_id") ?? "",
  };
}

export function UserManagementPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState(() => draftFrom(searchParams));
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [batchAction, setBatchAction] = useState<BatchAction | null>(null);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [mutating, setMutating] = useState(false);
  const [mutationError, setMutationError] = useState("");
  const [success, setSuccess] = useState("");
  const selectAllRef = useRef<HTMLInputElement>(null);
  const options = useApi<UserManagementOptions>("/api/v1/users/options/");
  const query = searchParams.toString();
  const users = useApi<UserManagementResponse>(
    `/api/v1/users/${query ? `?${query}` : ""}`,
  );

  useEffect(() => {
    setDraft(draftFrom(searchParams));
    setSelected(new Set());
  }, [searchParams]);

  const selectedItems = useMemo(
    () => users.data?.items.filter((item) => selected.has(item.id)) ?? [],
    [selected, users.data],
  );
  const selectableItems = useMemo(
    () =>
      users.data?.items.filter(
        (item) =>
          item.batch_capabilities.deactivate || item.batch_capabilities.delete,
      ) ?? [],
    [users.data],
  );
  const allPageSelected = Boolean(
    selectableItems.length &&
    selectableItems.every((item) => selected.has(item.id)),
  );
  const partlySelected = Boolean(selectedItems.length && !allPageSelected);
  const canDeactivateSelection = Boolean(
    selectedItems.length &&
    selectedItems.every((item) => item.batch_capabilities.deactivate),
  );
  const canDeleteSelection = Boolean(
    selectedItems.length &&
    selectedItems.every((item) => item.batch_capabilities.delete),
  );

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = partlySelected;
    }
  }, [partlySelected]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = new URLSearchParams();
    if (draft.q.trim()) next.set("q", draft.q.trim());
    if (draft.state) next.set("state", draft.state);
    if (draft.unit) next.set("unit_id", draft.unit);
    setSearchParams(next);
  }

  function resetFilters() {
    setDraft({ q: "", state: "", unit: "" });
    setSearchParams(new URLSearchParams());
  }

  function changePage(page: number) {
    const next = new URLSearchParams(searchParams);
    if (page > 1) next.set("page", String(page));
    else next.delete("page");
    setSearchParams(next);
  }

  function isSelectable(user: ManagedUserSummary) {
    return user.batch_capabilities.deactivate || user.batch_capabilities.delete;
  }

  function toggle(user: ManagedUserSummary) {
    if (!isSelectable(user)) return;
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(user.id)) next.delete(user.id);
      else next.add(user.id);
      return next;
    });
  }

  function togglePage() {
    setSelected(
      allPageSelected
        ? new Set()
        : new Set(selectableItems.map((item) => item.id)),
    );
  }

  function openBatchAction(action: BatchAction) {
    setBatchAction(action);
    setReason("");
    setConfirmation("");
    setMutationError("");
  }

  async function applyBatchAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!batchAction || !selectedItems.length) return;
    setMutating(true);
    setMutationError("");
    try {
      const result = await apiFetch<UserBulkActionResult>(
        "/api/v1/users/bulk-action/",
        {
          method: "POST",
          body: JSON.stringify({
            action: batchAction,
            users: selectedItems.map((item) => ({
              id: item.id,
              state_token: item.state_token,
            })),
            ...(batchAction === "delete"
              ? { reason: reason.trim(), confirmation }
              : {}),
          }),
        },
      );
      setSuccess(
        result.action === "delete"
          ? `${result.affected} compte(s) supprimé(s).`
          : `${result.affected} compte(s) désactivé(s).`,
      );
      setBatchAction(null);
      setSelected(new Set());
      setReason("");
      setConfirmation("");
      await users.reload();
    } catch (caught) {
      setMutationError(
        caught instanceof Error ? caught.message : "Action groupée impossible.",
      );
    } finally {
      setMutating(false);
    }
  }

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Administration IT</p>
          <h1>Utilisateurs</h1>
          <p>
            Gérez les comptes et leur rattachement actuel sans effacer
            l’historique.
          </p>
        </div>
        <ButtonLink to="/administration/utilisateurs/nouveau">
          <UserRoundPlus size={18} aria-hidden="true" /> Ajouter une personne
        </ButtonLink>
      </header>

      {success && (
        <p className="success-banner" role="status">
          {success}
        </p>
      )}

      <form className={styles.filters} onSubmit={applyFilters}>
        <div className="form-field">
          <label htmlFor="user-management-q">Recherche</label>
          <input
            id="user-management-q"
            value={draft.q}
            onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            placeholder="Nom, email, identifiant ou fonction"
          />
        </div>
        <div className="form-field">
          <label htmlFor="user-management-state">État</label>
          <select
            id="user-management-state"
            value={draft.state}
            onChange={(event) =>
              setDraft({ ...draft, state: event.target.value })
            }
          >
            <option value="">Tous les comptes</option>
            <option value="active">Actifs</option>
            <option value="inactive">Désactivés</option>
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="user-management-unit">Unité</label>
          <select
            id="user-management-unit"
            value={draft.unit}
            onChange={(event) =>
              setDraft({ ...draft, unit: event.target.value })
            }
          >
            <option value="">Toutes les unités</option>
            {options.data?.units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.code} — {unit.short_name}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.filterActions}>
          <Button>
            <Filter size={18} aria-hidden="true" /> Appliquer
          </Button>
          <Button type="button" variant="quiet" onClick={resetFilters}>
            <RotateCcw size={18} aria-hidden="true" /> Réinitialiser
          </Button>
        </div>
      </form>

      {(users.loading || options.loading) && (
        <Skeleton label="Chargement des utilisateurs" />
      )}
      {(users.error || options.error) && (
        <ErrorState
          error={
            users.error ?? options.error ?? new Error("Liste indisponible")
          }
          retry={() => {
            void users.reload();
            void options.reload();
          }}
        />
      )}
      {users.data && !users.data.items.length && (
        <EmptyState title="Aucun utilisateur">
          Aucun compte ne correspond aux filtres.
        </EmptyState>
      )}
      {users.data && users.data.items.length > 0 && (
        <>
          <div className={styles.batchToolbar} aria-label="Actions groupées">
            <p className={styles.resultCount}>
              {users.data.total} compte(s) · {selectedItems.length}{" "}
              sélectionné(s)
            </p>
            <div className={styles.batchActions}>
              <Button
                type="button"
                variant="quiet"
                disabled={!selectableItems.length}
                onClick={togglePage}
              >
                {allPageSelected ? "Tout désélectionner" : "Tout sélectionner"}
              </Button>
              <Button
                type="button"
                variant="quiet"
                disabled={!canDeactivateSelection}
                onClick={() => openBatchAction("deactivate")}
              >
                <PowerOff size={18} aria-hidden="true" /> Désactiver (
                {selectedItems.length})
              </Button>
              <Button
                type="button"
                variant="danger"
                disabled={!canDeleteSelection}
                onClick={() => openBatchAction("delete")}
              >
                <Trash2 size={18} aria-hidden="true" /> Supprimer (
                {selectedItems.length})
              </Button>
            </div>
          </div>
          {selectedItems.length > 0 &&
            !canDeactivateSelection &&
            !canDeleteSelection && (
              <p className={styles.selectionHint} role="status">
                Sélectionnez uniquement des comptes actifs à désactiver ou des
                comptes désactivés à supprimer.
              </p>
            )}
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      aria-label="Sélectionner tous les comptes de cette page"
                      checked={allPageSelected}
                      disabled={!selectableItems.length}
                      onChange={togglePage}
                    />
                  </th>
                  <th scope="col">Personne</th>
                  <th scope="col">Identifiant</th>
                  <th scope="col">Fonction</th>
                  <th scope="col">Unité principale</th>
                  <th scope="col">État</th>
                  <th scope="col">Accès</th>
                </tr>
              </thead>
              <tbody>
                {users.data.items.map((user) => (
                  <tr
                    key={user.id}
                    className={selected.has(user.id) ? styles.selectedRow : ""}
                  >
                    <td data-label="Sélection">
                      <input
                        type="checkbox"
                        aria-label={`Sélectionner ${user.name}`}
                        checked={selected.has(user.id)}
                        disabled={!isSelectable(user)}
                        onChange={() => toggle(user)}
                      />
                    </td>
                    <td data-label="Personne">
                      <Link to={`/administration/utilisateurs/${user.id}`}>
                        <strong>{user.name}</strong>
                      </Link>
                      <span>{user.email}</span>
                    </td>
                    <td data-label="Identifiant">{user.login_alias || "—"}</td>
                    <td data-label="Fonction">{user.position || "—"}</td>
                    <td data-label="Unité principale">
                      {user.primary_unit?.code ?? "—"}
                    </td>
                    <td data-label="État">
                      <StatusBadge
                        status={user.is_active ? "completed" : "rejected"}
                      >
                        {user.is_active ? "Actif" : "Désactivé"}
                      </StatusBadge>
                    </td>
                    <td data-label="Accès">
                      {!user.has_usable_password
                        ? "À activer"
                        : user.password_change_required
                          ? "Mot de passe à changer"
                          : "Ouvert"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {users.data.pages > 1 && (
            <nav
              className={styles.pagination}
              aria-label="Pagination des utilisateurs"
            >
              <Button
                type="button"
                variant="quiet"
                disabled={users.data.page <= 1}
                onClick={() => changePage((users.data?.page ?? 2) - 1)}
              >
                Précédent
              </Button>
              <span>
                Page {users.data.page} sur {users.data.pages}
              </span>
              <Button
                type="button"
                variant="quiet"
                disabled={users.data.page >= users.data.pages}
                onClick={() => changePage((users.data?.page ?? 0) + 1)}
              >
                Suivant
              </Button>
            </nav>
          )}
        </>
      )}

      {batchAction && (
        <div className={styles.modalBackdrop}>
          <section
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="user-batch-title"
          >
            <h2 id="user-batch-title">
              {batchAction === "delete"
                ? `Supprimer ${selectedItems.length} compte(s) ?`
                : `Désactiver ${selectedItems.length} compte(s) ?`}
            </h2>
            <p>
              {batchAction === "delete"
                ? "Seuls les comptes désactivés sans aucune donnée liée seront supprimés. Cette opération est définitive."
                : "Les personnes ne pourront plus se connecter. Leurs tâches et leurs historiques seront conservés."}
            </p>
            <ul className={styles.selectedUsers}>
              {selectedItems.map((item) => (
                <li key={item.id}>{item.name}</li>
              ))}
            </ul>
            <form
              className="stack"
              onSubmit={(event) => void applyBatchAction(event)}
            >
              {batchAction === "delete" && (
                <>
                  <div className="form-field">
                    <label htmlFor="user-delete-reason">Motif</label>
                    <textarea
                      id="user-delete-reason"
                      required
                      minLength={3}
                      maxLength={75}
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                    />
                  </div>
                  <div className="form-field">
                    <label htmlFor="user-delete-confirmation">
                      Saisir SUPPRIMER
                    </label>
                    <input
                      id="user-delete-confirmation"
                      required
                      value={confirmation}
                      onChange={(event) => setConfirmation(event.target.value)}
                      autoComplete="off"
                    />
                  </div>
                </>
              )}
              {mutationError && (
                <p className="error-banner" role="alert">
                  {mutationError}
                </p>
              )}
              <div className="cluster">
                <Button
                  variant={batchAction === "delete" ? "danger" : "primary"}
                  disabled={
                    mutating ||
                    (batchAction === "delete" &&
                      (confirmation !== "SUPPRIMER" ||
                        reason.trim().length < 3))
                  }
                >
                  {mutating
                    ? "Traitement…"
                    : batchAction === "delete"
                      ? "Supprimer définitivement"
                      : "Désactiver les comptes"}
                </Button>
                <Button
                  type="button"
                  variant="quiet"
                  disabled={mutating}
                  onClick={() => setBatchAction(null)}
                >
                  Annuler
                </Button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  );
}
