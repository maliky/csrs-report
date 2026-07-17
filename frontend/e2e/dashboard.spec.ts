import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("le dashboard reste lisible et accessible", async ({ page }) => {
  await page.goto("?month=2026-07");
  await expect(page.getByRole("heading", { name: "Mes tâches" })).toBeVisible();
  await expect(
    page.getByText("Finaliser les priorités de la quinzaine"),
  ).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
