import { NavLink, Outlet } from "react-router-dom";
import { apiFetch } from "../lib/api/client";
import type { Session } from "../lib/api/types";
import { ErrorState, Skeleton } from "../components/ui";
import { useApi } from "../lib/useApi";
import styles from "./shell.module.css";

export function AppShell() {
  const {
    data: session,
    error,
    loading,
    reload,
  } = useApi<Session>("/api/v1/session/");

  if (loading)
    return (
      <main className={styles.main}>
        <Skeleton label="Chargement de la session" />
      </main>
    );
  if (error || !session)
    return (
      <main className={styles.main}>
        <ErrorState
          error={error ?? new Error("Session indisponible")}
          retry={reload}
        />
      </main>
    );

  async function signOut() {
    await apiFetch<void>("/api/v1/session/logout/", { method: "POST" });
    window.location.assign("/connexion/");
  }

  const navClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? styles.active : "";
  return (
    <>
      <a className="skip-link" href="#contenu">
        Aller au contenu
      </a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <NavLink to="/" className={styles.brand}>
            CSRS Report
          </NavLink>
          <nav className={styles.nav} aria-label="Navigation principale">
            <NavLink to="/" end className={navClass}>
              Mes tâches
            </NavLink>
            <NavLink to="/propositions" className={navClass}>
              Propositions
            </NavLink>
            {session.capabilities.view_team && (
              <NavLink to="/equipe" className={navClass}>
                Mon équipe
              </NavLink>
            )}
            {session.capabilities.create_task && (
              <NavLink to="/taches/nouvelle" className={navClass}>
                Affecter
              </NavLink>
            )}
            <a href="/">Interface classique</a>
            {session.capabilities.admin && <a href="/admin/">Administration</a>}
            <button type="button" onClick={() => void signOut()}>
              Déconnexion
            </button>
            <span className={styles.user}>{session.user.name}</span>
          </nav>
        </div>
      </header>
      <main id="contenu" className={styles.main} tabIndex={-1}>
        <Outlet context={session} />
      </main>
      <footer className={styles.footer}>
        CSRS Report · Suivi collaboratif et responsable
      </footer>
    </>
  );
}
