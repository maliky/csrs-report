import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { MemoryRouter, useLocation } from "../../lib/router";
import { teamFixture } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { TeamPage } from "./TeamPage";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function renderPage(entry = "/equipe?month=2026-07") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <TeamPage />
      <LocationProbe />
    </MemoryRouter>,
  );
}

function summaryFor(name: string): HTMLElement {
  const summary = screen.getByText(name).closest("summary");
  if (!summary) throw new Error(`Résumé introuvable pour ${name}`);
  return summary;
}

test("ne charge pas le détail collaborateur à l'ouverture de la branche", async () => {
  const user = userEvent.setup();
  let requests = 0;
  server.use(
    http.get("/api/v1/team/12/", () => {
      requests += 1;
      return HttpResponse.json({
        period: teamFixture.period,
        employee: {
          id: 12,
          name: "Awa Finances",
          position: "Responsable des finances",
          login_alias: "finances",
        },
        tasks: [],
      });
    }),
  );
  renderPage();

  expect(
    await screen.findByRole("heading", { name: "Synthèse de l'équipe" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Voir la progression" }),
  ).not.toBeInTheDocument();

  const root = summaryFor("Direction administrative et financière").closest(
    "details",
  );
  const child = summaryFor("Awa Finances").closest("details");
  expect(root).toHaveAttribute("open");
  expect(child).not.toHaveAttribute("open");
  if (!root) throw new Error("Branche racine introuvable");
  expect(
    within(root).getByRole("link", {
      name: /Direction administrative et financière/,
    }),
  ).toHaveAttribute("href", "/equipe/11?month=2026-07");
  if (!child) throw new Error("Branche enfant introuvable");
  expect(
    within(child).getByRole("link", {
      name: /Awa Finances/,
    }),
  ).toHaveAttribute("href", "/equipe/12?month=2026-07");

  await user.click(summaryFor("Awa Finances"));
  expect(child).toHaveAttribute("open");
  expect(requests).toBe(0);

  await user.click(summaryFor("Awa Finances"));
  await user.click(summaryFor("Direction administrative et financière"));
  await user.click(summaryFor("Direction administrative et financière"));
  await waitFor(() => expect(requests).toBe(0));
});

test("filtre récursivement et conserve le choix entre les périodes", async () => {
  const user = userEvent.setup();
  renderPage();
  await screen.findByRole("heading", { name: "Synthèse de l'équipe" });

  await user.click(screen.getByRole("button", { name: "Avec tâches" }));
  expect(
    screen.getByText("Direction administrative et financière"),
  ).toBeInTheDocument();
  expect(screen.getByText("Awa Finances")).toBeInTheDocument();
  expect(screen.getByText("Direction de la valorisation")).toBeInTheDocument();
  expect(screen.queryByText("Contrôle interne")).not.toBeInTheDocument();
  expect(screen.queryByText("Bamba Comptable")).not.toBeInTheDocument();
  expect(screen.getByTestId("location")).toHaveTextContent("tasks=with");

  await user.click(screen.getByRole("link", { name: "Période suivante" }));
  await waitFor(() => {
    const params = new URLSearchParams(
      screen.getByTestId("location").textContent ?? "",
    );
    expect(params.get("month")).toBe("2026-08");
    expect(params.get("tasks")).toBe("with");
  });

  await user.click(await screen.findByRole("button", { name: "Sans tâche" }));
  expect(
    screen.getByText("Direction administrative et financière"),
  ).toBeInTheDocument();
  expect(screen.getByText("Awa Finances")).toBeInTheDocument();
  expect(screen.getByText("Bamba Comptable")).toBeInTheDocument();
  expect(screen.getByText("Contrôle interne")).toBeInTheDocument();
  expect(
    screen.queryByText("Direction de la valorisation"),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Tous" }));
  expect(screen.getByTestId("location")).not.toHaveTextContent("tasks=");
});
