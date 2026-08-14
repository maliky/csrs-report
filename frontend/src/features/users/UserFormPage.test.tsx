import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { server } from "../../mocks/server";
import { UserFormPage } from "./UserFormPage";

const manager = {
  id: 10,
  name: "Awa Koné",
  position: "Directrice",
  login_alias: "daf",
};
const employee = {
  id: 11,
  name: "Mariam Traoré",
  position: "Comptable",
  login_alias: "mtraore",
};
const replacement = {
  id: 12,
  name: "Yao N’Guessan",
  position: "Directeur adjoint",
  login_alias: "yng",
};

test("exige un nouveau responsable avant de retirer un collaborateur", async () => {
  const user = userEvent.setup();
  let submitted: Record<string, unknown> | null = null;
  server.use(
    http.get("/api/v1/users/options/", () =>
      HttpResponse.json({
        today: "2026-08-14",
        units: [
          {
            id: 1,
            code: "DAF",
            short_name: "DAF",
            long_name: "Direction administrative et financière",
            label: "DAF — Direction administrative et financière",
          },
        ],
        users: [manager, employee, replacement],
        agenda_directions: [
          { value: "administration", label: "Direction administrative" },
        ],
      }),
    ),
    http.get("/api/v1/users/10/", () =>
      HttpResponse.json({
        ...manager,
        email: "awa@example.test",
        is_active: true,
        is_superuser: false,
        password_change_required: false,
        has_usable_password: true,
        primary_unit: {
          id: 1,
          code: "DAF",
          short_name: "DAF",
          long_name: "Direction administrative et financière",
          label: "DAF — Direction administrative et financière",
        },
        first_name: "Awa",
        last_name: "Koné",
        phone: "",
        agenda_direction: "administration",
        include_in_direction_agendas: true,
        unit_ids: [1],
        primary_unit_id: 1,
        primary_supervisor: null,
        state_token: "user-state",
        capabilities: {
          deactivate: true,
          reactivate: false,
          reset_password: true,
          send_activation: false,
          edit: true,
        },
      }),
    ),
    http.get("/api/v1/users/10/collaborators/", () =>
      HttpResponse.json({
        supervisor: manager,
        state_token: "team-state",
        current: [employee],
        available: [],
        replacement_options: { "11": [manager, replacement] },
      }),
    ),
    http.put("/api/v1/users/10/collaborators/", async ({ request }) => {
      submitted = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        supervisor: manager,
        state_token: "team-state-2",
        current: [],
        available: [employee],
        replacement_options: {},
      });
    }),
  );
  render(
    <MemoryRouter initialEntries={["/administration/utilisateurs/10"]}>
      <Routes>
        <Route
          path="administration/utilisateurs/:userId"
          element={<UserFormPage mode="edit" />}
        />
      </Routes>
    </MemoryRouter>,
  );

  const team = await screen.findByRole("group", { name: "Équipe directe" });
  await user.selectOptions(
    within(team).getByRole("listbox", { name: /Sélectionnés/ }),
    "11",
  );
  await user.click(within(team).getByRole("button", { name: /Retirer/ }));
  expect(
    screen.getByRole("heading", { name: "Choisir le nouveau responsable" }),
  ).toBeInTheDocument();
  await user.selectOptions(
    screen.getByLabelText("Nouveau responsable de Mariam Traoré"),
    "12",
  );
  await user.click(
    screen.getByRole("button", { name: "Confirmer la réaffectation" }),
  );
  await user.click(
    screen.getByRole("button", { name: "Enregistrer l’équipe" }),
  );

  await waitFor(() => expect(submitted).not.toBeNull());
  expect(submitted).toMatchObject({
    collaborator_ids: [],
    replacements: [{ employee_id: 11, supervisor_id: 12 }],
    effective_date: "2026-08-14",
    state_token: "team-state",
  });
});
