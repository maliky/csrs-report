import { render, screen } from "@testing-library/react";
import { taskDetailFixture } from "../../mocks/fixtures";
import { ProgressChart } from "./ProgressChart";

test("expose les dates réelles et une alternative textuelle", () => {
  render(
    <ProgressChart
      points={taskDetailFixture.chart}
      today={taskDetailFixture.today}
      status={taskDetailFixture.status}
    />,
  );
  expect(
    screen.getByRole("img", { name: /progression réelle/i }),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Afficher les données du graphique"),
  ).toBeInTheDocument();
});

test("distingue un aperçu de progression de la valeur serveur", () => {
  const { container } = render(
    <ProgressChart
      points={taskDetailFixture.chart}
      today={taskDetailFixture.today}
      status={taskDetailFixture.status}
      previewPercentage={40}
    />,
  );

  expect(screen.getByText(/aperçu non enregistré : 40 %/i)).toBeInTheDocument();
  expect(container.querySelector("path[class*='previewLine']")).toHaveAttribute(
    "d",
  );
  expect(screen.getByText(/valeur serveur 90 %/i)).toBeInTheDocument();
});
