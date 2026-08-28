import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { dashboardFixture, profileFixture } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { EmployeePage } from "./EmployeePage";

test("masque par défaut les tâches terminées du collaborateur", async () => {
  const user = userEvent.setup();
  const completed = {
    ...dashboardFixture.tasks[0],
    id: 998,
    title: "Mission collaborateur terminée",
    status: "completed",
    status_label: "Terminée",
  };
  server.use(
    http.get("/api/v1/team/10/", () =>
      HttpResponse.json({
        period: dashboardFixture.period,
        employee: profileFixture,
        tasks: [...dashboardFixture.tasks, completed],
      }),
    ),
  );
  render(
    <MemoryRouter initialEntries={["/equipe/10"]}>
      <Routes>
        <Route path="/equipe/:employeeId" element={<EmployeePage />} />
      </Routes>
    </MemoryRouter>,
  );

  const filter = await screen.findByRole("checkbox", {
    name: "Afficher les tâches terminées",
  });
  expect(
    screen.queryByText("Mission collaborateur terminée"),
  ).not.toBeInTheDocument();
  await user.click(filter);
  expect(
    screen.getByText("Mission collaborateur terminée"),
  ).toBeInTheDocument();
});
