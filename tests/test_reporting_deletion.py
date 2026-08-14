from __future__ import annotations

from hashlib import sha256
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from accounts.models import User
from agenda.models import (
    AgendaDirection,
    AgendaDraft,
    AgendaVersion,
    StaffAvailability,
    VisitorVisit,
)
from processes.storage import LocalPrivateStorage
from work.models import (
    NotificationDelivery,
    OrganizationUnit,
    ProgressEntry,
    ReportingDeletionAudit,
    ReportingDeletionKind,
    Task,
    TaskAssignment,
    TaskCodeSequence,
    TaskProposal,
)
from work.reporting_cleanup import reset_reporting_data


pytestmark = pytest.mark.django_db


def admin_user() -> User:
    return User.objects.create_user(
        "it-admin@example.test",
        login_alias="it-admin",
        is_staff=True,
        is_it_admin=True,
    )


def test_task_management_is_restricted_and_exposes_global_tasks(
    client, people, assignment
) -> None:
    client.force_login(people["manager"])
    assert client.get("/api/v1/task-management/").status_code == 403
    assert client.get("/api/v1/session/").json()["capabilities"]["delete_tasks"] is False

    administrator = admin_user()
    client.force_login(administrator)
    session = client.get("/api/v1/session/")
    response = client.get("/api/v1/task-management/", {"q": "TSK-TEST"})

    assert session.json()["capabilities"]["delete_tasks"] is True
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == assignment.pk


def test_bulk_delete_is_atomic_audited_and_preserves_a_shared_task(
    client, people, assignment, unit
) -> None:
    administrator = admin_user()
    second = TaskAssignment.objects.create(
        task=assignment.task,
        employee=people["outsider"],
        manager=people["manager"],
        organization_unit=unit,
        calendar=assignment.calendar,
        start_date=assignment.start_date,
        due_date=assignment.due_date,
        estimated_work_days=assignment.estimated_work_days,
        status="active",
    )
    progress = ProgressEntry.objects.create(
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=30,
        note="Avancement temporaire.",
        author=people["employee"],
    )
    proposal = TaskProposal.objects.create(
        employee=assignment.employee,
        organization_unit=unit,
        title="Proposition deja validee",
        description="Conserver cette decision historique.",
        action=assignment.task.action,
        calendar=assignment.calendar,
        start_date=assignment.start_date,
        due_date=assignment.due_date,
        estimated_work_days=assignment.estimated_work_days,
        status="accepted",
        accepted_assignment=assignment,
    )
    client.force_login(administrator)

    stale = client.post(
        "/api/v1/tasks/bulk-delete/",
        {
            "assignments": [{"id": assignment.pk, "revision": 99}],
            "reason": "Nettoyage controle",
            "confirmation": "SUPPRIMER",
        },
        content_type="application/json",
    )
    assert stale.status_code == 409
    assert TaskAssignment.objects.filter(pk=assignment.pk).exists()
    assert not ReportingDeletionAudit.objects.exists()

    response = client.post(
        "/api/v1/tasks/bulk-delete/",
        {
            "assignments": [{"id": assignment.pk, "revision": assignment.revision}],
            "reason": "Nettoyage controle",
            "confirmation": "SUPPRIMER",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["deleted_assignments"] == 1
    assert response.json()["deleted_tasks"] == 0
    assert TaskAssignment.objects.filter(pk=second.pk).exists()
    assert Task.objects.filter(pk=assignment.task_id).exists()
    proposal.refresh_from_db()
    assert proposal.accepted_assignment is None
    audit = ReportingDeletionAudit.objects.get()
    assert audit.kind == ReportingDeletionKind.TASK_BATCH
    assert audit.actor == administrator
    assert audit.reason == "Nettoyage controle"
    assert audit.snapshot["assignments"][0]["assignment_id"] == assignment.pk
    assert not TaskAssignment.history.filter(id=assignment.pk).exists()
    assert not ProgressEntry.history.filter(id=progress.pk).exists()
    with pytest.raises(ValidationError):
        audit.delete()

    final = client.post(
        "/api/v1/tasks/bulk-delete/",
        {
            "assignments": [{"id": second.pk, "revision": second.revision}],
            "reason": "Fin du nettoyage controle",
            "confirmation": "SUPPRIMER",
        },
        content_type="application/json",
    )
    assert final.status_code == 200
    assert final.json()["deleted_tasks"] == 1
    assert not Task.objects.filter(pk=assignment.task_id).exists()
    assert not Task.history.filter(id=assignment.task_id).exists()
    assert ReportingDeletionAudit.objects.count() == 2


def test_reporting_reset_dry_run_then_clears_only_reporting_data(
    tmp_path, settings, people, assignment, unit
) -> None:
    administrator = admin_user()
    settings.PROCESS_DOCUMENT_BACKEND = "local"
    settings.PROCESS_DOCUMENT_ROOT = tmp_path
    TaskProposal.objects.create(
        employee=assignment.employee,
        organization_unit=unit,
        title="Proposition a supprimer",
        description="Donnee de reporting.",
        action=assignment.task.action,
        calendar=assignment.calendar,
        start_date=assignment.start_date,
        due_date=assignment.due_date,
        estimated_work_days=assignment.estimated_work_days,
    )
    TaskCodeSequence.objects.create(action=assignment.task.action, year=2026)
    NotificationDelivery.objects.create(
        recipient=assignment.employee,
        event_type="new_assignment",
        subject="Nouvelle tache",
        body="Donnee a supprimer",
    )
    visit = VisitorVisit.objects.create(
        party_size=1, recorded_by=administrator, updated_by=administrator
    )
    StaffAvailability.objects.create(
        employee=assignment.employee,
        kind="leave",
        start_date=assignment.start_date,
        end_date=assignment.start_date,
        recorded_by=administrator,
        updated_by=administrator,
    )
    draft = AgendaDraft.objects.create(
        period_start=assignment.start_date,
        period_end=assignment.due_date,
        major_events="RAS",
        updated_by=administrator,
    )
    pdf = b"%PDF-1.4 test"
    storage = LocalPrivateStorage(tmp_path)
    key = storage.save(case_reference="agenda-test", name="agenda.pdf", content=pdf)
    AgendaVersion.objects.create(
        draft=draft,
        period_start=draft.period_start,
        period_end=draft.period_end,
        agenda_direction=AgendaDirection.PROGRAMS,
        version=1,
        snapshot={},
        snapshot_sha256=sha256(b"{}").hexdigest(),
        storage_provider="local",
        storage_key=key,
        pdf_sha256=sha256(pdf).hexdigest(),
        pdf_size=len(pdf),
        generated_by=administrator,
    )
    user_ids = set(User.objects.values_list("pk", flat=True))
    unit_ids = set(OrganizationUnit.objects.values_list("pk", flat=True))

    preview = reset_reporting_data(
        actor=administrator, reason="Reinitialisation du pilote", dry_run=True
    )
    assert preview.counts["tasks"] == 1
    assert Task.objects.exists() and AgendaVersion._base_manager.exists()
    assert not ReportingDeletionAudit.objects.exists()

    result = reset_reporting_data(
        actor=administrator, reason="Reinitialisation du pilote"
    )

    assert result.counts["visits"] == 1
    assert not Task.objects.exists()
    assert not TaskAssignment.objects.exists()
    assert not TaskProposal.objects.exists()
    assert not TaskCodeSequence.objects.exists()
    assert not NotificationDelivery.objects.filter(event_type="new_assignment").exists()
    assert not AgendaDraft.objects.exists()
    assert not AgendaVersion._base_manager.exists()
    assert not VisitorVisit.objects.filter(pk=visit.pk).exists()
    assert not StaffAvailability.objects.exists()
    assert not (tmp_path / key).exists()
    assert set(User.objects.values_list("pk", flat=True)) == user_ids
    assert set(OrganizationUnit.objects.values_list("pk", flat=True)) == unit_ids
    audit = ReportingDeletionAudit.objects.get(kind=ReportingDeletionKind.REPORTING_RESET)
    assert audit.actor == administrator


def test_reset_command_requires_exactly_one_mode(people) -> None:
    administrator = admin_user()
    output = StringIO()
    with pytest.raises(CommandError, match="exactement"):
        call_command(
            "reset_reporting_data",
            actor=administrator.login_alias,
            reason="Controle",
            stdout=output,
        )
    call_command(
        "reset_reporting_data",
        actor=administrator.login_alias,
        reason="Controle",
        dry_run=True,
        stdout=output,
    )
    assert "simulation annulee" in output.getvalue()
