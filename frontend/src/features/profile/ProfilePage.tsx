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
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [avatar, setAvatar] = useState("");
  const [termsOfReference, setTermsOfReference] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [mutationError, setMutationError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    if (!data) return;
    setFirstName(data.first_name);
    setLastName(data.last_name);
    setPhone(data.phone);
    setAvatar(data.avatar);
    setTermsOfReference(data.terms_of_reference);
  }, [data]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMutationError("");
    setMessage("");
    try {
      const saved = await apiFetch<UserProfile>("/api/v1/me/profile/", {
        method: "PATCH",
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          phone,
          avatar,
          terms_of_reference: termsOfReference,
        }),
      });
      setData(saved);
      setFirstName(saved.first_name);
      setLastName(saved.last_name);
      setPhone(saved.phone);
      setAvatar(saved.avatar);
      setTermsOfReference(saved.terms_of_reference);
      setMessage("Le profil a été mis à jour.");
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
        <p className="muted">
          Modifiez vos informations de contact et votre avatar.
        </p>
        <form className="form-grid" onSubmit={onSubmit}>
          <div className="form-field wide">
            <label htmlFor="first-name">Prénom</label>
            <input
              id="first-name"
              name="first_name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="last-name">Nom</label>
            <input
              id="last-name"
              name="last_name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="phone">Téléphone</label>
            <input
              id="phone"
              name="phone"
              type="tel"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </div>
          <div className="form-field wide">
            <label htmlFor="avatar">Avatar</label>
            <input
              id="avatar"
              name="avatar"
              value={avatar}
              onChange={(event) => setAvatar(event.target.value)}
            />
          </div>
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
