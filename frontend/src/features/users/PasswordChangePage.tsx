import { KeyRound, LogOut } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, ButtonLink, Card } from "../../components/ui";
import { ApiError, apiFetch } from "../../lib/api/client";
import styles from "./users.module.css";

export function PasswordChangePage({
  onComplete,
  onLogout,
  required = false,
}: {
  onComplete?: () => Promise<unknown> | unknown;
  onLogout?: () => Promise<unknown> | unknown;
  required?: boolean;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    const formElement = event.currentTarget;
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<void>("/api/v1/session/password/", {
        method: "POST",
        body: JSON.stringify({
          current_password: form.get("current_password"),
          new_password: form.get("new_password"),
          new_password_confirmation: form.get("new_password_confirmation"),
        }),
      });
      formElement.reset();
      setSuccess("Le mot de passe a été modifié.");
      await onComplete?.();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Le mot de passe n’a pas pu être remplacé.",
      );
    } finally {
      setSaving(false);
    }
  }

  const card = (
    <Card className={styles.passwordCard}>
      <p className="eyebrow">Sécurité du compte</p>
      <h1>Choisir un nouveau mot de passe</h1>
      <p>
        {required
          ? "Le mot de passe transmis par l’administrateur est temporaire. Remplacez-le avant d’accéder à l’application."
          : "Saisissez votre mot de passe actuel, puis choisissez un nouveau mot de passe sécurisé."}
      </p>
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
        <div className="form-field">
          <label htmlFor="temporary-password">
            {required ? "Mot de passe temporaire" : "Mot de passe actuel"}
          </label>
          <input
            id="temporary-password"
            name="current_password"
            type="password"
            autoComplete="current-password"
            required
          />
        </div>
        <div className="form-field">
          <label htmlFor="new-password">Nouveau mot de passe</label>
          <input
            id="new-password"
            name="new_password"
            type="password"
            autoComplete="new-password"
            required
          />
        </div>
        <div className="form-field">
          <label htmlFor="new-password-confirmation">
            Confirmer le nouveau mot de passe
          </label>
          <input
            id="new-password-confirmation"
            name="new_password_confirmation"
            type="password"
            autoComplete="new-password"
            required
          />
        </div>
        <div className="cluster">
          <Button disabled={saving}>
            <KeyRound size={18} aria-hidden="true" />
            {saving ? "Enregistrement…" : "Enregistrer"}
          </Button>
          {onLogout && (
            <Button
              type="button"
              variant="quiet"
              disabled={saving}
              onClick={() => void onLogout()}
            >
              <LogOut size={18} aria-hidden="true" /> Déconnexion
            </Button>
          )}
        </div>
      </form>
    </Card>
  );

  if (required) return <main className={styles.passwordPage}>{card}</main>;
  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Sécurité du compte</p>
          <h1>Modifier mon mot de passe</h1>
        </div>
        <ButtonLink to="/profil" variant="quiet">
          Retour au profil
        </ButtonLink>
      </header>
      {card}
    </>
  );
}
