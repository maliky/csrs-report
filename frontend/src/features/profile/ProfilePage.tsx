import { useEffect, useState, type FormEvent } from "react";
import { apiFetch } from "../../lib/api/client";
import type { UserProfile } from "../../lib/api/types";
import { useApi } from "../../lib/useApi";
import { Button, ButtonLink, Card, ErrorState, Skeleton } from "../../components/ui";
import { useNavigate } from "../../lib/router";

export function ProfilePage() {
  const { data, error, loading, reload, setData } = useApi<UserProfile>(
    "/api/v1/me/profile/",
  );
  const [termsOfReference, setTermsOfReference] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [mutationError, setMutationError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    if (data) setTermsOfReference(data.terms_of_reference);
  }, [data]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMutationError("");
    setMessage("");
    try {
      const saved = await apiFetch<UserProfile>("/api/v1/me/profile/", {
        method: "PATCH",
        body: JSON.stringify({ terms_of_reference: termsOfReference }),
      });
      setData(saved);
      setTermsOfReference(saved.terms_of_reference);
      setMessage("Le cahier des charges a été mis à jour.");
    } catch (caught) {
      setMutationError(
        caught instanceof Error ? caught.message : "Enregistrement impossible",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Skeleton label="Chargement du profil" />;
  if (error || !data)
    return (
      <ErrorState error={error ?? new Error("Profil indisponible")} retry={reload} />
    );

  return (
    <>
      <header className="page-heading">
        <div>
          <p className="eyebrow">Mon compte</p>
          <h1>Mon profil</h1>
          <p>Consultez vos informations et mettez à jour votre cahier des charges.</p>
        </div>
        <ButtonLink to="/" variant="quiet">
          Retour au tableau de bord
        </ButtonLink>
      </header>
      <Card>
        <h2>Informations classiques</h2>
        <dl className="details-grid">
          <div className="detail">
            <dt>Nom</dt>
            <dd>{data.last_name || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Prénom</dt>
            <dd>{data.first_name || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Identifiant</dt>
            <dd>{data.login_alias || "—"}</dd>
          </div>
          <div className="detail">
            <dt>E-mail</dt>
            <dd>{data.email || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Fonction</dt>
            <dd>{data.position || "—"}</dd>
          </div>
          <div className="detail">
            <dt>Téléphone</dt>
            <dd>{data.phone || "—"}</dd>
          </div>
        </dl>
      </Card>
      <Card>
        <h2>Cahier des charges de l'employé</h2>
        <p className="muted">
          Décrivez vos objectifs et vos attendus opérationnels. Ce texte reste
          consultable pour vos supérieurs.
        </p>
        <form className="form-grid" onSubmit={onSubmit}>
          <div className="form-field wide">
            <label htmlFor="terms-of-reference">Cahier des charges</label>
            <textarea
              id="terms-of-reference"
              name="terms_of_reference"
              value={termsOfReference}
              onChange={(event) => setTermsOfReference(event.target.value)}
            />
          </div>
          <div className="cluster wide">
            <Button disabled={saving}>
              {saving ? "Enregistrement…" : "Enregistrer"}
            </Button>
            <Button variant="quiet" type="button" onClick={() => void navigate(-1)}>
              Annuler
            </Button>
            {mutationError && <div className="error-banner">{mutationError}</div>}
            {message && (
              <p className="success-banner" role="status">
                {message}
              </p>
            )}
          </div>
        </form>
      </Card>
    </>
  );
}
