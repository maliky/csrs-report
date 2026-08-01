import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "../../lib/router";
import { dashboardFixture } from "../../mocks/fixtures";
import { TaskCard } from "./TaskCard";

test("présente statut, progression et charge au premier regard", () => {
  render(
    <MemoryRouter>
      <TaskCard task={dashboardFixture.tasks[0]} />
    </MemoryRouter>,
  );
  expect(
    screen.getByRole("heading", {
      name: "Finaliser les priorités de la quinzaine",
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "90",
  );
  expect(screen.getByText("2,4 jours")).toBeInTheDocument();
  expect(screen.getByText("En cours")).toBeInTheDocument();
});
