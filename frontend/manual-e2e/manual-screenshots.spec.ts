import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const baseURL = process.env.CSRS_MANUAL_BASE_URL ?? "http://127.0.0.1:5173";
const outputDirectory = path.resolve(
  process.cwd(),
  "../docs/manual/screenshots",
);
const demoPassword = process.env.CSRS_DEMO_PASSWORD ?? "";
const adminPassword = process.env.CSRS_ADMIN_PASSWORD ?? "";

function assertLocalTarget(): void {
  const url = new URL(baseURL);
  if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
    throw new Error(
      "Les captures du manuel refusent tout hôte autre que localhost ou 127.0.0.1.",
    );
  }
  if (!demoPassword || !adminPassword) {
    throw new Error("CSRS_DEMO_PASSWORD et CSRS_ADMIN_PASSWORD sont requis.");
  }
}

function site(pathname: string): string {
  return new URL(pathname, baseURL).toString();
}

async function stable(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page.addStyleTag({
    content:
      "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}",
  });
}

async function capture(
  page: Page,
  name: string,
  fullPage = true,
): Promise<void> {
  await stable(page);
  await page.screenshot({
    path: path.join(outputDirectory, name),
    fullPage,
    animations: "disabled",
  });
}

async function login(
  context: BrowserContext,
  alias: string,
  password: string,
): Promise<Page> {
  const page = await context.newPage();
  await page.goto(site("/connexion/?next=/app/"));
  await page.locator('input[name="username"]').fill(alias);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/\/app\//);
  await expect(page.getByRole("heading", { name: "Mes tâches" })).toBeVisible();
  return page;
}

async function desktop(
  browser: Browser,
  alias: string,
  password = demoPassword,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    locale: "fr-FR",
    timezoneId: "Africa/Abidjan",
    colorScheme: "light",
    reducedMotion: "reduce",
  });
  return { context, page: await login(context, alias, password) };
}

test("génère les captures du manuel depuis la démonstration locale", async ({
  browser,
}) => {
  assertLocalTarget();
  mkdirSync(outputDirectory, { recursive: true });

  const loginContext = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    locale: "fr-FR",
  });
  const loginPage = await loginContext.newPage();
  await loginPage.goto(site("/connexion/"));
  await expect(
    loginPage.getByRole("heading", { name: "Connexion" }),
  ).toBeVisible();
  await capture(loginPage, "01-connexion.png", false);
  await loginContext.close();

  const mobileContext = await browser.newContext({
    viewport: { width: 360, height: 800 },
    isMobile: true,
    hasTouch: true,
    locale: "fr-FR",
    timezoneId: "Africa/Abidjan",
    colorScheme: "light",
    reducedMotion: "reduce",
  });
  const mobilePage = await login(mobileContext, "atall", demoPassword);
  await mobilePage.getByRole("button", { name: "Ouvrir le menu" }).click();
  await expect(
    mobilePage.getByRole("link", { name: "Propositions" }),
  ).toBeVisible();
  await capture(mobilePage, "02-navigation-mobile-atall.png", false);
  await mobileContext.close();

  const atall = await desktop(browser, "atall");
  await capture(atall.page, "03-dashboard-atall.png");
  const firstTask = atall.page.locator('main h2 a[href*="/taches/"]').first();
  await expect(firstTask).toBeVisible();
  await firstTask.click();
  await expect(
    atall.page.getByRole("heading", { name: "Progression dans le temps" }),
  ).toBeVisible();
  await capture(atall.page, "04-tache-detail-atall.png");
  const progressHeading = atall.page.getByRole("heading", {
    name: "Progression",
    exact: true,
  });
  await progressHeading.scrollIntoViewIfNeeded();
  await capture(atall.page, "05-progression-observation-atall.png", false);
  await atall.page.goto(site("/app/propositions/nouvelle"));
  await expect(
    atall.page.getByRole("heading", { name: "Proposer une tâche" }),
  ).toBeVisible();
  await capture(atall.page, "06-proposer-tache-atall.png");
  await atall.context.close();

  const daf = await desktop(browser, "daf");
  await daf.page.goto(site("/app/equipe"));
  await expect(
    daf.page.getByRole("heading", { name: "Synthèse de l'équipe" }),
  ).toBeVisible();
  await capture(daf.page, "07-equipe-daf.png");
  await daf.page.goto(site("/app/taches/nouvelle"));
  await expect(
    daf.page.getByRole("heading", { name: "Affecter une tâche" }),
  ).toBeVisible();
  await expect(daf.page.getByLabel("Collaborateur")).toBeVisible();
  await capture(daf.page, "08-affecter-tache-daf.png");
  await daf.page.goto(site("/app/propositions"));
  await expect(
    daf.page.getByRole("heading", { name: "Propositions de tâches" }),
  ).toBeVisible();
  await expect(
    daf.page.getByRole("button", { name: "Valider" }).first(),
  ).toBeVisible();
  await capture(daf.page, "09-valider-proposition-daf.png");
  await daf.context.close();

  const dg = await desktop(browser, "dg");
  await capture(dg.page, "10-dashboard-dg.png");
  await dg.page.goto(site("/app/taches/nouvelle"));
  await expect(
    dg.page.getByRole("heading", { name: "Affecter une tâche" }),
  ).toBeVisible();
  await expect(dg.page.getByLabel("Collaborateur")).toContainText(
    "Direction générale",
  );
  await capture(dg.page, "11-auto-affectation-dg.png");
  await dg.page.goto(site("/app/equipe"));
  await expect(
    dg.page.getByRole("heading", { name: "Synthèse de l'équipe" }),
  ).toBeVisible();
  await capture(dg.page, "12-equipe-dg.png");
  await dg.context.close();

  const secretary = await desktop(browser, "secretariat_dg");
  await secretary.page.goto(site("/app/agenda"));
  await expect(
    secretary.page.getByRole("heading", { name: "Agendas de direction" }),
  ).toBeVisible();
  await expect(
    secretary.page.getByRole("button", {
      name: /Du \d{2}\/\d{2}\/\d{4} au \d{2}\/\d{2}\/\d{4}/,
    }),
  ).toBeVisible();
  await secretary.page
    .getByLabel("Éléments à faire apparaître en tête du rapport")
    .fill("RAS");
  await secretary.page
    .getByRole("button", {
      name: /Du \d{2}\/\d{2}\/\d{4} au \d{2}\/\d{2}\/\d{4}/,
    })
    .click();
  await expect(
    secretary.page.getByRole("dialog", { name: "Choisir la période" }),
  ).toBeVisible();
  await capture(secretary.page, "14-agenda-secretariat-preparation.png");
  await secretary.page.getByRole("button", { name: "Annuler" }).click();
  await secretary.page.getByRole("button", { name: "Générer le PDF" }).click();
  await expect(
    secretary.page.getByText(
      "La nouvelle version PDF « Direction des programmes » est archivée et prête à imprimer.",
    ),
  ).toBeVisible();
  await expect(
    secretary.page.getByRole("link", { name: "Ouvrir le PDF" }).first(),
  ).toBeVisible();
  await capture(secretary.page, "15-agenda-secretariat-version.png");
  await secretary.context.close();

  const dgAgenda = await desktop(browser, "dg");
  await dgAgenda.page.goto(site("/app/agenda"));
  await expect(
    dgAgenda.page.getByRole("heading", { name: "Agendas archivés" }),
  ).toBeVisible();
  await expect(
    dgAgenda.page.getByRole("link", { name: "Ouvrir le PDF" }).first(),
  ).toBeVisible();
  await capture(dgAgenda.page, "16-agenda-archives-dg.png");
  await dgAgenda.context.close();

  const rh = await desktop(browser, "rh");
  await rh.page.goto(site("/app/absences"));
  await expect(
    rh.page.getByRole("heading", { name: "Absences et missions" }),
  ).toBeVisible();
  await capture(rh.page, "17-absences-rh.png");
  await rh.context.close();

  const dev = await desktop(browser, "dev", adminPassword);
  await dev.page.goto(site("/admin/accounts/user/add/"));
  await expect(
    dev.page.locator('select[name="organization_units"]'),
  ).toBeVisible();
  await expect(dev.page.locator('select[name="primary_unit"]')).toBeVisible();
  await expect(
    dev.page.locator('select[name="primary_supervisor"]'),
  ).toBeVisible();
  await expect(
    dev.page.locator('select[name="agenda_direction"]'),
  ).toBeVisible();
  await expect(
    dev.page.locator('input[name="include_in_direction_agendas"]'),
  ).toBeVisible();
  await capture(dev.page, "18-administration-personne-organigramme.png");
  await dev.page.goto(site("/admin/work/organizationunit/add/"));
  await expect(dev.page.locator('select[name="parent_unit"]')).toBeVisible();
  await expect(dev.page.locator('select[name="child_units"]')).toBeVisible();
  await capture(dev.page, "19-administration-unite.png");
  await dev.page.goto(site("/admin/access/rolegrant/"));
  await expect(dev.page.locator("#result_list")).toBeVisible();
  await capture(dev.page, "20-administration-delegations.png");
  await dev.context.close();
});
