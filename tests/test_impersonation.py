import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import User
from access.models import RoleSimulation, RoleSimulationAction
from work.models import ProgressEntry, TaskAssignment


pytestmark = pytest.mark.django_db


def api_client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def test_only_superusers_can_start_role_simulation(people) -> None:
    client = api_client(people["manager"])

    assert client.get("/api/v1/session/impersonation/options/").status_code == 403
    assert (
        client.post(
            "/api/v1/session/impersonation/",
            {"user_id": people["employee"].pk},
            content_type="application/json",
        ).status_code
        == 403
    )


def test_superuser_acts_with_target_permissions_and_keeps_audit(
    people, assignment: TaskAssignment
) -> None:
    administrator = User.objects.create_superuser(
        "role-admin@example.test", "Safe-password-9"
    )
    target = people["employee"]
    client = api_client(administrator)

    options = client.get("/api/v1/session/impersonation/options/")
    assert options.status_code == 200
    option = next(item for item in options.json()["users"] if item["id"] == target.pk)
    assert option["roles"][0]["code"] == "EMPLOYEE"

    started = client.post(
        "/api/v1/session/impersonation/",
        {"user_id": target.pk},
        content_type="application/json",
    )
    assert started.status_code == 200
    assert started.json()["user"]["id"] == target.pk
    assert started.json()["impersonation"]["administrator"]["id"] == administrator.pk
    assert client.get("/api/v1/users/").status_code == 403

    assignment.refresh_from_db()
    progress_path = f"/api/v1/tasks/{assignment.pk}/progress/"
    progress = client.post(
        progress_path,
        {
            "revision": assignment.revision,
            "entry_date": timezone.localdate().isoformat(),
            "percentage": 25,
            "note": "Saisie pendant la simulation.",
            "blocked": False,
        },
        content_type="application/json",
    )
    assert 200 <= progress.status_code < 300, progress.content
    assert ProgressEntry.objects.get(assignment=assignment).author == target
    action = RoleSimulationAction.objects.get(path=progress_path)
    assert action.simulation.administrator == administrator
    assert action.simulation.target == target
    assert action.status_code == progress.status_code

    protected = client.patch(
        "/api/v1/me/profile/",
        {"first_name": "Interdit"},
        content_type="application/json",
    )
    assert protected.status_code == 403
    assert protected.json()["error"]["code"] == "impersonation_protected_operation"
    assert RoleSimulationAction.objects.get(path="/api/v1/me/profile/").status_code == 403

    stopped = client.delete("/api/v1/session/impersonation/")
    assert stopped.status_code == 200
    assert stopped.json()["user"]["id"] == administrator.pk
    assert stopped.json()["impersonation"]["active"] is False
    simulation = RoleSimulation.objects.get()
    assert simulation.ended_at is not None
    assert simulation.end_reason == "manual"


def test_inactive_target_automatically_restores_superuser(people) -> None:
    administrator = User.objects.create_superuser(
        "restore-admin@example.test", "Safe-password-9"
    )
    target = people["employee"]
    client = api_client(administrator)
    assert (
        client.post(
            "/api/v1/session/impersonation/",
            {"user_id": target.pk},
            content_type="application/json",
        ).status_code
        == 200
    )
    target.is_active = False
    target.save(update_fields=["is_active"])

    session = client.get("/api/v1/session/")

    assert session.status_code == 200
    assert session.json()["user"]["id"] == administrator.pk
    simulation = RoleSimulation.objects.get()
    assert simulation.ended_at is not None
    assert simulation.end_reason == "target_unavailable"
