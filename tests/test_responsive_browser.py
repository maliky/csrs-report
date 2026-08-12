import shutil
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from django.utils.crypto import get_random_string

from accounts.models import User
from work.models import (
    ActionPlan,
    ActivityKind,
    InstitutionalAction,
    OrganizationUnit,
    ProgressEntry,
    ReportingLine,
    StrategicPlan,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskProposal,
    WorkCalendar,
    default_work_calendar_id,
)


@pytest.mark.selenium
@pytest.mark.skipif(
    shutil.which("chromedriver") is None,
    reason="chromedriver systeme indisponible",
)
class ResponsiveSmokeTest(StaticLiveServerTestCase):
    def setUp(self) -> None:
        self.password = f"Browser9!{get_random_string(18)}"
        self.user = User.objects.create_user(
            "browser@example.test",
            self.password,
            login_alias="browser",
        )
        unit = OrganizationUnit.objects.create(
            code="BROWSER",
            short_name="Equipe navigateur",
            long_name="Equipe utilisee par la verification navigateur",
        )
        plan = StrategicPlan.objects.create(
            name="Plan navigateur",
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=365),
        )
        action_plan = ActionPlan.objects.create(
            strategic_plan=plan, name="Actions navigateur", code="PA-BROWSER"
        )
        action = InstitutionalAction.objects.create(
            action_plan=action_plan, name="Action navigateur", code="ACT-BROWSER"
        )
        calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
        personal_start = timezone.localdate() - timedelta(days=14)
        task = Task.objects.create(
            code="BROWSER-01",
            title="Verifier la progression",
            description="Controle navigateur",
            action=action,
            created_by=self.user,
        )
        self.assignment = TaskAssignment.objects.create(
            task=task,
            employee=self.user,
            manager=self.user,
            organization_unit=unit,
            start_date=personal_start,
            due_date=calendar.due_date_for(personal_start, Decimal("2.0")),
            estimated_work_days=Decimal("2.0"),
            calendar=calendar,
            status="active",
        )
        ProgressEntry.objects.create(
            assignment=self.assignment,
            entry_date=timezone.localdate(),
            percentage=60,
            author=self.user,
        )
        closed_task = Task.objects.create(
            code="BROWSER-CLOSED",
            title="Clore une action avant l’échéance",
            description="Contrôle de la fin du graphique",
            action=action,
            created_by=self.user,
        )
        closed_day = timezone.localdate() - timedelta(days=7)
        closed_start = closed_day - timedelta(days=3)
        self.closed_assignment = TaskAssignment.objects.create(
            task=closed_task,
            employee=self.user,
            manager=self.user,
            organization_unit=unit,
            start_date=closed_start,
            due_date=calendar.due_date_for(closed_start, Decimal("20.0")),
            estimated_work_days=Decimal("20.0"),
            calendar=calendar,
            status="completed",
            completed_at=timezone.now() - timedelta(days=7),
        )
        ProgressEntry.objects.create(
            assignment=self.closed_assignment,
            entry_date=closed_day,
            percentage=100,
            author=self.user,
        )
        TaskActivity.objects.create(
            assignment=self.assignment,
            actor=self.user,
            kind=ActivityKind.PROGRESS,
            message="Controle de la mise en page du fil.",
            percentage_after=60,
        )
        member = User.objects.create_user("member@example.test")
        self.member = member
        ReportingLine.objects.create(
            employee=member,
            supervisor=self.user,
            unit=unit,
            start_date=timezone.localdate(),
            is_primary=True,
        )
        proposal_start = timezone.localdate()
        while not calendar.is_working_day(proposal_start):
            proposal_start += timedelta(days=1)
        self.proposal = TaskProposal.objects.create(
            employee=member,
            organization_unit=unit,
            title="Formaliser le tableau de priorités",
            description="Préparer une version arbitrée des engagements.",
            action=action,
            calendar=calendar,
            start_date=proposal_start,
            due_date=calendar.due_date_for(proposal_start, Decimal("3.0")),
            estimated_work_days=Decimal("3.0"),
        )
        subordinate = User.objects.create_user("subordinate@example.test")
        self.subordinate = subordinate
        ReportingLine.objects.create(
            employee=subordinate,
            supervisor=member,
            unit=unit,
            start_date=timezone.localdate(),
            is_primary=True,
        )
        team_task = Task.objects.create(
            code="BROWSER-TEAM",
            title="Consolider le dossier",
            description="Suivi equipe",
            action=action,
            created_by=self.user,
        )
        team_start = timezone.localdate() - timedelta(days=14)
        team_assignment = TaskAssignment.objects.create(
            task=team_task,
            employee=member,
            manager=self.user,
            organization_unit=unit,
            start_date=team_start,
            due_date=calendar.due_date_for(team_start, Decimal("5.0")),
            estimated_work_days=Decimal("5.0"),
            calendar=calendar,
            status="active",
        )
        self.team_assignment = team_assignment
        ProgressEntry.objects.create(
            assignment=team_assignment,
            entry_date=timezone.localdate(),
            percentage=40,
            author=member,
        )

    def test_login_page_at_phone_and_desktop_widths(self) -> None:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
        try:
            for width in (390, 1280):
                driver.set_window_size(width, 800)
                driver.get(f"{self.live_server_url}/connexion/")
                assert "Connexion" in driver.page_source
                assert (
                    driver.execute_script("return document.documentElement.scrollWidth")
                    <= width
                )
            driver.find_element(By.NAME, "username").send_keys("BROWSER")
            driver.find_element(By.NAME, "password").send_keys(self.password)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            WebDriverWait(driver, 10).until(EC.url_to_be(f"{self.live_server_url}/app/"))
            WebDriverWait(driver, 10).until(
                EC.text_to_be_present_in_element((By.TAG_NAME, "h1"), "Mes tâches")
            )
            assert "Mes tâches" in driver.page_source
            driver.get(f"{self.live_server_url}/classique/")
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".task-card-history-chart svg")
                )
            )
            assert not driver.find_elements(By.LINK_TEXT, "Observable")
            driver.get(f"{self.live_server_url}/taches/nouvelle/")
            start_input = driver.find_element(By.NAME, "start_date")
            due_input = driver.find_element(By.NAME, "due_date")
            workload_input = driver.find_element(By.NAME, "estimated_work_days")
            action_input = driver.find_element(By.NAME, "action")
            assert start_input.get_attribute("type") == "text"
            assert len(start_input.get_attribute("value").split("/")) == 3
            assert workload_input.get_attribute("value") == "5"
            assert not action_input.get_attribute("required")
            workload_input.clear()
            workload_input.send_keys("2.5")
            assert len(due_input.get_attribute("value").split("/")) == 3
            driver.get(f"{self.live_server_url}/equipe/")
            assert not driver.find_elements(By.CSS_SELECTOR, "details[open]")
            assert not driver.find_elements(By.CSS_SELECTOR, ".task-profile-chart svg")
            top_branch = driver.find_element(By.CSS_SELECTOR, ".team-tree > .team-branch")
            top_branch.find_element(By.CSS_SELECTOR, ":scope > summary").click()
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".task-profile-chart.workload-chart svg")
                )
            )
            assert not driver.find_elements(By.LINK_TEXT, "Voir toutes les tâches")
            assert "Reste cumulé" not in driver.page_source
            assert driver.find_element(
                By.CSS_SELECTOR, ".team-tree > .team-branch .subteam"
            ).get_attribute("open")
            child_branch = driver.find_element(
                By.CSS_SELECTOR, ".team-tree > .team-branch .team-branch"
            )
            assert not child_branch.get_attribute("open")
            child_branch.find_element(By.CSS_SELECTOR, ":scope > summary").click()
            assert child_branch.get_attribute("open")
            top_branch.find_element(By.CSS_SELECTOR, ":scope > summary").click()
            WebDriverWait(driver, 5).until(
                lambda _driver: not child_branch.get_attribute("open")
            )
            top_branch.find_element(By.CSS_SELECTOR, ":scope > summary").click()
            assert driver.find_element(
                By.CSS_SELECTOR, ".team-tree > .team-branch .subteam"
            ).get_attribute("open")
            assert not child_branch.get_attribute("open")
            assert driver.find_element(
                By.CSS_SELECTOR, ".task-profile-chart .workload-completed"
            )
            toggle = driver.find_element(By.CSS_SELECTOR, ".task-profile-toggle")
            toggle.click()
            assert toggle.get_attribute("aria-expanded") == "true"
            assert "Ouvrir la tâche" in driver.page_source
            driver.get(
                f"{self.live_server_url}/classique/?month={timezone.localdate():%Y-%m}"
            )
            assert driver.find_element(By.CSS_SELECTOR, ".period-nav-month")
            driver.get(f"{self.live_server_url}/taches/{self.assignment.pk}/")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".task-history-chart svg")
                )
            )
            assert driver.find_element(
                By.CSS_SELECTOR, ".task-history-chart .chart-due-line"
            )
            assert driver.find_element(
                By.CSS_SELECTOR, ".task-history-chart .chart-start-line"
            )
            assert driver.find_element(
                By.CSS_SELECTOR, ".task-history-chart .chart-today-line"
            )
            marker_labels = {
                label.get_attribute("textContent").split()[0]
                for label in driver.find_elements(
                    By.CSS_SELECTOR, ".task-history-chart .chart-marker-label"
                )
            }
            assert marker_labels == {"Début", "Aujourd’hui", "Fin"}
            assert driver.find_element(By.CSS_SELECTOR, ".chart-overrun-zone")
            pointer_layer = driver.find_element(
                By.CSS_SELECTOR, ".task-history-chart .chart-pointer-layer"
            )
            ActionChains(driver).move_to_element(pointer_layer).perform()
            tooltip = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, "body > .progress-chart-tooltip")
                )
            )
            assert tooltip.value_of_css_property("position") == "fixed"
            assert int(tooltip.value_of_css_property("z-index")) >= 10000
            slider = driver.find_element(By.CSS_SELECTOR, "[data-progress]")
            driver.execute_script(
                "arguments[0].value=40; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
                slider,
            )
            form = driver.find_element(By.CSS_SELECTOR, ".progress-form")
            assert "progress-regression" in form.get_attribute("class")
            assert "réduite de 20 points" in driver.page_source
            assert driver.find_element(By.NAME, "note").get_attribute("required")
            activity = driver.find_element(By.CSS_SELECTOR, ".comments .activity")
            assert activity.value_of_css_property("flex-direction") == "row"
            driver.set_window_size(390, 800)
            assert activity.value_of_css_property("flex-direction") == "column"
            driver.get(f"{self.live_server_url}/taches/{self.closed_assignment.pk}/")
            closed_chart = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".task-history-chart[data-chart-end]")
                )
            )
            assert closed_chart.get_attribute("data-chart-end") == str(
                self.closed_assignment.completed_at.date()
            )
            assert not driver.find_elements(
                By.CSS_SELECTOR, ".task-history-chart .chart-today-line"
            )
            assert not driver.find_elements(
                By.CSS_SELECTOR, ".task-history-chart .chart-due-line"
            )
        finally:
            driver.quit()

    @pytest.mark.skipif(
        not Path("static/react/assets/app.js").exists(),
        reason="compiler le frontend React avant le controle navigateur",
    )
    def test_react_dashboard_and_task_at_phone_and_desktop_widths(self) -> None:
        """Exercise the production React bundle against Django's real API."""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
        try:
            driver.get(f"{self.live_server_url}/connexion/")
            driver.find_element(By.NAME, "username").send_keys("BROWSER")
            driver.find_element(By.NAME, "password").send_keys(self.password)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            WebDriverWait(driver, 10).until(EC.url_to_be(f"{self.live_server_url}/app/"))
            for width in (360, 1440):
                driver.set_window_size(width, 900)
                driver.get(
                    f"{self.live_server_url}/app/?month={timezone.localdate():%Y-%m}"
                )
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
                assert "Mes tâches" in driver.page_source
                assert (
                    driver.execute_script("return document.documentElement.scrollWidth")
                    <= width
                )
                if width == 360:
                    open_menu = driver.find_element(
                        By.CSS_SELECTOR, "button[aria-label='Ouvrir le menu']"
                    )
                    open_menu.click()
                    sidebar = WebDriverWait(driver, 5).until(
                        EC.visibility_of_element_located(
                            (By.CSS_SELECTOR, "aside[aria-label='Navigation principale']")
                        )
                    )
                    WebDriverWait(driver, 5).until(
                        lambda _driver, menu=sidebar: menu.rect["x"] >= 0
                    )
                    driver.find_element(
                        By.CSS_SELECTOR,
                        "aside button[aria-label='Fermer le menu']",
                    ).click()
                    WebDriverWait(driver, 5).until(EC.invisibility_of_element(sidebar))
                else:
                    driver.find_element(
                        By.CSS_SELECTOR, "button[aria-label='Réduire le menu']"
                    ).click()
                    assert driver.find_element(
                        By.CSS_SELECTOR, "button[aria-label='Déployer le menu']"
                    )
                axe_source = Path("frontend/node_modules/axe-core/axe.min.js").read_text()
                driver.execute_script(axe_source)
                audit = driver.execute_async_script(
                    """
                    const done = arguments[arguments.length - 1];
                    axe.run(document, {
                      runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}
                    }).then(done);
                    """
                )
                serious = [
                    item
                    for item in audit["violations"]
                    if item["impact"] in ("serious", "critical")
                ]
                assert not serious, serious
            driver.set_window_size(360, 900)
            driver.get(f"{self.live_server_url}/app/equipe/?week={timezone.localdate()}")
            WebDriverWait(driver, 10).until(
                EC.text_to_be_present_in_element(
                    (By.TAG_NAME, "h1"), "Synthèse de l'équipe"
                )
            )
            assert "Voir la progression" not in driver.page_source
            member_branch = driver.find_element(
                By.CSS_SELECTOR,
                f"details[data-team-employee-id='{self.member.pk}']",
            )
            member_summary = member_branch.find_element(
                By.CSS_SELECTOR, ":scope > summary"
            )
            assert member_summary.rect["height"] >= 44
            assert member_branch.get_attribute("open") is not None
            subordinate_branch = driver.find_element(
                By.CSS_SELECTOR,
                f"details[data-team-employee-id='{self.subordinate.pk}']",
            )
            assert subordinate_branch.get_attribute("open") is None
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        f"[data-team-task-id='{self.team_assignment.pk}']",
                    )
                )
            )
            assert driver.find_element(
                By.CSS_SELECTOR,
                f"a[href='/app/taches/{self.team_assignment.pk}']",
            )
            driver.find_element(
                By.CSS_SELECTOR, "button[data-task-filter='with']"
            ).click()
            assert driver.find_elements(
                By.CSS_SELECTOR,
                f"details[data-team-employee-id='{self.member.pk}']",
            )
            assert not driver.find_elements(
                By.CSS_SELECTOR,
                f"details[data-team-employee-id='{self.subordinate.pk}']",
            )
            driver.find_element(
                By.CSS_SELECTOR, "button[data-task-filter='without']"
            ).click()
            assert driver.find_elements(
                By.CSS_SELECTOR,
                f"details[data-team-employee-id='{self.member.pk}']",
            )
            assert driver.find_elements(
                By.CSS_SELECTOR,
                f"details[data-team-employee-id='{self.subordinate.pk}']",
            )
            assert (
                driver.execute_script("return document.documentElement.scrollWidth")
                <= 360
            )
            driver.set_window_size(1440, 900)
            driver.get(f"{self.live_server_url}/app/taches/{self.assignment.pk}/")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "svg[role='img']"))
            )
            assert "Date de début" in driver.page_source
            assert "Fin prévue" in driver.page_source
            assert f"Aujourd'hui {timezone.localdate():%d/%m/%Y}" in driver.page_source
            assert f"Fin prévue {self.assignment.due_date:%d/%m/%Y}" in driver.page_source
            chart = driver.find_element(By.CSS_SELECTOR, "svg[role='img']")
            ActionChains(driver).move_to_element(chart).perform()
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "[role='status']"))
            )
            slider = driver.find_element(By.CSS_SELECTOR, "input[type='range']")
            slider.click()
            slider.send_keys(Keys.HOME)
            slider.send_keys(*([Keys.ARROW_RIGHT] * 8))
            assert slider.get_attribute("value") == "40"
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//*[contains(., 'Aperçu non enregistré : 40 %')]")
                )
            )
            note = driver.find_element(By.ID, "progress-note")
            assert note.get_attribute("required")
            note.send_keys("Contrôle complémentaire nécessaire.")
            save_button = driver.find_element(
                By.XPATH, "//button[normalize-space()='Enregistrer la progression']"
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", save_button
            )
            driver.execute_script("arguments[0].click();", save_button)
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//*[contains(., 'Progression enregistrée à 40 %.')]")
                )
            )
            assert (
                self.assignment.progress_entries.get(
                    entry_date=timezone.localdate()
                ).percentage
                == 40
            )
            assert "Contrôle complémentaire nécessaire." in driver.page_source
            assert "Aperçu non enregistré" not in driver.page_source
            driver.set_window_size(360, 900)
            driver.get(f"{self.live_server_url}/app/propositions")
            proposal_link = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        f"a[href='/app/propositions/{self.proposal.pk}']",
                    )
                )
            )
            card = proposal_link.find_element(By.XPATH, "ancestor::section[1]")
            validate = card.find_element(
                By.XPATH, ".//button[normalize-space()='Valider']"
            )
            card_box = card.rect
            button_box = validate.rect
            assert button_box["x"] >= card_box["x"]
            assert button_box["x"] + button_box["width"] <= (
                card_box["x"] + card_box["width"]
            )
            driver.execute_script("arguments[0].click();", validate)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//*[normalize-space()='Validée']")
                    )
                )
            except TimeoutException as error:
                self.proposal.refresh_from_db()
                banners = [
                    item.text
                    for item in driver.find_elements(By.CSS_SELECTOR, "[role='alert']")
                ]
                raise AssertionError(
                    f"status={self.proposal.status}; erreurs={banners}"
                ) from error
            self.proposal.refresh_from_db()
            assert self.proposal.status == "accepted"
            assert self.proposal.accepted_assignment_id is not None
            accepted_link = driver.find_element(
                By.CSS_SELECTOR,
                f"a[aria-label='Ouvrir {self.proposal.title}']",
            )
            assert accepted_link.get_attribute("href").endswith(
                f"/app/taches/{self.proposal.accepted_assignment_id}"
            )
            assert (
                driver.execute_script("return document.documentElement.scrollWidth")
                <= 360
            )
        finally:
            driver.quit()
