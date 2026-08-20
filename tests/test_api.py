from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from api.exceptions import api_exception_handler
from work.models import ProgressEntry, Task, TaskAssignment, TaskProposal


pytestmark = pytest.mark.django_db


def api_client(user: User) -> Client:
    """Return a session-authenticated Django test client."""
    client = Client()
    client.force_login(user)
    return client


def proposal_for_assignment(assignment: TaskAssignment) -> TaskProposal:
    return TaskProposal.objects.create(
        employee=assignment.employee,
        organization_unit=assignment.organization_unit,
        title="Formaliser le tableau de priorités",
        description="Préparer une version arbitrée.",
        action=assignment.task.action,
        calendar=assignment.calendar,
        start_date=assignment.start_date,
        due_date=assignment.due_date,
        estimated_work_days=assignment.estimated_work_days,
    )


def test_api_rejects_anonymous_sessions() -> None:
    response = Client().get(reverse("api:session"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_unexpected_api_errors_keep_the_json_contract() -> None:
    response = api_exception_handler(RuntimeError("private detail"), {})

    assert response.status_code == 500
    assert response.data == {
        "error": {
            "code": "server_error",
            "message": "Le serveur n'a pas pu traiter cette demande.",
            "fields": {},
        }
    }


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


def test_team_count_matches_multiple_tasks_in_employee_profile(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    second_task = Task.objects.create(
        code="TSK-TEST-2",
        title="Vérifier le second prototype",
        description="Seconde tâche fictive.",
        action=assignment.task.action,
        created_by=people["manager"],
    )
    TaskAssignment.objects.create(
        task=second_task,
        employee=assignment.employee,
        manager=assignment.manager,
        organization_unit=assignment.organization_unit,
        calendar=assignment.calendar,
        start_date=assignment.start_date,
        due_date=assignment.due_date,
        estimated_work_days=assignment.estimated_work_days,
        status="active",
    )
    client = api_client(people["manager"])
    period = {"week": assignment.start_date.isoformat()}

    team = client.get(reverse("api:team"), period)
    profile = client.get(
        reverse("api:team-employee", args=[assignment.employee_id]), period
    )

    assert team.status_code == 200
    employee_node = next(
        node
        for node in team.json()["nodes"]
        if node["employee"]["id"] == assignment.employee_id
    )
    assert employee_node["task_count"] == 2
    assert profile.status_code == 200
    assert len(profile.json()["tasks"]) == 2


def test_user_can_read_and_update_own_terms_of_reference(people: dict[str, User]) -> None:
    employee_client = api_client(people["employee"])
    endpoint = reverse("api:me-profile")
    expected = "Cahier des charges aligné sur la période."

    response = employee_client.get(endpoint)
    assert response.status_code == 200
    assert response.json()["id"] == people["employee"].pk
    assert response.json()["terms_of_reference"] == people["employee"].terms_of_reference

    saved = employee_client.patch(
        endpoint,
        {"terms_of_reference": expected},
        content_type="application/json",
    )

    assert saved.status_code == 200
    assert saved.json()["terms_of_reference"] == expected
    assert User.objects.get(pk=people["employee"].pk).terms_of_reference == expected


def test_supervisor_can_read_profile_data_from_team_employee(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    employee = assignment.employee
    employee.first_name = "Mariam"
    employee.last_name = "Dia"
    employee.phone = "+225 01 02 03 04 05"
    employee.terms_of_reference = "Piloter les arbitrages de la feuille de route."
    employee.save(
        update_fields=["first_name", "last_name", "phone", "terms_of_reference"]
    )

    response = api_client(people["manager"]).get(
        reverse("api:team-employee", args=[employee.pk]),
        {"month": assignment.start_date.strftime("%Y-%m")},
    )
    payload = response.json()
    employee_payload = payload["employee"]

    assert response.status_code == 200
    assert employee_payload["id"] == employee.pk
    assert employee_payload["first_name"] == "Mariam"
    assert employee_payload["last_name"] == "Dia"
    assert employee_payload["email"] == employee.email
    assert employee_payload["phone"] == "+225 01 02 03 04 05"
    assert (
        employee_payload["terms_of_reference"]
        == "Piloter les arbitrages de la feuille de route."
    )


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
    estimated_work_days = Decimal("1.625")
    due = calendar.due_date_for(start, estimated_work_days)

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
            "estimated_work_days": str(estimated_work_days),
        },
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["action"] is None
    assert response.json()["estimated_work_days"] == "1.625"
    assert TaskAssignment.objects.get(pk=response.json()["id"]).estimated_work_days == (
        estimated_work_days
    )


def test_manager_accepts_a_proposal_and_receives_the_assignment_link(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    proposal = proposal_for_assignment(assignment)
    response = api_client(people["manager"]).post(
        reverse("api:proposal-decision", args=[proposal.pk]),
        {"revision": proposal.revision, "decision": "accept", "reason": ""},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["accepted_assignment_id"] is not None
    assert payload["capabilities"] == {
        "edit": False,
        "resubmit": False,
        "review": False,
    }


def test_author_corrects_and_resubmits_a_rejected_proposal(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    proposal = proposal_for_assignment(assignment)
    rejected = api_client(people["manager"]).post(
        reverse("api:proposal-decision", args=[proposal.pk]),
        {
            "revision": proposal.revision,
            "decision": "reject",
            "reason": "Préciser le résultat attendu.",
        },
        content_type="application/json",
    )
    employee = api_client(people["employee"])
    corrected = employee.patch(
        reverse("api:proposal-detail", args=[proposal.pk]),
        {
            "revision": rejected.json()["revision"],
            "title": "Formaliser les priorités arbitrées",
            "description": "Préparer le tableau et sa note de synthèse.",
            "action_id": assignment.task.action_id,
            "calendar_id": assignment.calendar_id,
            "start_date": assignment.start_date.isoformat(),
            "due_date": assignment.due_date.isoformat(),
            "estimated_work_days": str(assignment.estimated_work_days),
        },
        content_type="application/json",
    )
    resubmitted = employee.post(
        reverse("api:proposal-resubmit", args=[proposal.pk]),
        {"revision": corrected.json()["revision"]},
        content_type="application/json",
    )

    assert rejected.status_code == 200
    assert corrected.status_code == 200
    assert corrected.json()["status"] == "rejected"
    assert corrected.json()["decision_note"] == "Préciser le résultat attendu."
    assert resubmitted.status_code == 200
    assert resubmitted.json()["status"] == "submitted"
    assert resubmitted.json()["decision_note"] == ""
    assert resubmitted.json()["capabilities"]["edit"] is True


def test_proposal_detail_hides_itself_from_an_outsider(
    people: dict[str, User], assignment: TaskAssignment
) -> None:
    proposal = proposal_for_assignment(assignment)
    response = api_client(people["outsider"]).get(
        reverse("api:proposal-detail", args=[proposal.pk])
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


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
