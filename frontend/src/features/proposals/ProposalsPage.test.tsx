import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { ProposalsPage } from "./ProposalsPage";

function renderPage(entry = "/propositions") {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/propositions" element={<ProposalsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("filtre les propositions par statut, période chevauchante et collaborateur", async () => {
  const user = userEvent.setup();
  renderPage();

  expect(
    await screen.findByRole("heading", { name: "Propositions de tâches" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/3 propositions affichées/i)).toBeInTheDocument();
  await user.click(screen.getByRole("checkbox", { name: "Soumises" }));
  await user.click(screen.getByRole("checkbox", { name: "Validées" }));
  await user.click(screen.getByRole("button", { name: /appliquer/i }));
  expect(screen.getByText("Clarifier la note de cadrage")).toBeInTheDocument();
  expect(
    screen.queryByText("Formaliser le tableau de priorités"),
  ).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /réinitialiser/i }));
  fireEvent.change(screen.getByLabelText("Période à partir du"), {
    target: { value: "20/07/2026" },
  });
  fireEvent.change(screen.getByLabelText("Période jusqu'au"), {
    target: { value: "23/07/2026" },
  });
  expect(screen.getByLabelText("Période à partir du")).toHaveValue(
    "20/07/2026",
  );
  await user.selectOptions(screen.getByLabelText("Collaborateur"), "48");
  await user.click(screen.getByRole("button", { name: /appliquer/i }));
  expect(
    screen.getByText("Formaliser le tableau de priorités"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("Clarifier la note de cadrage"),
  ).not.toBeInTheDocument();
});

test("ouvre la tâche acceptée et valide une carte soumise", async () => {
  const user = userEvent.setup();
  renderPage();

  const accepted = await screen.findByRole("link", {
    name: "Ouvrir Consolider le tableau des engagements",
  });
  expect(accepted).toHaveAttribute("href", "/taches/31");
  expect(
    screen.getByRole("link", {
      name: "Ouvrir Formaliser le tableau de priorités",
    }),
  ).toHaveAttribute("href", "/propositions/45");

  await user.click(screen.getByRole("button", { name: "Valider" }));
  await waitFor(() =>
    expect(
      screen.getByRole("link", {
        name: "Ouvrir Formaliser le tableau de priorités",
      }),
    ).toHaveAttribute("href", "/taches/31"),
  );
  expect(
    screen.queryByRole("button", { name: "Valider" }),
  ).not.toBeInTheDocument();
});
