import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "../../lib/router";
import { server } from "../../mocks/server";
import { ProcessesPage } from "./ProcessesPage";

const item = {
  id: 31,
  reference: "OM-2026-00A1",
  revision: 3,
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
  available_actions: ["claim"],
};

test("sépare les dossiers à traiter des dossiers du demandeur", async () => {
  server.use(
    http.get("/api/v1/processes/", ({ request }) => {
      const box = new URL(request.url).searchParams.get("box");
      return HttpResponse.json({
        items: box === "mine" ? [] : [item],
        counters: { pending: box === "mine" ? 0 : 1, correction_returns: 2 },
      });
    }),
  );
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <ProcessesPage />
    </MemoryRouter>,
  );

  expect(
    await screen.findByRole("heading", { name: "Bouaké" }),
  ).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "Mes dossiers" }));
  expect(
    await screen.findByText("Créez un ordre de mission pour commencer."),
  ).toBeInTheDocument();
});
