import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "../../lib/router";
import { TaskFormPage } from "./TaskFormPage";

test("applique les bons pas/minimum selon l'unité", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/taches/nouvelle"]}>
      <Routes>
        <Route path="/taches/nouvelle" element={<TaskFormPage mode="create" />} />
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

test("arrondit et incrémente le champ charge selon l'unité choisie", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={["/taches/nouvelle"]}>
      <Routes>
        <Route path="/taches/nouvelle" element={<TaskFormPage mode="create" />} />
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
  await user.type(workload, "4.4");
  await user.tab();
  expect(workload).toHaveValue(4);

  await user.click(workload);
  await user.keyboard("{ArrowDown}");
  expect(workload).toHaveValue(3);
});
