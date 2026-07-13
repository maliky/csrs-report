"""Behavior and security tests for the aggregate Observable export."""

from decimal import Decimal

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from work.models import (
    InstitutionalAction,
    ReportingLine,
    Task,
    TaskAssignment,
    WorkCalendar,
    default_work_calendar_id,
)
from work.observable import create_export_token


def create_assignment(
    *,
    code: str,
    employee: User,
    manager: User,
    action: InstitutionalAction,
    workload: Decimal = Decimal("2.00"),
) -> TaskAssignment:
    """Create a coherent assignment for export permission tests."""
    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    start = timezone.localdate()
    task = Task.objects.create(
        code=code,
        title=f"Tache {code}",
        description=f"Description privee {code}",
        action=action,
        created_by=manager,
    )
    return TaskAssignment.objects.create(
        task=task,
        employee=employee,
        manager=manager,
        calendar=calendar,
        start_date=start,
        due_date=calendar.due_date_for(start, workload),
        estimated_work_days=workload,
        status="active",
    )


@pytest.mark.django_db
def test_observable_page_requires_login_and_provides_copy_ready_code(
    client, people: dict[str, User]
) -> None:
    url = reverse("observable-export")
    assert client.get(url).status_code == 302

    client.force_login(people["manager"])
    response = client.get(url)
    content = response.content.decode()

    assert response.status_code == 200
    assert "Un export pour toutes les tâches visibles" in content
    assert reverse("observable-progress-export") in content
    assert "Authorization" in content
    assert "csrs.tasks" in content
    assert "csrs.progress" in content
    assert "?token=" not in content


@pytest.mark.django_db
def test_observable_preflight_allows_noncredentialed_authorization(client) -> None:
    response = client.options(
        reverse("observable-progress-export"),
        HTTP_ORIGIN="https://observablehq.com",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization",
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
    assert response.headers["Access-Control-Allow-Methods"] == "GET, OPTIONS"


@pytest.mark.django_db
def test_observable_export_contains_all_and_only_visible_tasks(
    client,
    assignment: TaskAssignment,
    people: dict[str, User],
    action: InstitutionalAction,
) -> None:
    today = timezone.localdate()
    assignment.progress_entries.create(
        entry_date=today,
        percentage=35,
        note="Cette note ne doit jamais sortir.",
        author=people["employee"],
    )
    manager_assignment = create_assignment(
        code="OBS-MANAGER",
        employee=people["manager"],
        manager=people["manager"],
        action=action,
    )
    outsider_assignment = create_assignment(
        code="OBS-OUTSIDE",
        employee=people["outsider"],
        manager=people["outsider"],
        action=action,
    )
    token = create_export_token(people["manager"])

    response = client.get(
        reverse("observable-progress-export"),
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_ORIGIN="https://observablehq.com",
    )
    payload = response.json()

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["Cache-Control"] == "no-store"
    assert payload["schema_version"] == 1
    assert payload["task_count"] == 2
    assert {task["task_id"] for task in payload["tasks"]} == {
        assignment.pk,
        manager_assignment.pk,
    }
    assert outsider_assignment.pk not in {task["task_id"] for task in payload["tasks"]}
    assert set(payload["progress"][0]) == {
        "task_id",
        "start_date",
        "day",
        "due_date",
        "planned_work_days",
        "elapsed_work_days",
        "remaining_schedule_days",
        "overdue_days",
        "percentage",
        "observed",
    }
    observed = [
        row
        for row in payload["progress"]
        if row["task_id"] == assignment.pk and row["observed"]
    ]
    assert [(row["day"], row["percentage"]) for row in observed] == [
        (today.isoformat(), 35)
    ]
    serialized = response.content.decode()
    for private_value in (
        "Cette note ne doit jamais sortir.",
        "Description privee",
        people["employee"].email,
        people["employee"].first_name,
    ):
        assert private_value not in serialized


@pytest.mark.django_db
def test_observable_token_rechecks_current_hierarchy(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    token = create_export_token(people["manager"])
    line = ReportingLine.objects.get(
        supervisor=people["manager"], employee=people["employee"], is_primary=True
    )
    line.delete()

    response = client.get(
        reverse("observable-progress-export"),
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert assignment.pk not in {task["task_id"] for task in response.json()["tasks"]}


@pytest.mark.django_db
def test_observable_export_rejects_missing_invalid_expired_and_inactive_tokens(
    client, people: dict[str, User]
) -> None:
    url = reverse("observable-progress-export")
    for authorization in (None, "Bearer incorrect"):
        headers = (
            {"HTTP_AUTHORIZATION": authorization} if authorization is not None else {}
        )
        response = client.get(url, **headers)
        assert response.status_code == 401
        assert response.headers["Access-Control-Allow-Origin"] == "*"

    token = create_export_token(people["manager"])
    with override_settings(OBSERVABLE_EXPORT_TOKEN_MAX_AGE_SECONDS=-1):
        assert client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 401

    fresh_token = create_export_token(people["manager"])
    people["manager"].is_active = False
    people["manager"].save(update_fields=["is_active"])
    assert client.get(url, HTTP_AUTHORIZATION=f"Bearer {fresh_token}").status_code == 401
