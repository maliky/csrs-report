import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "../../lib/router";
import { server } from "../../mocks/server";
import { AvailabilityPage } from "./AvailabilityPage";

test("permet aux RH de saisir le nom précis de l'employé", async () => {
  const user = userEvent.setup();
  let employeeId: number | null = null;
  server.use(
    http.get("/api/v1/availability/", () =>
      HttpResponse.json({
        week_start: "2026-08-24",
        items: [],
        employees: [
          {
            id: 10,
            name: "Awa Finance",
            position: "Analyste",
            login_alias: "awa",
            avatar: "",
          },
          {
            id: 11,
            name: "Mariam Atall",
            position: "Responsable TSI",
            login_alias: "mariam",
            avatar: "",
          },
        ],
        kinds: [{ value: "absence", label: "Absence" }],
      }),
    ),
    http.post("/api/v1/availability/", async ({ request }) => {
      const body = (await request.json()) as { employee_id: number };
      employeeId = body.employee_id;
      return HttpResponse.json({}, { status: 201 });
    }),
  );
  render(
    <MemoryRouter>
      <AvailabilityPage />
    </MemoryRouter>,
  );

  const employee = await screen.findByLabelText("Employé concerné");
  await user.type(employee, "Awa Finance — Analyste");
  await user.click(screen.getByRole("button", { name: "Ajouter" }));

  await waitFor(() => expect(employeeId).toBe(10));
});
