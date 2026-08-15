import { render, screen, waitFor, within } from "@testing-library/react";
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
  expect(
    screen.getByRole("button", {
      name: "Du 10/08/2026 au 16/08/2026",
    }),
  ).toBeInTheDocument();
  await user.click(
    screen.getByRole("button", {
      name: "Du 10/08/2026 au 16/08/2026",
    }),
  );
  expect(
    screen.getByRole("dialog", { name: "Choisir la période" }),
  ).toBeVisible();
  expect(
    screen.getByText("Cliquez sur la date de début, puis sur la date de fin."),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Annuler" }));
  await user.click(screen.getByRole("button", { name: "Semaine prochaine" }));
  expect(
    screen.getByRole("heading", {
      name: "Direction des programmes · du 10/08/2026 au 16/08/2026",
    }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Direction de l’agenda")).toHaveValue(
    "programs",
  );
  expect(
    screen.getAllByRole("button", { name: "Générer le PDF" }),
  ).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "Générer le PDF" }));

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

test("applique une plage choisie sur un calendrier unique sans requête intermédiaire", async () => {
  const requestedPeriods: string[] = [];
  server.use(
    http.get("/api/v1/agenda/preview/", ({ request }) => {
      const url = new URL(request.url);
      const periodStart = url.searchParams.get("period_start") ?? "";
      const periodEnd = url.searchParams.get("period_end") ?? "";
      requestedPeriods.push(`${periodStart}:${periodEnd}`);
      return HttpResponse.json({
        draft: {
          period_start: periodStart,
          period_end: periodEnd,
          major_events: "",
          revision: 0,
        },
        snapshot: {
          ...emptySnapshot,
          period_start: periodStart,
          period_end: periodEnd,
        },
      });
    }),
    http.get("/api/v1/visits/", ({ request }) => {
      const url = new URL(request.url);
      return HttpResponse.json({
        period_start: url.searchParams.get("period_start"),
        period_end: url.searchParams.get("period_end"),
        visits: [],
      });
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

  await screen.findByRole("heading", {
    name: "Direction des programmes · du 10/08/2026 au 16/08/2026",
  });
  expect(requestedPeriods).toEqual(["2026-08-10:2026-08-16"]);

  await user.click(
    screen.getByRole("button", {
      name: "Du 10/08/2026 au 16/08/2026",
    }),
  );
  const dialog = screen.getByRole("dialog", { name: "Choisir la période" });
  await user.click(
    within(dialog).getByRole("button", { name: /20 août 2026/i }),
  );
  expect(
    within(dialog).getByText(
      "Début sélectionné : 20/08/2026. Choisissez maintenant la date de fin.",
    ),
  ).toBeInTheDocument();
  expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
  expect(
    within(dialog).getByRole("button", { name: "Appliquer" }),
  ).toBeDisabled();
  expect(requestedPeriods).toHaveLength(1);
  expect(
    screen.getByRole("heading", {
      name: "Direction des programmes · du 10/08/2026 au 16/08/2026",
    }),
  ).toBeInTheDocument();

  await user.click(
    within(dialog).getByRole("button", { name: /26 août 2026/i }),
  );
  await user.click(within(dialog).getByRole("button", { name: "Appliquer" }));

  expect(
    await screen.findByRole("heading", {
      name: "Direction des programmes · du 20/08/2026 au 26/08/2026",
    }),
  ).toBeInTheDocument();
  expect(requestedPeriods).toEqual([
    "2026-08-10:2026-08-16",
    "2026-08-20:2026-08-26",
  ]);
});

test("conserve le dernier agenda visible si le changement de période échoue", async () => {
  let failRefresh = false;
  server.use(
    http.get("/api/v1/agenda/preview/", ({ request }) => {
      if (failRefresh)
        return HttpResponse.json(
          {
            error: {
              code: "temporary_failure",
              message: "Service temporairement indisponible.",
            },
          },
          { status: 503 },
        );
      const url = new URL(request.url);
      const periodStart = url.searchParams.get("period_start") ?? "";
      const periodEnd = url.searchParams.get("period_end") ?? "";
      return HttpResponse.json({
        draft: {
          period_start: periodStart,
          period_end: periodEnd,
          major_events: "",
          revision: 0,
        },
        snapshot: {
          ...emptySnapshot,
          period_start: periodStart,
          period_end: periodEnd,
        },
      });
    }),
    http.get("/api/v1/visits/", ({ request }) => {
      const url = new URL(request.url);
      return HttpResponse.json({
        period_start: url.searchParams.get("period_start"),
        period_end: url.searchParams.get("period_end"),
        visits: [],
      });
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

  await screen.findByRole("heading", {
    name: "Direction des programmes · du 10/08/2026 au 16/08/2026",
  });
  await user.click(
    screen.getByRole("button", {
      name: "Du 10/08/2026 au 16/08/2026",
    }),
  );
  const dialog = screen.getByRole("dialog", { name: "Choisir la période" });
  await user.click(
    within(dialog).getByRole("button", { name: /20 août 2026/i }),
  );
  await user.click(
    within(dialog).getByRole("button", { name: /26 août 2026/i }),
  );
  failRefresh = true;
  await user.click(within(dialog).getByRole("button", { name: "Appliquer" }));

  expect(
    await screen.findByText(/Mise à jour impossible.*Service temporairement/i),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", {
      name: "Direction des programmes · du 10/08/2026 au 16/08/2026",
    }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Impossible de charger cette page" }),
  ).not.toBeInTheDocument();

  failRefresh = false;
  await user.click(screen.getByRole("button", { name: "Réessayer" }));
  await waitFor(() =>
    expect(
      screen.getByRole("heading", {
        name: "Direction des programmes · du 20/08/2026 au 26/08/2026",
      }),
    ).toBeInTheDocument(),
  );
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
