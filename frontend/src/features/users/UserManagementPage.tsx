import { Filter, RotateCcw, UserRoundPlus } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import {
  Button,
  ButtonLink,
  EmptyState,
  ErrorState,
  Skeleton,
  StatusBadge,
} from "../../components/ui";
import type {
  UserManagementOptions,
  UserManagementPage as UserManagementResponse,
} from "../../lib/api/types";
import { Link, useSearchParams } from "../../lib/router";
import { useApi } from "../../lib/useApi";
import styles from "./users.module.css";

type FilterDraft = { q: string; state: string; unit: string };

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
  const options = useApi<UserManagementOptions>("/api/v1/users/options/");
  const query = searchParams.toString();
  const users = useApi<UserManagementResponse>(
    `/api/v1/users/${query ? `?${query}` : ""}`,
  );

  useEffect(() => setDraft(draftFrom(searchParams)), [searchParams]);

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
          <p className={styles.resultCount}>{users.data.total} compte(s)</p>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
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
                  <tr key={user.id}>
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
    </>
  );
}
