import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "../../lib/router";
import { emptyDashboardHandler } from "../../mocks/handlers";
import { dashboardFixture } from "../../mocks/fixtures";
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

test("masque les tâches terminées jusqu'à leur ouverture", async () => {
  const user = userEvent.setup();
  const completed = {
    ...dashboardFixture.tasks[0],
    id: 999,
    title: "Tâche déjà terminée",
    status: "completed",
    status_label: "Terminée",
  };
  server.use(
    http.get("/api/v1/dashboard/", () =>
      HttpResponse.json({
        ...dashboardFixture,
        tasks: [...dashboardFixture.tasks, completed],
      }),
    ),
  );
  render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );

  const toggle = await screen.findByRole("checkbox", {
    name: "Afficher les tâches terminées",
  });
  expect(screen.queryByText("Tâche déjà terminée")).not.toBeInTheDocument();
  await user.click(toggle);
  expect(screen.getByText("Tâche déjà terminée")).toBeInTheDocument();
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
      name: "Aucune tâche en cours sur cette période",
    }),
  ).toBeInTheDocument();
});
