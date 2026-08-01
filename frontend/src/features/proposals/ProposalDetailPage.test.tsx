import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { ProposalDetailPage } from "./ProposalDetailPage";

test("permet à l'auteur de modifier puis resoumettre un rejet", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/propositions/41"]}>
      <Routes>
        <Route
          path="/propositions/:proposalId"
          element={<ProposalDetailPage />}
        />
      </Routes>
    </MemoryRouter>,
  );

  expect(
    await screen.findByRole("heading", {
      name: "Clarifier la note de cadrage",
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /modifier/i })).toHaveAttribute(
    "href",
    "/propositions/41/modifier",
  );
  await user.click(
    screen.getByRole("button", { name: /corriger et resoumettre/i }),
  );
  await waitFor(() => expect(screen.getByText("Soumise")).toBeInTheDocument());
  expect(
    screen.queryByRole("button", { name: /corriger et resoumettre/i }),
  ).not.toBeInTheDocument();
});

test("relie une proposition validée à sa progression", async () => {
  render(
    <MemoryRouter initialEntries={["/propositions/38"]}>
      <Routes>
        <Route
          path="/propositions/:proposalId"
          element={<ProposalDetailPage />}
        />
      </Routes>
    </MemoryRouter>,
  );

  expect(
    await screen.findByRole("link", { name: "Voir la progression" }),
  ).toHaveAttribute("href", "/taches/31");
});
