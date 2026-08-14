import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { TransferSelector } from "./TransferSelector";

test("ajoute et retire les choix avec des controles accessibles", async () => {
  const user = userEvent.setup();
  const onAdd = vi.fn();
  const onRemove = vi.fn();
  render(
    <TransferSelector
      legend="Unités actuelles"
      available={[{ id: 1, label: "DAF" }]}
      selected={[{ id: 2, label: "CFIN" }]}
      onAdd={onAdd}
      onRemove={onRemove}
    />,
  );

  await user.selectOptions(
    screen.getByRole("listbox", { name: /Disponibles/ }),
    "1",
  );
  await user.click(screen.getByRole("button", { name: /Ajouter/ }));
  expect(onAdd).toHaveBeenCalledWith([1]);

  await user.selectOptions(
    screen.getByRole("listbox", { name: /Sélectionnés/ }),
    "2",
  );
  await user.click(screen.getByRole("button", { name: /Retirer/ }));
  expect(onRemove).toHaveBeenCalledWith([2]);
});

test("filtre une liste sans modifier la selection", async () => {
  const user = userEvent.setup();
  render(
    <TransferSelector
      legend="Équipe directe"
      available={[
        { id: 1, label: "Awa Koné" },
        { id: 2, label: "Mariam Traoré" },
      ]}
      selected={[]}
      onAdd={() => undefined}
      onRemove={() => undefined}
    />,
  );

  await user.type(
    screen.getAllByPlaceholderText("Filtrer la liste")[0],
    "Mariam",
  );
  expect(
    screen.queryByRole("option", { name: "Awa Koné" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("option", { name: "Mariam Traoré" }),
  ).toBeInTheDocument();
});
