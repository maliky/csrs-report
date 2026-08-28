import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { server } from "../../mocks/server";
import { MemoryRouter } from "../../lib/router";
import { PasswordChangePage } from "./PasswordChangePage";

test("remplace le mot de passe temporaire avant de continuer", async () => {
  const user = userEvent.setup();
  const onComplete = vi.fn();
  let payload: Record<string, string> | null = null;
  server.use(
    http.post("/api/v1/session/password/", async ({ request }) => {
      payload = (await request.json()) as Record<string, string>;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(
    <PasswordChangePage
      required
      onComplete={onComplete}
      onLogout={() => undefined}
    />,
  );

  await user.type(
    screen.getByLabelText("Mot de passe temporaire"),
    "Temp-2026!",
  );
  await user.type(
    screen.getByLabelText("Nouveau mot de passe"),
    "New-2026!Secure",
  );
  await user.type(
    screen.getByLabelText("Confirmer le nouveau mot de passe"),
    "New-2026!Secure",
  );
  await user.click(screen.getByRole("button", { name: /Enregistrer/ }));

  expect(
    await screen.findByRole("button", { name: /Enregistrer/ }),
  ).toBeEnabled();
  expect(payload).toEqual({
    current_password: "Temp-2026!",
    new_password: "New-2026!Secure",
    new_password_confirmation: "New-2026!Secure",
  });
  expect(onComplete).toHaveBeenCalledOnce();
});

test("permet un changement volontaire depuis le profil", async () => {
  const user = userEvent.setup();
  server.use(
    http.post(
      "/api/v1/session/password/",
      () => new HttpResponse(null, { status: 204 }),
    ),
  );
  render(
    <MemoryRouter>
      <PasswordChangePage />
    </MemoryRouter>,
  );

  await user.type(screen.getByLabelText("Mot de passe actuel"), "Actuel-2026!");
  await user.type(
    screen.getByLabelText("Nouveau mot de passe"),
    "Nouveau-2026!",
  );
  await user.type(
    screen.getByLabelText("Confirmer le nouveau mot de passe"),
    "Nouveau-2026!",
  );
  await user.click(screen.getByRole("button", { name: /Enregistrer/ }));

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Le mot de passe a été modifié.",
  );
});
