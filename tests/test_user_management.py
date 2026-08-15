from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Protocol, cast

import pytest
from django.contrib.auth import authenticate
from django.core import mail
from django.test import Client
from django.utils import timezone

from accounts.models import User
from accounts.services import user_management_state_token
from work.models import (
    OrganizationMembership,
    OrganizationUnit,
    OrganizationUnitLink,
    ReportingLine,
    Task,
    TaskAssignment,
    WorkCalendar,
    default_work_calendar_id,
)
from work.services import collaborator_state_token


pytestmark = pytest.mark.django_db


class ClientResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...

    def __getitem__(self, key: str) -> str: ...


def create_it_admin(alias: str = "it") -> User:
    return User.objects.create_user(
        f"{alias}@example.test",
        "Admin-test-2026!",
        login_alias=alias,
        is_staff=True,
        is_it_admin=True,
    )


def json_post(client: Client, path: str, data: dict[str, object]) -> ClientResponse:
    return cast(
        ClientResponse,
        client.post(path, data, content_type="application/json"),
    )


def test_user_management_requires_it_and_preserves_deactivated_account(client) -> None:
    ordinary = User.objects.create_user("ordinary@example.test", "Ordinary-2026!")
    client.force_login(ordinary)
    assert client.get("/api/v1/users/").status_code == 403
    assert client.get("/api/v1/session/").json()["capabilities"]["manage_users"] is False

    administrator = create_it_admin()
    client.force_login(administrator)
    assert client.get("/api/v1/session/").json()["capabilities"]["manage_users"] is True
    own_detail = client.get(f"/api/v1/users/{administrator.pk}/").json()
    own_deactivation = json_post(
        client,
        f"/api/v1/users/{administrator.pk}/deactivate/",
        {"state_token": own_detail["state_token"]},
    )
    assert own_deactivation.status_code == 400

    emergency = User.objects.create_superuser(
        "emergency@example.test", "Emergency-test-2026!"
    )
    emergency_detail = client.get(f"/api/v1/users/{emergency.pk}/")
    assert emergency_detail.status_code == 200
    assert emergency_detail.json()["capabilities"]["edit"] is False
    protected_reset = json_post(
        client,
        f"/api/v1/users/{emergency.pk}/temporary-password/",
        {"state_token": emergency_detail.json()["state_token"]},
    )
    assert protected_reset.status_code == 403

    payload = {
        "email": "new.person@example.test",
        "login_alias": "new_person",
        "first_name": "Nouvelle",
        "last_name": "Personne",
        "position": "Chargée de suivi",
        "phone": "",
        "agenda_direction": "administration",
        "include_in_direction_agendas": True,
        "unit_ids": [],
        "primary_unit_id": None,
        "primary_supervisor_id": None,
        "organization_effective_date": timezone.localdate().isoformat(),
    }

    created = client.post("/api/v1/users/", payload, content_type="application/json")

    assert created.status_code == 201
    user = User.objects.get(email=payload["email"])
    assert not user.has_usable_password()
    assert created.json()["capabilities"]["send_activation"] is True
    activation = json_post(
        client,
        f"/api/v1/users/{user.pk}/activation-link/",
        {"state_token": created.json()["state_token"]},
    )
    assert activation.status_code == 200
    assert len(mail.outbox) == 1
    assert "Choisissez votre mot de passe" in mail.outbox[0].body

    changed_payload = {
        **payload,
        "position": "Responsable du suivi",
        "state_token": created.json()["state_token"],
    }
    changed = client.patch(
        f"/api/v1/users/{user.pk}/",
        changed_payload,
        content_type="application/json",
    )
    assert changed.status_code == 200
    assert changed.json()["position"] == "Responsable du suivi"

    deactivated = json_post(
        client,
        f"/api/v1/users/{user.pk}/deactivate/",
        {"state_token": changed.json()["state_token"]},
    )
    assert deactivated.status_code == 200
    user.refresh_from_db()
    assert not user.is_active
    assert User.objects.filter(pk=user.pk).exists()
    assert user.history.filter(is_active=False, history_user=administrator).exists()

    stale = json_post(
        client,
        f"/api/v1/users/{user.pk}/reactivate/",
        {"state_token": changed.json()["state_token"]},
    )
    assert stale.status_code == 409
    reactivated = json_post(
        client,
        f"/api/v1/users/{user.pk}/reactivate/",
        {"state_token": deactivated.json()["state_token"]},
    )
    assert reactivated.status_code == 200
    user.refresh_from_db()
    assert user.is_active


def test_user_list_exposes_batch_tokens_and_bulk_deactivation_is_atomic(
    client: Client,
) -> None:
    administrator = create_it_admin()
    first = User.objects.create_user(
        "first.batch@example.test", "Batch-password-2026!", login_alias="first_batch"
    )
    second = User.objects.create_user(
        "second.batch@example.test", "Batch-password-2026!", login_alias="second_batch"
    )
    client.force_login(administrator)

    listed = client.get("/api/v1/users/?page_size=100")
    assert listed.status_code == 200
    rows = {item["id"]: item for item in listed.json()["items"]}
    assert rows[administrator.pk]["batch_capabilities"]["deactivate"] is False
    assert rows[first.pk]["batch_capabilities"]["deactivate"] is True
    assert rows[first.pk]["state_token"] == user_management_state_token(first)

    stale_token = rows[second.pk]["state_token"]
    second.position = "Fonction modifiée ailleurs"
    second.save(update_fields=["position"])
    stale = json_post(
        client,
        "/api/v1/users/bulk-action/",
        {
            "action": "deactivate",
            "users": [
                {"id": first.pk, "state_token": rows[first.pk]["state_token"]},
                {"id": second.pk, "state_token": stale_token},
            ],
        },
    )
    assert stale.status_code == 409
    first.refresh_from_db()
    assert first.is_active

    deactivated = json_post(
        client,
        "/api/v1/users/bulk-action/",
        {
            "action": "deactivate",
            "users": [
                {"id": first.pk, "state_token": user_management_state_token(first)},
                {"id": second.pk, "state_token": user_management_state_token(second)},
            ],
        },
    )
    assert deactivated.status_code == 200
    assert deactivated.json() == {"action": "deactivate", "affected": 2}
    assert User.objects.filter(pk__in=(first.pk, second.pk), is_active=False).count() == 2
    assert first.history.filter(
        is_active=False,
        history_user=administrator,
        history_change_reason="Désactivation groupée du compte",
    ).exists()


def test_bulk_user_action_requires_it_and_rejects_invalid_selection(
    client: Client,
) -> None:
    target = User.objects.create_user(
        "batch.target@example.test", "Batch-password-2026!", login_alias="batch_target"
    )
    ordinary = User.objects.create_user(
        "batch.ordinary@example.test", "Batch-password-2026!"
    )
    selection: list[dict[str, object]] = [
        {"id": target.pk, "state_token": user_management_state_token(target)}
    ]
    payload: dict[str, object] = {
        "action": "deactivate",
        "users": selection,
    }
    client.force_login(ordinary)
    assert json_post(client, "/api/v1/users/bulk-action/", payload).status_code == 403

    administrator = create_it_admin()
    client.force_login(administrator)
    duplicate_payload = {
        **payload,
        "users": selection * 2,
    }
    assert (
        json_post(client, "/api/v1/users/bulk-action/", duplicate_payload).status_code
        == 400
    )
    oversized_payload = {
        **payload,
        "users": selection * 101,
    }
    assert (
        json_post(client, "/api/v1/users/bulk-action/", oversized_payload).status_code
        == 400
    )


def test_bulk_delete_removes_only_inactive_orphans_and_keeps_audit(
    client: Client,
) -> None:
    administrator = create_it_admin()
    orphan = User.objects.create_user(
        "orphan@example.test", "Batch-password-2026!", login_alias="orphan"
    )
    orphan.is_active = False
    orphan.save(update_fields=["is_active"])
    linked = User.objects.create_user(
        "linked@example.test", "Batch-password-2026!", login_alias="linked"
    )
    linked.is_active = False
    linked.save(update_fields=["is_active"])
    unit = OrganizationUnit.objects.create(
        code="BATCH-USERS", short_name="Lot", long_name="Unité du lot"
    )
    OrganizationMembership.objects.create(
        user=linked,
        unit=unit,
        start_date=timezone.localdate(),
        is_primary=True,
    )
    task_linked = User.objects.create_user(
        "task-linked@example.test",
        "Batch-password-2026!",
        login_alias="task_linked",
    )
    task_linked.is_active = False
    task_linked.save(update_fields=["is_active"])
    Task.objects.create(
        code="BATCH-USER-TASK",
        title="Tâche liée au compte",
        description="Cette relation protégée interdit la suppression du compte.",
        created_by=task_linked,
    )
    client.force_login(administrator)

    blocked = json_post(
        client,
        "/api/v1/users/bulk-action/",
        {
            "action": "delete",
            "users": [
                {"id": orphan.pk, "state_token": user_management_state_token(orphan)},
                {"id": linked.pk, "state_token": user_management_state_token(linked)},
                {
                    "id": task_linked.pk,
                    "state_token": user_management_state_token(task_linked),
                },
            ],
            "reason": "Compte pilote créé par erreur",
            "confirmation": "SUPPRIMER",
        },
    )
    assert blocked.status_code == 400
    assert "linked" in blocked.json()["error"]["message"]
    assert "task_linked" in str(blocked.json()["error"]["fields"]["users"])
    assert User.objects.filter(pk=orphan.pk).exists()

    orphan_id = orphan.pk
    deleted = json_post(
        client,
        "/api/v1/users/bulk-action/",
        {
            "action": "delete",
            "users": [
                {"id": orphan_id, "state_token": user_management_state_token(orphan)}
            ],
            "reason": "Compte pilote créé par erreur",
            "confirmation": "SUPPRIMER",
        },
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"action": "delete", "affected": 1}
    assert not User.objects.filter(pk=orphan_id).exists()
    deletion_history = User.history.get(id=orphan_id, history_type="-")
    assert deletion_history.history_user == administrator
    assert (
        deletion_history.history_change_reason
        == "Suppression groupée : Compte pilote créé par erreur"
    )

    missing_confirmation = json_post(
        client,
        "/api/v1/users/bulk-action/",
        {
            "action": "delete",
            "users": [
                {"id": linked.pk, "state_token": user_management_state_token(linked)}
            ],
            "reason": "Nettoyage",
        },
    )
    assert missing_confirmation.status_code == 400
    assert User.objects.filter(pk=linked.pk).exists()


def test_temporary_password_is_one_time_and_blocks_business_access(client) -> None:
    administrator = create_it_admin()
    target = User.objects.create_user(
        "temporary@example.test", "Old-password-2026!", login_alias="temporary"
    )
    client.force_login(administrator)
    detail = client.get(f"/api/v1/users/{target.pk}/").json()

    response = json_post(
        client,
        f"/api/v1/users/{target.pk}/temporary-password/",
        {"state_token": detail["state_token"]},
    )

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    temporary_password = response.json()["temporary_password"]
    target.refresh_from_db()
    assert target.password_change_required
    assert not target.check_password("Old-password-2026!")
    assert target.check_password(temporary_password)
    assert "password" not in {field.name for field in target.history.model._meta.fields}

    client.logout()
    assert authenticate(username="temporary", password=temporary_password) == target
    assert client.login(username="temporary", password=temporary_password)
    blocked = client.get("/api/v1/dashboard/")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"
    assert client.get("/api/v1/session/").status_code == 200

    new_password = "New-secure-password-2026!"
    changed = json_post(
        client,
        "/api/v1/session/password/",
        {
            "current_password": temporary_password,
            "new_password": new_password,
            "new_password_confirmation": new_password,
        },
    )
    assert changed.status_code == 204
    target.refresh_from_db()
    assert not target.password_change_required
    assert target.check_password(new_password)
    assert client.get("/api/v1/dashboard/").status_code == 200


def test_collaborator_editor_requires_replacement_and_transfers_active_tasks(
    client,
) -> None:
    administrator = create_it_admin()
    root = OrganizationUnit.objects.create(
        code="ROOT-USERS", short_name="Racine", long_name="Direction racine"
    )
    child = OrganizationUnit.objects.create(
        code="CHILD-USERS", short_name="Enfant", long_name="Service enfant"
    )
    OrganizationUnitLink.objects.create(
        supervisor_service=root, collaborator_service=child
    )
    first_manager = User.objects.create_user("first.manager@example.test")
    second_manager = User.objects.create_user("second.manager@example.test")
    employee = User.objects.create_user("team.member@example.test")
    today = timezone.localdate()
    for manager in (first_manager, second_manager):
        OrganizationMembership.objects.create(
            user=manager,
            unit=root,
            start_date=today - timedelta(days=30),
            is_primary=True,
        )
    OrganizationMembership.objects.create(
        user=employee,
        unit=child,
        start_date=today - timedelta(days=30),
        is_primary=True,
    )
    ReportingLine.objects.create(
        employee=employee,
        supervisor=first_manager,
        unit=child,
        start_date=today - timedelta(days=30),
        is_primary=True,
    )
    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    task = Task.objects.create(
        code="USER-MOVE",
        title="Tâche à transférer",
        description="Conserver la responsabilité active.",
        created_by=first_manager,
    )
    assignment = TaskAssignment.objects.create(
        task=task,
        employee=employee,
        manager=first_manager,
        organization_unit=child,
        start_date=today,
        due_date=calendar.due_date_for(today, Decimal("3.0")),
        estimated_work_days=Decimal("3.0"),
        calendar=calendar,
        status="active",
    )
    client.force_login(administrator)
    endpoint = f"/api/v1/users/{first_manager.pk}/collaborators/"
    initial = client.get(endpoint)
    assert initial.status_code == 200
    assert [item["id"] for item in initial.json()["current"]] == [employee.pk]

    missing_replacement = client.put(
        endpoint,
        {
            "collaborator_ids": [],
            "replacements": [],
            "effective_date": today.isoformat(),
            "state_token": initial.json()["state_token"],
        },
        content_type="application/json",
    )
    assert missing_replacement.status_code == 400
    assert (
        ReportingLine.objects.get(
            employee=employee, is_primary=True, end_date__isnull=True
        ).supervisor
        == first_manager
    )

    moved = client.put(
        endpoint,
        {
            "collaborator_ids": [],
            "replacements": [
                {"employee_id": employee.pk, "supervisor_id": second_manager.pk}
            ],
            "effective_date": today.isoformat(),
            "state_token": initial.json()["state_token"],
        },
        content_type="application/json",
    )
    assert moved.status_code == 200
    assert (
        ReportingLine.objects.get(
            employee=employee, is_primary=True, end_date__isnull=True
        ).supervisor
        == second_manager
    )
    assignment.refresh_from_db()
    assert assignment.manager == second_manager

    stale = client.put(
        endpoint,
        {
            "collaborator_ids": [employee.pk],
            "replacements": [],
            "effective_date": today.isoformat(),
            "state_token": initial.json()["state_token"],
        },
        content_type="application/json",
    )
    assert stale.status_code == 409
    assert moved.json()["state_token"] == collaborator_state_token(first_manager)

    fresh = client.get(endpoint)
    added_back = client.put(
        endpoint,
        {
            "collaborator_ids": [employee.pk],
            "replacements": [],
            "effective_date": today.isoformat(),
            "state_token": fresh.json()["state_token"],
        },
        content_type="application/json",
    )
    assert added_back.status_code == 200
    assert (
        ReportingLine.objects.get(
            employee=employee, is_primary=True, end_date__isnull=True
        ).supervisor
        == first_manager
    )
