from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from work.models import ProgressEntry, TaskAssignment


pytestmark = pytest.mark.django_db


def api_client(user: User) -> Client:
    """Return a session-authenticated Django test client."""
    client = Client()
    client.force_login(user)
    return client


def test_api_rejects_anonymous_sessions() -> None:
    response = Client().get(reverse("api:session"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_session_and_dashboard_expose_current_user_and_period(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    client = api_client(people["employee"])

    session = client.get(reverse("api:session"))
    dashboard = client.get(reverse("api:dashboard"), {"month": "2026-07"})

    assert session.status_code == 200
    assert session.json()["user"]["id"] == people["employee"].pk
    assert session.cookies["csrftoken"]
    assert dashboard.status_code == 200
    assert dashboard.json()["period"]["kind"] == "month"


def test_task_detail_hides_an_assignment_from_an_outsider(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    response = api_client(people["outsider"]).get(
        reverse("api:task-detail", args=[assignment.pk])
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_progress_update_increments_revision_and_rejects_stale_write(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    client = api_client(people["employee"])
    endpoint = reverse("api:task-progress", args=[assignment.pk])
    payload = {
        "revision": 1,
        "entry_date": timezone.localdate().isoformat(),
        "percentage": 25,
        "note": "Premier livrable transmis.",
        "blocked": False,
    }

    saved = client.post(endpoint, payload, content_type="application/json")
    stale = client.post(endpoint, payload, content_type="application/json")

    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert ProgressEntry.objects.get(assignment=assignment).percentage == 25
    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "stale_revision",
        "message": "Cette ressource a été modifiée depuis son chargement.",
        "fields": {"revision": ["2"]},
    }


def test_progress_regression_requires_note_and_returns_updated_chart(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    client = api_client(people["employee"])
    endpoint = reverse("api:task-progress", args=[assignment.pk])
    today = timezone.localdate().isoformat()
    first = client.post(
        endpoint,
        {
            "revision": assignment.revision,
            "entry_date": today,
            "percentage": 50,
            "note": "Premier état contrôlé.",
            "blocked": False,
        },
        content_type="application/json",
    )
    rejected = client.post(
        endpoint,
        {
            "revision": first.json()["revision"],
            "entry_date": today,
            "percentage": 40,
            "note": "",
            "blocked": False,
        },
        content_type="application/json",
    )
    saved = client.post(
        endpoint,
        {
            "revision": first.json()["revision"],
            "entry_date": today,
            "percentage": 40,
            "note": "Contrôle complémentaire nécessaire.",
            "blocked": False,
        },
        content_type="application/json",
    )

    assert rejected.status_code == 400
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["percentage"] == 40
    assert payload["chart"][-1]["day"] == today
    assert payload["chart"][-1]["percentage"] == 40
    assert payload["chart"][-1]["observed"] is True
    assert payload["activities"][0]["message"] == ("Contrôle complémentaire nécessaire.")


def test_manager_can_create_an_unclassified_task(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    client = api_client(people["manager"])
    calendar = assignment.calendar
    start = timezone.localdate() + timedelta(days=1)
    while not calendar.is_working_day(start):
        start += timedelta(days=1)
    due = calendar.due_date_for(start, assignment.estimated_work_days)

    response = client.post(
        reverse("api:task-create"),
        {
            "title": "Préparer la synthèse",
            "description": "Consolider les contributions des services.",
            "employee_id": people["employee"].pk,
            "action_id": None,
            "calendar_id": calendar.pk,
            "start_date": start.isoformat(),
            "due_date": due.isoformat(),
            "estimated_work_days": "5",
        },
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["action"] is None
    assert response.json()["estimated_work_days"] == "5"


def test_task_creation_validates_authorization_on_the_server(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    response = api_client(people["outsider"]).post(
        reverse("api:task-create"),
        {
            "title": "Tâche interdite",
            "description": "Cette affectation ne doit pas être créée.",
            "employee_id": people["employee"].pk,
            "calendar_id": assignment.calendar_id,
            "start_date": assignment.start_date.isoformat(),
            "due_date": assignment.due_date.isoformat(),
            "estimated_work_days": str(assignment.estimated_work_days),
        },
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_unsafe_api_calls_require_the_csrf_token(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(people["employee"])
    session = client.get(reverse("api:session"))
    endpoint = reverse("api:task-observation", args=[assignment.pk])
    payload = {"revision": assignment.revision, "message": "Point partagé."}

    rejected = client.post(endpoint, payload, content_type="application/json")
    accepted = client.post(
        endpoint,
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=session.json()["csrf_token"],
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json()["revision"] == assignment.revision + 1
