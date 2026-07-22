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

test("la navigation latérale reste utilisable", async ({ page }, testInfo) => {
  await page.goto("");
  await expect(page.getByRole("heading", { name: "Mes tâches" })).toBeVisible();
  if (testInfo.project.name === "telephone") {
    const open = page.getByRole("button", { name: "Ouvrir le menu" });
    await open.click();
    await expect(
      page.getByRole("link", { name: "Propositions" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Fermer le menu" }).click();
  } else {
    await page.getByRole("button", { name: "Réduire le menu" }).click();
    await expect(
      page.getByRole("button", { name: "Déployer le menu" }),
    ).toBeVisible();
  }
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test("prévisualise et enregistre une régression", async ({ page }) => {
  await page.goto("taches/31");
  await expect(
    page.getByRole("heading", {
      name: "Finaliser les priorités de la quinzaine",
    }),
  ).toBeVisible();
  await page.getByRole("slider", { name: /avancement/i }).fill("80");
  await expect(page.getByText(/aperçu non enregistré : 80 %/i)).toBeVisible();
  await page
    .getByLabel("Observation", { exact: true })
    .fill("Contrôle complémentaire nécessaire.");
  await page
    .getByRole("button", { name: "Enregistrer la progression" })
    .click();
  await expect(page.getByText("Progression enregistrée à 80 %.")).toBeVisible();
  await expect(page.getByText("80 % réalisé")).toBeVisible();
  await expect(page.getByText(/aperçu non enregistré/i)).toHaveCount(0);
});

test("filtre et valide une proposition sans débordement", async ({ page }) => {
  await page.goto("propositions");
  await expect(
    page.getByRole("heading", { name: "Propositions de tâches" }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: "Validées" }).uncheck();
  await page.getByRole("checkbox", { name: "Rejetées" }).uncheck();
  await page.getByRole("button", { name: /appliquer/i }).click();
  await expect(
    page.getByText("Formaliser le tableau de priorités"),
  ).toBeVisible();
  const card = page
    .getByRole("link", { name: "Ouvrir Formaliser le tableau de priorités" })
    .locator("xpath=ancestor::section[1]");
  const validate = card.getByRole("button", { name: "Valider" });
  const [cardBox, buttonBox] = await Promise.all([
    card.boundingBox(),
    validate.boundingBox(),
  ]);
  expect(cardBox).not.toBeNull();
  expect(buttonBox).not.toBeNull();
  expect(buttonBox!.x).toBeGreaterThanOrEqual(cardBox!.x);
  expect(buttonBox!.x + buttonBox!.width).toBeLessThanOrEqual(
    cardBox!.x + cardBox!.width,
  );
  await validate.click();
  await expect(card.getByText("Validée")).toBeVisible();
});
