import { fireEvent, render, screen, within } from "@testing-library/react";
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
  expect(screen.getByText("Début 04/05/2026")).toBeInTheDocument();
  expect(screen.getByText("Aujourd'hui 17/07/2026")).toBeInTheDocument();
  expect(screen.getByText("Fin prévue 24/07/2026")).toBeInTheDocument();
  expect(screen.getByText("Comprendre le graphique")).toBeInTheDocument();
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

test("rend le retard visible dans le graphique et son alternative", () => {
  const overduePoint = {
    ...taskDetailFixture.chart.at(-1)!,
    day: "2026-07-29",
    elapsed_work_days: 62,
    remaining_schedule_days: 0,
    overdue_days: 3,
    observed: false,
  };
  render(
    <ProgressChart
      points={[...taskDetailFixture.chart, overduePoint]}
      today="2026-07-29"
      status="active"
      actionKey={4}
    />,
  );

  expect(screen.getByText("Aujourd'hui 29/07/2026")).toBeInTheDocument();
  expect(screen.getByText("Fin prévue 24/07/2026")).toBeInTheDocument();
  expect(screen.getByText("Retard : 3 jours ouvrés")).toBeInTheDocument();
  const table = screen
    .getByText("Afficher les données du graphique")
    .closest("details");
  if (!table) throw new Error("Alternative textuelle introuvable");
  expect(
    within(table).getByRole("columnheader", { name: "Retard" }),
  ).toBeInTheDocument();
  expect(within(table).getAllByText("3 jours ouvrés")).not.toHaveLength(0);

  const chart = screen.getByLabelText(/Graphique de progression/i);
  fireEvent.keyDown(chart, { key: "End" });
  expect(
    screen
      .getAllByRole("status")
      .some(
        (item) =>
          item.textContent?.includes("29/07/2026") &&
          item.textContent.includes("Retard : 3 jours ouvrés"),
      ),
  ).toBe(true);
});
