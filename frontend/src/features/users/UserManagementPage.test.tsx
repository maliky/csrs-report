import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { server } from "../../mocks/server";
import { UserManagementPage } from "./UserManagementPage";

test("liste les comptes et ouvre leur fiche", async () => {
  server.use(
    http.get("/api/v1/users/options/", () =>
      HttpResponse.json({
        today: "2026-08-14",
        units: [
          {
            id: 4,
            code: "DAF",
            short_name: "DAF",
            long_name: "Direction administrative et financière",
            label: "DAF — Direction administrative et financière",
          },
        ],
        users: [],
        agenda_directions: [],
      }),
    ),
    http.get("/api/v1/users/", () =>
      HttpResponse.json({
        items: [
          {
            id: 12,
            name: "Awa Koné",
            position: "Directrice administrative",
            login_alias: "daf",
            email: "awa@example.test",
            is_active: true,
            is_superuser: false,
            password_change_required: false,
            has_usable_password: true,
            state_token: "user-state-12",
            batch_capabilities: { deactivate: true, delete: false },
            primary_unit: {
              id: 4,
              code: "DAF",
              short_name: "DAF",
              long_name: "Direction administrative et financière",
              label: "DAF — Direction administrative et financière",
            },
          },
        ],
        total: 1,
        page: 1,
        pages: 1,
        page_size: 50,
      }),
    ),
  );
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<UserManagementPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText("Awa Koné")).toBeInTheDocument();
  expect(screen.getByText("awa@example.test")).toBeInTheDocument();
  expect(screen.getByText("Ouvert")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Ajouter une personne" }),
  ).toHaveAttribute("href", "/administration/utilisateurs/nouveau");
  expect(screen.getByRole("link", { name: "Awa Koné" })).toHaveAttribute(
    "href",
    "/administration/utilisateurs/12",
  );
});

test("sélectionne, désactive puis supprime des comptes par lot", async () => {
  const user = userEvent.setup();
  const actions: Array<Record<string, unknown>> = [];
  let items = [
    {
      id: 12,
      name: "Compte actif",
      position: "Agent",
      login_alias: "actif",
      email: "actif@example.test",
      is_active: true,
      is_superuser: false,
      password_change_required: false,
      has_usable_password: true,
      primary_unit: null,
      state_token: "active-state",
      batch_capabilities: { deactivate: true, delete: false },
    },
    {
      id: 13,
      name: "Compte orphelin",
      position: "",
      login_alias: "orphelin",
      email: "orphelin@example.test",
      is_active: false,
      is_superuser: false,
      password_change_required: false,
      has_usable_password: true,
      primary_unit: null,
      state_token: "inactive-state",
      batch_capabilities: { deactivate: false, delete: true },
    },
  ];
  server.use(
    http.get("/api/v1/users/options/", () =>
      HttpResponse.json({
        today: "2026-08-15",
        units: [],
        users: [],
        agenda_directions: [],
      }),
    ),
    http.get("/api/v1/users/", () =>
      HttpResponse.json({
        items,
        total: items.length,
        page: 1,
        pages: 1,
        page_size: 50,
      }),
    ),
    http.post("/api/v1/users/bulk-action/", async ({ request }) => {
      const body = (await request.json()) as {
        action: "deactivate" | "delete";
        users: Array<{ id: number }>;
      };
      actions.push(body as unknown as Record<string, unknown>);
      const ids = new Set(body.users.map((item) => item.id));
      if (body.action === "deactivate") {
        items = items.map((item) =>
          ids.has(item.id)
            ? {
                ...item,
                is_active: false,
                state_token: "deactivated-state",
                batch_capabilities: { deactivate: false, delete: true },
              }
            : item,
        );
      } else {
        items = items.filter((item) => !ids.has(item.id));
      }
      return HttpResponse.json({
        action: body.action,
        affected: ids.size,
      });
    }),
  );
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<UserManagementPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText("Compte actif")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Tout sélectionner" }));
  expect(screen.getByRole("button", { name: "Désactiver (2)" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Supprimer (2)" })).toBeDisabled();

  await user.click(
    screen.getByRole("checkbox", { name: "Sélectionner Compte orphelin" }),
  );
  await user.click(screen.getByRole("button", { name: "Désactiver (1)" }));
  await user.click(
    screen.getByRole("button", { name: "Désactiver les comptes" }),
  );
  expect(
    await screen.findByText("1 compte(s) désactivé(s)."),
  ).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Tout sélectionner" }));
  await user.click(screen.getByRole("button", { name: "Supprimer (2)" }));
  await user.type(screen.getByLabelText("Motif"), "Comptes pilotes inutiles");
  await user.type(screen.getByLabelText("Saisir SUPPRIMER"), "SUPPRIMER");
  await user.click(
    screen.getByRole("button", { name: "Supprimer définitivement" }),
  );

  expect(
    await screen.findByRole("heading", { name: "Aucun utilisateur" }),
  ).toBeInTheDocument();
  expect(actions).toHaveLength(2);
  expect(actions[0]).toMatchObject({ action: "deactivate" });
  expect(actions[1]).toMatchObject({
    action: "delete",
    reason: "Comptes pilotes inutiles",
    confirmation: "SUPPRIMER",
  });
});
