import { render, screen } from "@testing-library/react";
import { taskDetailFixture } from "../../mocks/fixtures";
import { ProgressChart } from "./ProgressChart";

test("expose les dates réelles et une alternative textuelle", () => {
  render(
    <ProgressChart
      points={taskDetailFixture.chart}
      today={taskDetailFixture.today}
    />,
  );
  expect(
    screen.getByRole("img", { name: /progression réelle/i }),
  ).toBeInTheDocument();
  expect(
    screen.getAllByRole("button", { name: /progression observée/i }),
  ).toHaveLength(8);
  expect(
    screen.getByText("Afficher les données du graphique"),
  ).toBeInTheDocument();
});
