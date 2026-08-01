import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { server } from "../../mocks/server";
import { ProcessDetailPage } from "./ProcessDetailPage";

function detail(actions = ["claim"]) {
  return {
    id: 31,
    reference: "OM-2026-00A1",
    revision: actions.includes("claim") ? 3 : 4,
    status: "assistance",
    status_label: "Préparation par l'assistance",
    current_step: "assistance",
    initiator: { id: 8, name: "Aïssata Koné", position: "DG", login_alias: "dg" },
    origin_unit: { id: 2, name: "Direction de la recherche", short_name: "drrv" },
    mission_type: "domestic",
    mission_type_label: "Mission nationale",
    destination: "Bouaké",
    purpose: "Coordonner la campagne scientifique.",
    departure_date: "2026-08-10",
    return_date: "2026-08-12",
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:10:00Z",
    due_date: "2026-08-03",
    claimed_by: null,
    available_actions: actions,
    mission: {
      itinerary: "Abidjan — Bouaké",
      transport_mode: "Véhicule",
      transport_company: "",
      funding_source: "Projet",
      costs_covered: "Transport",
      vehicle_required: false,
      vehicle_details: "",
      official_number: "",
    },
    participants: [{ id: 8, name: "Aïssata Koné", position: "DG", login_alias: "dg" }],
    documents: [],
    events: [{ id: 1, kind: "created", from_status: "", to_status: "draft", message: "Brouillon créé.", actor: { id: 8, name: "Aïssata Koné", position: "DG", login_alias: "dg" }, occurred_at: "2026-08-01T10:00:00Z" }],
    capabilities: { edit: false, upload: false, download_documents: true, export: false },
    signature: null,
  };
}

test("rend la file visible puis permet de prendre le dossier en charge", async () => {
  let state = detail();
  server.use(
    http.get("/api/v1/processes/31/", () => HttpResponse.json(state)),
    http.post("/api/v1/processes/31/actions/", async ({ request }) => {
      const body = (await request.json()) as { action: string; revision: number };
      expect(body).toEqual(expect.objectContaining({ action: "claim", revision: 3 }));
      state = detail(["send_to_signature"]);
      return HttpResponse.json(state);
    }),
  );
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/processus/31"]}>
      <Routes><Route path="/processus/:processId" element={<ProcessDetailPage />} /></Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText("File de service")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Prendre en charge" }));
  expect(await screen.findByRole("button", { name: "Transmettre au DG" })).toBeInTheDocument();
});
