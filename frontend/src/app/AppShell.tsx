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
  UserCog,
  Users,
  UserRoundCheck,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "../lib/router";
import { apiFetch } from "../lib/api/client";
import type { RoleSimulationOptions, Session } from "../lib/api/types";
import { ErrorState, Skeleton } from "../components/ui";
import { useApi } from "../lib/useApi";
import styles from "./shell.module.css";
import { PasswordChangePage } from "../features/users/PasswordChangePage";

const SIDEBAR_STORAGE_KEY = "csrs.sidebar.collapsed";

function UserAvatar({
  avatar,
  name,
  className,
}: {
  avatar: string | null;
  name: string;
  className: string;
}) {
  const [imageError, setImageError] = useState(false);
  const initial = name.trim().slice(0, 1).toUpperCase() || "?";

  useEffect(() => setImageError(false), [avatar]);

  if (!avatar || imageError) {
    return <span className={className}>{initial}</span>;
  }

  return (
    <span className={className} aria-hidden="true">
      <img
        src={avatar}
        className={styles.avatarImage}
        alt=""
        onError={() => setImageError(true)}
      />
    </span>
  );
}

export function AppShell() {
  const {
    data: session,
    error,
    loading,
    reload,
    setData,
  } = useApi<Session>("/api/v1/session/");
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true",
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobileToggle = useRef<HTMLButtonElement>(null);
  const mobileClose = useRef<HTMLButtonElement>(null);
  const [roleOptions, setRoleOptions] = useState<RoleSimulationOptions | null>(
    null,
  );
  const [roleError, setRoleError] = useState("");
  const [switchingUserId, setSwitchingUserId] = useState<number | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const refreshProfile = () => void reload();
    window.addEventListener("csrs:profile-updated", refreshProfile);
    return () =>
      window.removeEventListener("csrs:profile-updated", refreshProfile);
  }, [reload]);

  useEffect(() => {
    if (
      !session?.capabilities.switch_role ||
      session.impersonation.active
    )
      return;

    let cancelled = false;
    setRoleOptions(null);
    setRoleError("");
    void apiFetch<RoleSimulationOptions>(
      "/api/v1/session/impersonation/options/",
    )
      .then((options) => {
        if (!cancelled) setRoleOptions(options);
      })
      .catch((caught) => {
        if (cancelled) return;
        setRoleError(
          caught instanceof Error ? caught.message : "Liste indisponible",
        );
      });

    return () => {
      cancelled = true;
    };
  }, [
    session?.capabilities.switch_role,
    session?.impersonation.active,
  ]);
  const location = useLocation();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    function closeOnEscape(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (mobileOpen) {
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

  async function startRoleSimulation(userId: number) {
    setSwitchingUserId(userId);
    setRoleError("");
    try {
      const next = await apiFetch<Session>("/api/v1/session/impersonation/", {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
      setData(next);
      navigate("/");
    } catch (caught) {
      setRoleError(
        caught instanceof Error ? caught.message : "Changement impossible",
      );
    } finally {
      setSwitchingUserId(null);
    }
  }

  async function stopRoleSimulation() {
    setRoleError("");
    const next = await apiFetch<Session>("/api/v1/session/impersonation/", {
      method: "DELETE",
    });
    setData(next);
    navigate("/");
  }

  if (session.capabilities.password_change_required)
    return (
      <PasswordChangePage required onComplete={reload} onLogout={signOut} />
    );

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
          aria-label="Fermer le menu en touchant l’arrière-plan"
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
          {session.capabilities.manage_users && (
            <NavLink
              to="/administration/utilisateurs"
              className={navClass}
              title="Utilisateurs"
            >
              <UserCog size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Utilisateurs</span>
            </NavLink>
          )}
          {session.capabilities.admin && (
            <a
              href="/admin/"
              className={styles.navItem}
              title="Administration avancée"
            >
              <Settings size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Administration avancée</span>
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
          <div className={styles.userAccount}>
            <NavLink
              to="/profil"
              className={`${styles.user} ${styles.userLink}`}
              title="Voir mon profil"
            >
              <UserAvatar
                avatar={session.user.avatar ?? null}
                name={session.user.name}
                className={styles.avatar}
              />
              <span className={styles.userDetails}>
                <strong>{session.user.name}</strong>
                <small>{session.user.position}</small>
              </span>
            </NavLink>
            {session.capabilities.switch_role &&
              !session.impersonation.active && (
                <select
                  id="administrator-role-switcher"
                  className={styles.roleSwitcherCompact}
                  aria-label="Changer de rôle"
                  title="Changer de rôle"
                  value=""
                  disabled={roleOptions === null || switchingUserId !== null}
                  aria-describedby={
                    roleError ? "role-switcher-error" : undefined
                  }
                  onChange={(event) => {
                    const userId = Number(event.target.value);
                    if (userId) void startRoleSimulation(userId);
                  }}
                >
                  <option value="">
                    {switchingUserId !== null
                      ? "Activation en cours…"
                      : roleOptions
                        ? "Changer de rôle…"
                        : "Chargement des utilisateurs…"}
                  </option>
                  {roleOptions?.users.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name} —{" "}
                      {option.position || "Fonction non renseignée"}
                    </option>
                  ))}
                </select>
              )}
          </div>
          {roleError && (
            <small
              id="role-switcher-error"
              className={styles.roleSwitcherError}
              role="alert"
            >
              {roleError}
            </small>
          )}
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
        {session.impersonation.active && (
          <section className={styles.impersonationBanner} role="status">
            <div>
              <strong>Mode utilisateur simulé</strong>
              <span>
                Vous agissez comme {session.user.name}. Les actions sont
                attribuées à cet utilisateur et auditées au nom de{" "}
                {session.impersonation.administrator?.name}.
              </span>
            </div>
            <button type="button" onClick={() => void stopRoleSimulation()}>
              Revenir en administrateur
            </button>
          </section>
        )}
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
