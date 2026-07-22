import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TaskDetailPage } from "./TaskDetailPage";

test("prévisualise puis enregistre une baisse de progression", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/taches/31"]}>
      <Routes>
        <Route path="/taches/:taskId" element={<TaskDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

  expect(
    await screen.findByRole("heading", {
      name: "Finaliser les priorités de la quinzaine",
    }),
  ).toBeInTheDocument();
  const slider = screen.getByRole("slider", { name: /avancement/i });
  fireEvent.change(slider, { target: { value: "80" } });
  expect(screen.getByText(/aperçu non enregistré : 80 %/i)).toBeInTheDocument();

  const note = screen.getByLabelText("Observation", { selector: "textarea" });
  expect(note).toBeRequired();
  await user.type(note, "Contrôle complémentaire nécessaire.");
  await user.click(
    screen.getByRole("button", { name: "Enregistrer la progression" }),
  );

  expect(
    await screen.findByText("Progression enregistrée à 80 %."),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(
      screen.queryByText(/aperçu non enregistré/i),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByText("80 % réalisé")).toBeInTheDocument();
  expect(
    screen.getByText("Contrôle complémentaire nécessaire."),
  ).toBeInTheDocument();
});
