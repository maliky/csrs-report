import {
  CalendarDays,
  ClipboardList,
  Cog,
  Lightbulb,
  ListPlus,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Users,
  UserRoundCheck,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "../lib/router";
import { apiFetch } from "../lib/api/client";
import type { Session } from "../lib/api/types";
import { ErrorState, Skeleton } from "../components/ui";
import { useApi } from "../lib/useApi";
import styles from "./shell.module.css";

const SIDEBAR_STORAGE_KEY = "csrs.sidebar.collapsed";

export function AppShell() {
  const {
    data: session,
    error,
    loading,
    reload,
  } = useApi<Session>("/api/v1/session/");
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true",
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobileToggle = useRef<HTMLButtonElement>(null);
  const mobileClose = useRef<HTMLButtonElement>(null);
  const location = useLocation();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    function closeOnEscape(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape" && mobileOpen) {
        setMobileOpen(false);
        mobileToggle.current?.focus();
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen]);

  if (loading)
    return (
      <main className={styles.loadingMain}>
        <Skeleton label="Chargement de la session" />
      </main>
    );
  if (error || !session)
    return (
      <main className={styles.loadingMain}>
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

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      return next;
    });
  }

  function openMobile() {
    setMobileOpen(true);
    window.requestAnimationFrame(() => mobileClose.current?.focus());
  }

  const navClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? `${styles.navItem} ${styles.active}` : styles.navItem;
  const iconSize = 20;

  return (
    <div
      className={`${styles.shell} ${collapsed ? styles.shellCollapsed : ""}`}
    >
      <a className="skip-link" href="#contenu">
        Aller au contenu
      </a>
      <header className={styles.mobileBar}>
        <NavLink to="/" className={styles.mobileBrand}>
          CSRS Report
        </NavLink>
        <button
          ref={mobileToggle}
          type="button"
          className={styles.iconButton}
          aria-label="Ouvrir le menu"
          aria-controls="navigation-principale"
          aria-expanded={mobileOpen}
          onClick={openMobile}
        >
          <Menu aria-hidden="true" />
        </button>
      </header>
      {mobileOpen && (
        <button
          className={styles.backdrop}
          type="button"
          aria-label="Fermer le menu"
          onClick={() => {
            setMobileOpen(false);
            mobileToggle.current?.focus();
          }}
        />
      )}
      <aside
        id="navigation-principale"
        className={`${styles.sidebar} ${collapsed ? styles.collapsed : ""} ${mobileOpen ? styles.mobileOpen : ""}`}
        aria-label="Navigation principale"
      >
        <div className={styles.sidebarHeader}>
          <NavLink to="/" className={styles.brand} title="CSRS Report">
            <span className={styles.brandMark}>CR</span>
            <span className={styles.brandLabel}>CSRS Report</span>
          </NavLink>
          <button
            ref={mobileClose}
            type="button"
            className={`${styles.iconButton} ${styles.mobileClose}`}
            aria-label="Fermer le menu"
            onClick={() => {
              setMobileOpen(false);
              mobileToggle.current?.focus();
            }}
          >
            <X aria-hidden="true" />
          </button>
        </div>
        <nav className={styles.nav}>
          <NavLink to="/" end className={navClass} title="Mes tâches">
            <ClipboardList size={iconSize} aria-hidden="true" />
            <span className={styles.navLabel}>Mes tâches</span>
          </NavLink>
          {session.capabilities.view_team && (
            <NavLink to="/equipe" className={navClass} title="Mon équipe">
              <Users size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Mon équipe</span>
            </NavLink>
          )}
          {session.capabilities.view_weekly_agenda && (
            <NavLink
              to="/agenda"
              className={navClass}
              title="Agenda hebdomadaire"
            >
              <CalendarDays size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Agenda</span>
            </NavLink>
          )}
          {session.capabilities.manage_availability && (
            <NavLink
              to="/absences"
              className={navClass}
              title="Absences et missions"
            >
              <UserRoundCheck size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Absences et missions</span>
            </NavLink>
          )}
          <NavLink to="/propositions" className={navClass} title="Propositions">
            <Lightbulb size={iconSize} aria-hidden="true" />
            <span className={styles.navLabel}>Propositions</span>
          </NavLink>
          {session.capabilities.create_task && (
            <NavLink
              to="/taches/nouvelle"
              className={navClass}
              title="Affecter"
            >
              <ListPlus size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Affecter</span>
            </NavLink>
          )}
        </nav>
        <div className={styles.sidebarSecondary}>
          {session.capabilities.delete_tasks && (
            <NavLink
              to="/administration/taches"
              className={navClass}
              title="Gestion des tâches"
            >
              <Cog size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Gestion des tâches</span>
            </NavLink>
          )}
          {session.capabilities.admin && (
            <a href="/admin/" className={styles.navItem} title="Administration">
              <Settings size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Administration</span>
            </a>
          )}
          <button
            type="button"
            className={styles.navItem}
            title="Déconnexion"
            onClick={() => void signOut()}
          >
            <LogOut size={iconSize} aria-hidden="true" />
            <span className={styles.navLabel}>Déconnexion</span>
          </button>
          <div className={styles.user} title={session.user.name}>
            <span className={styles.avatar} aria-hidden="true">
              {session.user.name.slice(0, 1).toUpperCase()}
            </span>
            <span className={styles.userDetails}>
              <strong>{session.user.name}</strong>
              <small>{session.user.position}</small>
            </span>
          </div>
        </div>
        <button
          type="button"
          className={`${styles.collapseButton} ${styles.desktopToggle}`}
          aria-label={collapsed ? "Déployer le menu" : "Réduire le menu"}
          aria-expanded={!collapsed}
          onClick={toggleCollapsed}
          title={collapsed ? "Déployer le menu" : "Réduire le menu"}
        >
          {collapsed ? (
            <PanelLeftOpen size={20} aria-hidden="true" />
          ) : (
            <PanelLeftClose size={20} aria-hidden="true" />
          )}
          <span className={styles.navLabel}>
            {collapsed ? "Déployer" : "Réduire"}
          </span>
        </button>
      </aside>
      <div className={styles.content}>
        <main id="contenu" className={styles.main} tabIndex={-1}>
          <Outlet context={session} />
        </main>
        <footer className={styles.footer}>
          CSRS Report · Suivi collaboratif et responsable
        </footer>
      </div>
    </div>
  );
}
