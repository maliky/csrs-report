import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "../../lib/router";
import { server } from "../../mocks/server";
import { AgendaPage } from "./AgendaPage";
import { AvailabilityPage } from "./AvailabilityPage";

const emptySnapshot = {
  schema_version: 1,
  week_start: "2026-08-03",
  week_end: "2026-08-09",
  major_events: "",
  arrivals: [],
  departures: [],
  availability: [],
  units: [],
};

test("enregistre une arrivée puis l’affiche parmi les visites en cours", async () => {
  let visits: object[] = [];
  server.use(
    http.get("/api/v1/agenda/preview/", () =>
      HttpResponse.json({
        draft: { week_start: "2026-08-03", major_events: "", revision: 0 },
        snapshot: emptySnapshot,
      }),
    ),
    http.get("/api/v1/visits/", () =>
      HttpResponse.json({ week_start: "2026-08-03", visits }),
    ),
    http.post("/api/v1/visits/", async ({ request }) => {
      const body = (await request.json()) as {
        party_size: number;
        visitor_names: string[];
      };
      visits = [
        {
          id: 17,
          revision: 1,
          party_size: body.party_size,
          visitor_names: body.visitor_names,
          arrived_at: "2026-08-05T09:00:00Z",
          departed_at: null,
          cancelled_at: null,
        },
      ];
      return HttpResponse.json(visits[0], { status: 201 });
    }),
    http.get("/api/v1/agenda/versions/", () =>
      HttpResponse.json({ versions: [] }),
    ),
  );
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <AgendaPage />
    </MemoryRouter>,
  );

  await screen.findByRole("heading", { name: "Agenda hebdomadaire" });
  await user.clear(screen.getByLabelText("Nombre arrivé"));
  await user.type(screen.getByLabelText("Nombre arrivé"), "2");
  await user.type(screen.getByLabelText(/Noms/), "Awa Test");
  await user.click(screen.getByRole("button", { name: /Notifier l’arrivée/ }));

  expect(await screen.findByText("Awa Test")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /Marquer le départ/ }),
  ).toBeInTheDocument();
});

test("permet aux RH d’ajouter un congé à la semaine", async () => {
  let items: object[] = [];
  const employee = { id: 9, name: "Mariam Koné", position: "Chercheuse" };
  server.use(
    http.get("/api/v1/availability/", () =>
      HttpResponse.json({
        week_start: "2026-08-03",
        items,
        employees: [employee],
        kinds: [
          { value: "leave", label: "Congé" },
          { value: "absence", label: "Absence" },
          { value: "mission", label: "Mission" },
        ],
      }),
    ),
    http.post("/api/v1/availability/", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      items = [
        {
          id: 21,
          revision: 1,
          employee,
          kind: body.kind,
          kind_label: "Congé",
          start_date: body.start_date,
          end_date: body.end_date,
          note: body.note,
          cancelled_at: null,
        },
      ];
      return HttpResponse.json(items[0], { status: 201 });
    }),
  );
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <AvailabilityPage />
    </MemoryRouter>,
  );

  await screen.findByRole("heading", { name: "Absences et missions" });
  await user.click(screen.getByRole("button", { name: "Ajouter" }));
  expect(await screen.findByText("Mariam Koné — Congé")).toBeInTheDocument();
});
