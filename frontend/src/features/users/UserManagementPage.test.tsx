import { render, screen } from "@testing-library/react";
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
