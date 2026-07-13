import shutil
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from django.utils.crypto import get_random_string

from accounts.models import User
from work.models import (
    ActionPlan,
    InstitutionalAction,
    OrganizationUnit,
    ProgressEntry,
    ReportingLine,
    StrategicPlan,
    Task,
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
            start_date=personal_start,
            due_date=calendar.due_date_for(personal_start, Decimal("2.00")),
            estimated_work_days=Decimal("2.00"),
            calendar=calendar,
            status="active",
        )
        ProgressEntry.objects.create(
            assignment=self.assignment,
            entry_date=timezone.localdate(),
            percentage=60,
            author=self.user,
        )
        member = User.objects.create_user("member@example.test")
        unit = OrganizationUnit.objects.create(code="BROWSER", name="Equipe navigateur")
        ReportingLine.objects.create(
            employee=member,
            supervisor=self.user,
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
            start_date=team_start,
            due_date=calendar.due_date_for(team_start, Decimal("5.00")),
            estimated_work_days=Decimal("5.00"),
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
                EC.presence_of_element_located((By.CSS_SELECTOR, ".workload-chart svg"))
            )
            driver.get(f"{self.live_server_url}/equipe/")
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".task-profile-chart svg")
                )
            )
            assert driver.find_element(By.CSS_SELECTOR, ".chart-overrun-zone")
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
            slider = driver.find_element(By.CSS_SELECTOR, "[data-progress]")
            driver.execute_script(
                "arguments[0].value=40; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
                slider,
            )
            form = driver.find_element(By.CSS_SELECTOR, ".progress-form")
            assert "progress-regression" in form.get_attribute("class")
            assert "réduite de 20 points" in driver.page_source
            assert driver.find_element(By.NAME, "note").get_attribute("required")
        finally:
            driver.quit()
