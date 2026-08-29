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
  Repeat2,
  Settings,
  UserCog,
  Users,
  UserRoundCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "../lib/router";
import { apiFetch } from "../lib/api/client";
import type { RoleSimulationOptions, Session } from "../lib/api/types";
import { Button, ErrorState, Skeleton } from "../components/ui";
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
  const roleSwitcherButton = useRef<HTMLButtonElement>(null);
  const [roleDialogOpen, setRoleDialogOpen] = useState(false);
  const [roleOptions, setRoleOptions] = useState<RoleSimulationOptions | null>(
    null,
  );
  const [roleQuery, setRoleQuery] = useState("");
  const [roleError, setRoleError] = useState("");
  const [switchingUserId, setSwitchingUserId] = useState<number | null>(null);
  const navigate = useNavigate();
  const filteredRoleOptions = useMemo(() => {
    const query = roleQuery.trim().toLocaleLowerCase("fr");
    if (!query) return roleOptions?.users ?? [];
    return (roleOptions?.users ?? []).filter((option) =>
      [
        option.name,
        option.position,
        option.login_alias ?? "",
        ...option.roles.map((role) => `${role.name} ${role.unit}`),
      ]
        .join(" ")
        .toLocaleLowerCase("fr")
        .includes(query),
    );
  }, [roleOptions, roleQuery]);

  useEffect(() => {
    const refreshProfile = () => void reload();
    window.addEventListener("csrs:profile-updated", refreshProfile);
    return () =>
      window.removeEventListener("csrs:profile-updated", refreshProfile);
  }, [reload]);
  const location = useLocation();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    function closeOnEscape(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (roleDialogOpen) {
        setRoleDialogOpen(false);
        roleSwitcherButton.current?.focus();
      } else if (mobileOpen) {
        setMobileOpen(false);
        mobileToggle.current?.focus();
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen, roleDialogOpen]);

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

  async function openRoleSwitcher() {
    setRoleDialogOpen(true);
    setRoleError("");
    setRoleQuery("");
    try {
      setRoleOptions(
        await apiFetch<RoleSimulationOptions>(
          "/api/v1/session/impersonation/options/",
        ),
      );
    } catch (caught) {
      setRoleError(
        caught instanceof Error ? caught.message : "Liste indisponible",
      );
    }
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
      setRoleDialogOpen(false);
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
          {session.capabilities.switch_role && (
            <button
              ref={roleSwitcherButton}
              type="button"
              className={styles.navItem}
              title="Changer de rôle"
              onClick={() => void openRoleSwitcher()}
            >
              <Repeat2 size={iconSize} aria-hidden="true" />
              <span className={styles.navLabel}>Changer de rôle</span>
            </button>
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
      {roleDialogOpen && (
        <div className={styles.roleModalBackdrop}>
          <section
            className={styles.roleModal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="role-switcher-title"
          >
            <div className={styles.roleModalHeading}>
              <div>
                <p className="eyebrow">Simulation sécurisée</p>
                <h2 id="role-switcher-title">Changer de rôle</h2>
              </div>
              <Button
                type="button"
                variant="quiet"
                onClick={() => setRoleDialogOpen(false)}
              >
                Fermer
              </Button>
            </div>
            <div className="form-field">
              <label htmlFor="role-user-search">Rechercher une personne</label>
              <input
                id="role-user-search"
                type="search"
                autoFocus
                value={roleQuery}
                onChange={(event) => setRoleQuery(event.target.value)}
              />
            </div>
            {roleError && (
              <div className="error-banner" role="alert">
                {roleError}
              </div>
            )}
            <div className={styles.roleOptions}>
              {filteredRoleOptions.map((option) => (
                <article className={styles.roleOption} key={option.id}>
                  <div>
                    <strong>{option.name}</strong>
                    <span>{option.position || "Fonction non renseignée"}</span>
                    <small>
                      {option.roles
                        .map((role) =>
                          role.unit ? `${role.name} · ${role.unit}` : role.name,
                        )
                        .join(" · ")}
                    </small>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={switchingUserId !== null}
                    onClick={() => void startRoleSimulation(option.id)}
                  >
                    {switchingUserId === option.id
                      ? "Activation…"
                      : `Agir comme ${option.name}`}
                  </Button>
                </article>
              ))}
              {roleOptions && filteredRoleOptions.length === 0 && (
                <p className="muted">Aucun utilisateur ne correspond.</p>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
