import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "../../lib/router";
import { TaskManagementPage } from "./TaskManagementPage";

test("selectionne et supprime plusieurs taches avec confirmation", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <TaskManagementPage />
    </MemoryRouter>,
  );

  expect(
    await screen.findByText("Finaliser les priorités de la quinzaine"),
  ).toBeInTheDocument();
  await user.click(
    screen.getByRole("checkbox", {
      name: "Sélectionner toutes les tâches de cette page",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Supprimer (2)" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Motif"), "Nettoyage du pilote");
  await user.type(screen.getByLabelText("Saisir SUPPRIMER"), "SUPPRIMER");
  await user.click(
    screen.getByRole("button", { name: "Supprimer définitivement" }),
  );

  expect(
    await screen.findByText(/2 tâche\(s\) supprimée\(s\)/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Aucune tâche" }),
  ).toBeInTheDocument();
});
