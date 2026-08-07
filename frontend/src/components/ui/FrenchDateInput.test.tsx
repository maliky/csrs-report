import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { FrenchDateInput } from "./FrenchDateInput";

test("affiche une valeur ISO au format jj/mm/aaaa et conserve ISO pour le code", async () => {
  const user = userEvent.setup();

  function Example() {
    const [value, setValue] = useState("2026-08-03");
    return (
      <label>
        Date
        <FrenchDateInput value={value} required onValueChange={setValue} />
        <output>{value}</output>
      </label>
    );
  }

  render(<Example />);
  const input = screen.getByLabelText("Date");
  expect(input).toHaveAttribute("type", "text");
  expect(input).toHaveAttribute("placeholder", "jj/mm/aaaa");
  expect(input).toHaveValue("03/08/2026");

  await user.clear(input);
  await user.type(input, "09/08/2026");

  expect(input).toHaveValue("09/08/2026");
  expect(screen.getByText("2026-08-09")).toBeInTheDocument();
});

test("soumet une date ISO et refuse une date française impossible", async () => {
  const user = userEvent.setup();
  render(
    <form data-testid="form">
      <label htmlFor="day">Jour</label>
      <FrenchDateInput id="day" name="day" required defaultValue="2026-08-03" />
    </form>,
  );
  const input = screen.getByLabelText("Jour");
  const form = screen.getByTestId("form") as HTMLFormElement;

  expect(new FormData(form).get("day")).toBe("2026-08-03");
  await user.clear(input);
  await user.type(input, "31/02/2026");

  expect(input).toBeInvalid();
  expect((input as HTMLInputElement).validationMessage).toBe(
    "Saisissez une date valide au format jj/mm/aaaa.",
  );
  expect(new FormData(form).get("day")).toBe("");

  fireEvent.change(input, { target: { value: "2026-08-12" } });
  expect(input).toHaveValue("12/08/2026");
  expect(input).toBeValid();
  expect(new FormData(form).get("day")).toBe("2026-08-12");
});
