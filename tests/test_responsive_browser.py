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
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
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
        ReportingLine.objects.create(
            employee=member,
            supervisor=self.user,
            unit=unit,
            start_date=timezone.localdate(),
            is_primary=True,
        )
        subordinate = User.objects.create_user("subordinate@example.test")
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
            assert driver.current_url == f"{self.live_server_url}/"
            assert "Mes tâches" in driver.page_source
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
            driver.get(f"{self.live_server_url}/?month={timezone.localdate():%Y-%m}")
            assert driver.find_element(By.CSS_SELECTOR, ".period-nav-month")
            driver.get(f"{self.live_server_url}/taches/{self.assignment.pk}/")
            WebDriverWait(driver, 5).until(
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
            driver.get(
                f"{self.live_server_url}/taches/{self.closed_assignment.pk}/"
            )
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
            driver.get(
                f"{self.live_server_url}/app/taches/{self.assignment.pk}/"
            )
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "svg[role='img']"))
            )
            assert "Date de début" in driver.page_source
            assert "Date du jour" in driver.page_source
            assert "Fin prévue" in driver.page_source
            observed = driver.find_element(By.CSS_SELECTOR, "circle[role='button']")
            ActionChains(driver).move_to_element(observed).perform()
            WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "[role='status']"))
            )
        finally:
            driver.quit()
