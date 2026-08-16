import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { server } from "../../mocks/server";
import { ProposalFormPage } from "./ProposalFormPage";

test("définit le bon pas/minimum selon l'unité sélectionnée", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/propositions/nouvelle"]}>
      <Routes>
        <Route
          path="/propositions/nouvelle"
          element={<ProposalFormPage mode="create" />}
        />
      </Routes>
    </MemoryRouter>,
  );

  const workload = await screen.findByLabelText(/Charge estimée/);
  expect(workload).toHaveAttribute("min", "0.5");
  expect(workload).toHaveAttribute("step", "0.5");

  await user.click(screen.getByRole("button", { name: "Heures" }));
  expect(workload).toHaveAttribute("min", "1");
  expect(workload).toHaveAttribute("step", "1");
});

test("convertit la saisie heures en jours pour la planification et l'enregistrement", async () => {
  const user = userEvent.setup();
  let lastSubmit: Record<string, unknown> | null = null;
  let lastPreview: Record<string, string> | null = null;

  server.use(
    http.post("/api/v1/planning/preview/", async ({ request }) => {
      lastPreview = (await request.json()) as Record<string, string>;
      return HttpResponse.json({
        start_date: String(lastPreview.start_date),
        due_date: String(lastPreview.due_date),
        estimated_work_days: String(lastPreview.estimated_work_days),
      });
    }),
    http.post("/api/v1/proposals/", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      lastSubmit = body;
      return HttpResponse.json({
        id: 101,
        revision: 1,
        title: String(body.title),
        description: String(body.description),
        status: "submitted",
        status_label: "Soumise",
        start_date: String(body.start_date),
        due_date: String(body.due_date),
        estimated_work_days: String(body.estimated_work_days),
        action: null,
        calendar: { id: 1, label: "Calendrier par défaut" },
        employee: {
          id: 8,
          name: "Aïssata Koné",
          position: "Directrice générale",
          login_alias: "dg",
        },
        accepted_assignment_id: null,
        decision_note: "",
        created_at: "2026-07-17T12:00:00Z",
        can_review: false,
        capabilities: { edit: true, resubmit: false, review: false },
      });
    }),
  );

  render(
    <MemoryRouter initialEntries={["/propositions/nouvelle"]}>
      <Routes>
        <Route
          path="/propositions/nouvelle"
          element={<ProposalFormPage mode="create" />}
        />
      </Routes>
    </MemoryRouter>,
  );

  await user.type(await screen.findByLabelText("Nom court"), "Saisie en heures");
  await user.type(screen.getByLabelText("Description"), "Description test");
  await user.click(screen.getByRole("button", { name: "Heures" }));
  const workload = screen.getByLabelText(/Charge estimée/);
  await user.clear(workload);
  await user.type(workload, "16");

  await waitFor(() => {
    expect(lastPreview).not.toBeNull();
    expect(lastPreview).toHaveProperty("estimated_work_days", "2.0");
  });

  await user.click(screen.getByRole("button", { name: "Soumettre" }));

  await waitFor(() => {
    expect(lastSubmit).not.toBeNull();
    expect(lastSubmit).toMatchObject({ estimated_work_days: "2.0" });
  });
});

test("arrondit la saisie manuelle selon l'unité et la progression clavier", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/propositions/nouvelle"]}>
      <Routes>
        <Route
          path="/propositions/nouvelle"
          element={<ProposalFormPage mode="create" />}
        />
      </Routes>
    </MemoryRouter>,
  );

  const workload = await screen.findByLabelText(/Charge estimée/);
  await user.clear(workload);
  await user.type(workload, "1.2");
  await user.tab();
  expect(workload).toHaveValue(1);

  await user.click(screen.getByRole("button", { name: "Heures" }));
  await user.clear(workload);
  await user.type(workload, "13");
  await user.tab();
  expect(workload).toHaveValue(13);

  await user.click(screen.getByRole("button", { name: "Jours" }));
  await user.clear(workload);
  await user.type(workload, "2.1");
  await user.tab();
  expect(workload).toHaveValue(2);

  await user.click(workload);
  await user.keyboard("{ArrowUp}");
  expect(workload).toHaveValue(2.5);
});
