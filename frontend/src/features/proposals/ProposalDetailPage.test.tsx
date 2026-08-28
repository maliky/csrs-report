import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { proposalsFixture, sessionFixture } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
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

test("permet à l'auteur de supprimer une proposition soumise", async () => {
  const user = userEvent.setup();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  const submitted = {
    ...proposalsFixture.reviewable[0],
    employee: sessionFixture.user,
    can_review: false,
    capabilities: {
      edit: true,
      resubmit: false,
      review: false,
      delete: true,
    },
  };
  server.use(
    http.get("/api/v1/proposals/45/", () => HttpResponse.json(submitted)),
  );
  render(
    <MemoryRouter initialEntries={["/propositions/45"]}>
      <Routes>
        <Route
          path="/propositions/:proposalId"
          element={<ProposalDetailPage />}
        />
        <Route path="/propositions" element={<h1>Liste des propositions</h1>} />
      </Routes>
    </MemoryRouter>,
  );

  const cancel = await screen.findByRole("button", {
    name: "Supprimer la proposition",
  });
  await user.click(cancel);
  expect(
    await screen.findByRole("heading", { name: "Liste des propositions" }),
  ).toBeInTheDocument();
  confirm.mockRestore();
});
