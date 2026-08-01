import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "../../lib/router";
import { emptyDashboardHandler } from "../../mocks/handlers";
import { server } from "../../mocks/server";
import { DashboardPage } from "./DashboardPage";

test("charge les engagements mensuels depuis le contrat API", async () => {
  render(
    <MemoryRouter initialEntries={["/?month=2026-07"]}>
      <DashboardPage />
    </MemoryRouter>,
  );
  expect(await screen.findByText("juillet 2026")).toBeInTheDocument();
  expect(
    screen.getByText("Finaliser les priorités de la quinzaine"),
  ).toBeInTheDocument();
});

test("explique une période vide", async () => {
  server.use(emptyDashboardHandler);
  render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );
  expect(
    await screen.findByRole("heading", {
      name: "Aucune tâche sur cette période",
    }),
  ).toBeInTheDocument();
});
