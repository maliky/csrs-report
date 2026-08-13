import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, vi } from "vitest";
import { MemoryRouter } from "../../lib/router";
import { server } from "../../mocks/server";
import { AgendaPage } from "./AgendaPage";
import { AvailabilityPage } from "./AvailabilityPage";

const emptySnapshot = {
  schema_version: 2,
  period_start: "2026-08-10",
  period_end: "2026-08-16",
  agenda_direction: "programs",
  agenda_direction_label: "Direction des programmes",
  major_events: "",
  unclassified_users: [],
  arrivals: [],
  departures: [],
  availability: [],
  units: [],
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date("2026-08-05T12:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

test("enregistre une arrivée puis l’affiche parmi les visites en cours", async () => {
  let visits: object[] = [];
  server.use(
    http.get("/api/v1/agenda/preview/", () =>
      HttpResponse.json({
        draft: {
          period_start: "2026-08-10",
          period_end: "2026-08-16",
          major_events: "",
          revision: 0,
        },
        snapshot: emptySnapshot,
      }),
    ),
    http.get("/api/v1/visits/", () =>
      HttpResponse.json({
        period_start: "2026-08-10",
        period_end: "2026-08-16",
        visits,
      }),
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
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <MemoryRouter>
      <AgendaPage />
    </MemoryRouter>,
  );

  await screen.findByRole("heading", { name: "Agendas de direction" });
  await user.clear(screen.getByLabelText("Nombre arrivé"));
  await user.type(screen.getByLabelText("Nombre arrivé"), "2");
  await user.type(screen.getByLabelText(/Noms/), "Awa Test");
  await user.click(screen.getByRole("button", { name: /Notifier l’arrivée/ }));

  expect(await screen.findByText("Awa Test")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /Marquer le départ/ }),
  ).toBeInTheDocument();
});

test("enregistre le brouillon avant de générer une version PDF", async () => {
  let draftRevision: number | null = null;
  let versions: object[] = [];
  server.use(
    http.get("/api/v1/agenda/preview/", () =>
      HttpResponse.json({
        draft: {
          period_start: "2026-08-10",
          period_end: "2026-08-16",
          major_events: "",
          revision: 0,
        },
        snapshot: emptySnapshot,
      }),
    ),
    http.get("/api/v1/visits/", () =>
      HttpResponse.json({
        period_start: "2026-08-10",
        period_end: "2026-08-16",
        visits: [],
      }),
    ),
    http.put("/api/v1/agenda/draft/", async ({ request }) => {
      const body = (await request.json()) as { revision: number };
      draftRevision = body.revision;
      return HttpResponse.json({
        period_start: "2026-08-10",
        period_end: "2026-08-16",
        major_events: "",
        revision: 1,
      });
    }),
    http.post("/api/v1/agenda/versions/", () => {
      const version = {
        id: 31,
        period_start: "2026-08-10",
        period_end: "2026-08-16",
        agenda_direction: "programs",
        agenda_direction_label: "Direction des programmes",
        version: 1,
        snapshot_sha256: "a".repeat(64),
        pdf_sha256: "b".repeat(64),
        pdf_size: 2048,
        generated_by: {
          id: 2,
          name: "Secrétariat DG",
          position: "Secrétariat",
        },
        generated_at: "2026-08-07T09:00:00Z",
        pdf_url: "/api/v1/agenda/versions/31/pdf/",
      };
      versions = [version];
      return HttpResponse.json(version, { status: 201 });
    }),
    http.get("/api/v1/agenda/versions/", () => HttpResponse.json({ versions })),
  );
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <MemoryRouter>
      <AgendaPage />
    </MemoryRouter>,
  );

  await screen.findByRole("heading", { name: "Agendas de direction" });
  expect(screen.getByLabelText("Début")).toHaveValue("10/08/2026");
  expect(screen.getByLabelText("Fin")).toHaveValue("16/08/2026");
  expect(
    screen.getByRole("heading", {
      name: "Direction des programmes · du 10/08/2026 au 16/08/2026",
    }),
  ).toBeInTheDocument();
  await user.click(
    screen.getByRole("button", {
      name: /Générer — Direction des programmes/,
    }),
  );

  expect(
    await screen.findByText(
      "La nouvelle version PDF « Direction des programmes » est archivée et prête à imprimer.",
    ),
  ).toBeInTheDocument();
  expect(draftRevision).toBe(0);
  expect(
    await screen.findByText(
      "Direction des programmes · du 10/08/2026 au 16/08/2026 — version 1",
    ),
  ).toBeInTheDocument();
});

test("permet aux RH d’ajouter un congé à la semaine", async () => {
  let items: object[] = [];
  let submitted: Record<string, unknown> | null = null;
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
      submitted = body;
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
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(
    <MemoryRouter>
      <AvailabilityPage />
    </MemoryRouter>,
  );

  await screen.findByRole("heading", { name: "Absences et missions" });
  expect(screen.getByLabelText("Semaine")).toHaveValue("03/08/2026");
  expect(screen.getByLabelText("Début")).toHaveValue("03/08/2026");
  expect(screen.getByLabelText("Fin")).toHaveValue("03/08/2026");
  await user.click(screen.getByRole("button", { name: "Ajouter" }));
  expect(await screen.findByText("Mariam Koné — Congé")).toBeInTheDocument();
  expect(screen.getByText("Du 03/08/2026 au 03/08/2026")).toBeInTheDocument();
  expect(submitted).toEqual(
    expect.objectContaining({
      start_date: "2026-08-03",
      end_date: "2026-08-03",
    }),
  );
});
