import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "../lib/router";
import { AppShell } from "./AppShell";

test("réduit la barre latérale et mémorise le choix", async () => {
  window.localStorage.clear();
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<h1>Contenu de test</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  expect(await screen.findByText("Contenu de test")).toBeInTheDocument();
  const team = screen.getByRole("link", { name: "Mon équipe" });
  const proposals = screen.getByRole("link", { name: "Propositions" });
  expect(
    team.compareDocumentPosition(proposals) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Réduire le menu" }));
  expect(window.localStorage.getItem("csrs.sidebar.collapsed")).toBe("true");
  expect(
    screen.getByRole("button", { name: "Déployer le menu" }),
  ).toBeInTheDocument();
});

test("ouvre et ferme le tiroir mobile avec des contrôles accessibles", async () => {
  window.localStorage.clear();
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<h1>Contenu mobile</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  await screen.findByText("Contenu mobile");
  const open = screen.getByRole("button", {
    name: "Ouvrir le menu",
    hidden: true,
  });
  fireEvent.click(open);
  expect(open).toHaveAttribute("aria-expanded", "true");
  const close = screen.getByRole("button", {
    name: "Fermer le menu",
    hidden: true,
  });
  fireEvent.click(close);
  expect(open).toHaveAttribute("aria-expanded", "false");
});
