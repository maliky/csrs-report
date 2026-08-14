import { Filter, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Button,
  EmptyState,
  ErrorState,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import { apiFetch } from "../../lib/api/client";
import type {
  TaskBulkDeleteResult,
  TaskManagementItem,
  TaskManagementPage as TaskManagementResponse,
} from "../../lib/api/types";
import { formatDate } from "../../lib/format";
import { useSearchParams } from "../../lib/router";
import { useApi } from "../../lib/useApi";
import styles from "./taskManagement.module.css";

const STATUS_OPTIONS = [
  ["planned", "Planifiée"],
  ["active", "En cours"],
  ["awaiting_validation", "À valider"],
  ["completed", "Terminée"],
  ["closed_early", "Clôturée avant achèvement"],
] as const;

type FilterDraft = { q: string; status: string; employee: string };

function draftFrom(params: URLSearchParams): FilterDraft {
  return {
    q: params.get("q") ?? "",
    status: params.get("status") ?? "",
    employee: params.get("employee_id") ?? "",
  };
}

export function TaskManagementPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState(() => draftFrom(searchParams));
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [mutationError, setMutationError] = useState("");
  const [success, setSuccess] = useState("");
  const query = searchParams.toString();
  const endpoint = `/api/v1/task-management/${query ? `?${query}` : ""}`;
  const { data, error, loading, reload } =
    useApi<TaskManagementResponse>(endpoint);

  useEffect(() => {
    setDraft(draftFrom(searchParams));
    setSelected(new Set());
  }, [searchParams]);

  const selectedItems = useMemo(() => {
    if (!data) return [];
    return data.items.filter((item) => selected.has(item.id));
  }, [data, selected]);
  const allPageSelected = Boolean(
    data?.items.length && data.items.every((item) => selected.has(item.id)),
  );

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = new URLSearchParams();
    if (draft.q.trim()) next.set("q", draft.q.trim());
    if (draft.status) next.set("status", draft.status);
    if (draft.employee) next.set("employee_id", draft.employee);
    setSearchParams(next);
  }

  function resetFilters() {
    setDraft({ q: "", status: "", employee: "" });
    setSearchParams(new URLSearchParams());
  }

  function toggle(item: TaskManagementItem) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      return next;
    });
  }

  function togglePage() {
    if (!data) return;
    setSelected(
      allPageSelected ? new Set() : new Set(data.items.map((item) => item.id)),
    );
  }

  function changePage(page: number) {
    const next = new URLSearchParams(searchParams);
    if (page > 1) next.set("page", String(page));
    else next.delete("page");
    setSearchParams(next);
  }

  async function deleteSelection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedItems.length) return;
    setDeleting(true);
    setMutationError("");
    try {
      const result = await apiFetch<TaskBulkDeleteResult>(
        "/api/v1/tasks/bulk-delete/",
        {
          method: "POST",
          body: JSON.stringify({
            assignments: selectedItems.map((item) => ({
              id: item.id,
              revision: item.revision,
            })),
            reason,
            confirmation,
          }),
        },
      );
      setSuccess(
        `${result.deleted_assignments} tâche(s) supprimée(s). Journal nº ${result.audit_id}.`,
      );
      setConfirming(false);
      setSelected(new Set());
      setReason("");
      setConfirmation("");
      await reload();
    } catch (caught) {
      setMutationError(
        caught instanceof Error ? caught.message : "Suppression impossible.",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Administration IT</p>
          <h1>Gestion des tâches</h1>
          <p>
            Recherchez et supprimez un lot de tâches avec une trace d’audit.
          </p>
        </div>
        <Button
          variant="danger"
          disabled={!selectedItems.length}
          onClick={() => {
            setMutationError("");
            setConfirming(true);
          }}
        >
          <Trash2 size={18} aria-hidden="true" /> Supprimer (
          {selectedItems.length})
        </Button>
      </header>

      {success && (
        <p className="success-banner" role="status">
          {success}
        </p>
      )}
      <form className={styles.filters} onSubmit={applyFilters}>
        <div className="form-field">
          <label htmlFor="task-management-q">Recherche</label>
          <input
            id="task-management-q"
            value={draft.q}
            onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            placeholder="Code, titre ou collaborateur"
          />
        </div>
        <div className="form-field">
          <label htmlFor="task-management-status">Statut</label>
          <select
            id="task-management-status"
            value={draft.status}
            onChange={(event) =>
              setDraft({ ...draft, status: event.target.value })
            }
          >
            <option value="">Tous les statuts</option>
            {STATUS_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="task-management-employee">Collaborateur</label>
          <select
            id="task-management-employee"
            value={draft.employee}
            onChange={(event) =>
              setDraft({ ...draft, employee: event.target.value })
            }
          >
            <option value="">Tous les collaborateurs</option>
            {data?.employees.map((employee) => (
              <option key={employee.id} value={employee.id}>
                {employee.name}
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

      {loading && <Skeleton label="Chargement des tâches à gérer" />}
      {error && <ErrorState error={error} retry={() => void reload()} />}
      {data && !data.items.length && (
        <EmptyState title="Aucune tâche">
          Aucune tâche ne correspond aux filtres.
        </EmptyState>
      )}
      {data && data.items.length > 0 && (
        <>
          <p className={styles.resultCount}>{data.total} tâche(s)</p>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">
                    <input
                      type="checkbox"
                      aria-label="Sélectionner toutes les tâches de cette page"
                      checked={allPageSelected}
                      onChange={togglePage}
                    />
                  </th>
                  <th scope="col">Tâche</th>
                  <th scope="col">Collaborateur</th>
                  <th scope="col">Responsable</th>
                  <th scope="col">Statut</th>
                  <th scope="col">Progression</th>
                  <th scope="col">Période</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr
                    key={item.id}
                    className={selected.has(item.id) ? styles.selectedRow : ""}
                  >
                    <td data-label="Sélection">
                      <input
                        type="checkbox"
                        aria-label={`Sélectionner ${item.code} ${item.title}`}
                        checked={selected.has(item.id)}
                        onChange={() => toggle(item)}
                      />
                    </td>
                    <td data-label="Tâche">
                      <strong>{item.code}</strong>
                      <span>{item.title}</span>
                    </td>
                    <td data-label="Collaborateur">{item.employee.name}</td>
                    <td data-label="Responsable">{item.manager.name}</td>
                    <td data-label="Statut">
                      <StatusBadge status={item.status}>
                        {item.status_label}
                      </StatusBadge>
                    </td>
                    <td data-label="Progression">{item.percentage} %</td>
                    <td data-label="Période">
                      {formatDate(item.start_date)} –{" "}
                      {formatDate(item.due_date)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.pages > 1 && (
            <nav
              className={styles.pagination}
              aria-label="Pagination des tâches"
            >
              <Button
                type="button"
                variant="quiet"
                disabled={data.page <= 1}
                onClick={() => changePage(data.page - 1)}
              >
                Précédent
              </Button>
              <span>
                Page {data.page} sur {data.pages}
              </span>
              <Button
                type="button"
                variant="quiet"
                disabled={data.page >= data.pages}
                onClick={() => changePage(data.page + 1)}
              >
                Suivant
              </Button>
            </nav>
          )}
        </>
      )}

      {confirming && (
        <div className={styles.modalBackdrop}>
          <section
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-task-title"
          >
            <h2 id="delete-task-title">
              Supprimer {selectedItems.length} tâche(s) ?
            </h2>
            <p>
              Cette suppression est définitive. Un journal minimal sera
              conservé.
            </p>
            <form
              className="stack"
              onSubmit={(event) => void deleteSelection(event)}
            >
              <div className="form-field">
                <label htmlFor="task-delete-reason">Motif</label>
                <textarea
                  id="task-delete-reason"
                  required
                  minLength={3}
                  maxLength={500}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </div>
              <div className="form-field">
                <label htmlFor="task-delete-confirmation">
                  Saisir SUPPRIMER
                </label>
                <input
                  id="task-delete-confirmation"
                  required
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  autoComplete="off"
                />
              </div>
              {mutationError && (
                <p className="error-banner" role="alert">
                  {mutationError}
                </p>
              )}
              <div className="cluster">
                <Button
                  variant="danger"
                  disabled={
                    deleting ||
                    confirmation !== "SUPPRIMER" ||
                    reason.trim().length < 3
                  }
                >
                  {deleting ? "Suppression…" : "Supprimer définitivement"}
                </Button>
                <Button
                  type="button"
                  variant="quiet"
                  disabled={deleting}
                  onClick={() => setConfirming(false)}
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
