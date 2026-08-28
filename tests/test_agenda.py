from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from accounts.models import AgendaDirection as UserAgendaDirection, User
from access.models import GrantScope, RoleGrant, ScopedRole
from agenda.api import version_payload
from agenda.models import AgendaDirection, AgendaDraft, StaffAvailability, VisitorVisit
from agenda.services import (
    agenda_pdf_bytes,
    build_agenda_snapshot,
    generate_agenda,
    next_week_period,
)
from work.models import ProgressEntry, TaskActivity
from work.organogram import load_organogram
from work.services import week_start_for


def grant_role(*, user: User, role_code: str, unit, granted_by: User) -> RoleGrant:
    return RoleGrant.objects.create(
        user=user,
        role=ScopedRole.objects.get(code=role_code),
        unit=unit,
        scope=GrantScope.UNIT_TREE,
        valid_from=timezone.now() - timedelta(days=1),
        granted_by=granted_by,
        grant_reason="Scénario automatisé de l’agenda.",
    )


def test_canonical_organogram_reproduces_the_august_2026_structure() -> None:
    specs = load_organogram()
    by_code = {item.code: item for item in specs}
    assert len(specs) == 43
    assert specs[0].code == "CA"
    assert by_code["CS"].parent_code == "CA"
    assert by_code["ETH"].parent_code == "CS"
    assert by_code["DG"].parent_code == "CA"
    assert by_code["PSPI"].parent_code == "DG"
    assert by_code["DP"].parent_code == "DG"
    assert by_code["PSTA"].parent_code == "DP"
    assert by_code["LAB"].parent_code == "PSTA"
    assert by_code["DAF"].parent_code == "DG"
    assert by_code["SCH"].parent_code == "DAF"
    assert by_code["CCOMPTA"].parent_code == "SFC"
    assert len({item.code for item in specs}) == len(specs)
    assert len({item.demo_alias for item in specs if item.demo_alias}) == len(
        [item for item in specs if item.demo_alias]
    )


@pytest.mark.django_db
def test_secretary_records_visit_and_hr_records_availability(
    client, people, unit
) -> None:
    admin = User.objects.create_superuser("agenda-admin@example.test", "safe-password")
    secretary = people["manager"]
    hr = people["observer"]
    grant_role(
        user=secretary,
        role_code="AGENDA_SECRETARIAT",
        unit=unit,
        granted_by=admin,
    )
    grant_role(user=hr, role_code="AGENDA_HR", unit=unit, granted_by=admin)

    client.force_login(secretary)
    response = client.post(
        "/api/v1/visits/",
        {"party_size": 2, "visitor_names": ["A. Visiteur"]},
        content_type="application/json",
    )
    assert response.status_code == 201
    visit = VisitorVisit.objects.get()
    assert visit.party_size == 2
    assert visit.visitor_names == ["A. Visiteur"]
    response = client.post(
        f"/api/v1/visits/{visit.pk}/departure/",
        {"revision": visit.revision},
        content_type="application/json",
    )
    assert response.status_code == 200
    visit.refresh_from_db()
    assert visit.departed_at is not None
    assert visit.revision == 2

    client.force_login(hr)
    monday = week_start_for(timezone.localdate())
    response = client.post(
        "/api/v1/availability/",
        {
            "employee_id": people["employee"].pk,
            "kind": "leave",
            "start_date": monday.isoformat(),
            "end_date": (monday + timedelta(days=2)).isoformat(),
            "note": "Congé annuel",
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    assert StaffAvailability.objects.get().employee == people["employee"]
    assert client.get("/api/v1/agenda/versions/").status_code == 404


@pytest.mark.django_db
def test_secretary_saves_draft_and_generates_pdf_through_api(
    tmp_path: Path, settings, client, assignment, people, unit
) -> None:
    settings.PROCESS_DOCUMENT_BACKEND = "local"
    settings.PROCESS_DOCUMENT_ROOT = tmp_path
    admin = User.objects.create_superuser(
        "agenda-api-admin@example.test", "safe-password"
    )
    secretary = people["manager"]
    grant_role(
        user=secretary,
        role_code="AGENDA_SECRETARIAT",
        unit=unit,
        granted_by=admin,
    )
    client.force_login(secretary)
    monday = week_start_for(timezone.localdate())
    sunday = monday + timedelta(days=6)
    draft_url = "/api/v1/agenda/draft/"

    response = client.put(
        draft_url,
        {
            "period_start": monday.isoformat(),
            "period_end": sunday.isoformat(),
            "major_events": "Comité hebdomadaire",
            "revision": 0,
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 1

    stale = client.put(
        draft_url,
        {
            "period_start": monday.isoformat(),
            "period_end": sunday.isoformat(),
            "major_events": "Version périmée",
            "revision": 0,
        },
        content_type="application/json",
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_revision"

    response = client.put(
        draft_url,
        {
            "period_start": monday.isoformat(),
            "period_end": sunday.isoformat(),
            "major_events": "Comité hebdomadaire confirmé",
            "revision": 1,
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 2

    generated = client.post(
        "/api/v1/agenda/versions/",
        {
            "period_start": monday.isoformat(),
            "period_end": sunday.isoformat(),
            "agenda_direction": AgendaDirection.PROGRAMS,
        },
        content_type="application/json",
    )
    assert generated.status_code == 201
    assert generated.json()["version"] == 1

    pdf = client.get(generated.json()["pdf_url"])
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_agenda_snapshot_groups_overlapping_tasks_and_marks_unclassified_users(
    assignment, people, unit
) -> None:
    monday = week_start_for(timezone.localdate())
    ProgressEntry.objects.create(
        assignment=assignment,
        entry_date=monday - timedelta(days=1),
        percentage=25,
        note="Point antérieur",
        author=people["employee"],
    )
    entry = ProgressEntry.objects.create(
        assignment=assignment,
        entry_date=monday + timedelta(days=2),
        percentage=65,
        note="Livrable transmis",
        author=people["employee"],
    )
    TaskActivity.objects.create(
        assignment=assignment,
        kind="progress",
        actor=people["employee"],
        occurred_at=timezone.now(),
        message="Livrable transmis",
        percentage_before=25,
        percentage_after=65,
        progress_entry=entry,
    )

    snapshot = build_agenda_snapshot(
        period_start=monday,
        period_end=monday + timedelta(days=6),
        agenda_direction=AgendaDirection.PROGRAMS,
        major_events="Réunion du CA",
    )
    assert snapshot["major_events"] == "Réunion du CA"
    assert len(snapshot["units"]) == 1
    employee = snapshot["units"][0]["employees"][0]
    assert employee["completion_rate"] == 65
    assert employee["tasks"][0]["percentage"] == 65
    assert employee["tasks"][0]["progress_delta"] == 40
    assert employee["tasks"][0]["observation"] == "Livrable transmis"
    assert employee["unclassified"] is True
    assert snapshot["unclassified_users"][0]["id"] == people["employee"].pk


@pytest.mark.parametrize("terminal_status", ["completed", "closed_early"])
@pytest.mark.django_db
def test_agenda_snapshot_excludes_terminal_assignments(
    assignment, terminal_status
) -> None:
    assignment.status = terminal_status
    assignment.completed_at = timezone.now()
    assignment.save(update_fields=["status", "completed_at"])
    monday = week_start_for(timezone.localdate())

    snapshot = build_agenda_snapshot(
        period_start=monday,
        period_end=monday + timedelta(days=6),
        agenda_direction=AgendaDirection.PROGRAMS,
    )

    assert snapshot["units"] == []
    assert snapshot["unclassified_users"] == []


@pytest.mark.django_db
def test_generated_agenda_version_is_private_frozen_and_reprintable(
    tmp_path: Path, settings, assignment, people, unit
) -> None:
    settings.PROCESS_DOCUMENT_BACKEND = "local"
    settings.PROCESS_DOCUMENT_ROOT = tmp_path
    admin = User.objects.create_superuser("pdf-admin@example.test", "safe-password")
    secretary = people["manager"]
    grant_role(
        user=secretary,
        role_code="AGENDA_SECRETARIAT",
        unit=unit,
        granted_by=admin,
    )
    monday = week_start_for(timezone.localdate())
    sunday = monday + timedelta(days=6)
    AgendaDraft.objects.create(
        period_start=monday,
        period_end=sunday,
        major_events="Comité hebdomadaire",
        updated_by=secretary,
    )

    first = generate_agenda(
        actor=secretary,
        period_start=monday,
        period_end=sunday,
        agenda_direction=AgendaDirection.PROGRAMS,
    )
    first_bytes = agenda_pdf_bytes(first)
    assert first.version == 1
    assert first_bytes.startswith(b"%PDF")
    assert first.pdf_size == len(first_bytes)
    frozen_digest = first.snapshot_sha256

    draft = AgendaDraft.objects.get(period_start=monday, period_end=sunday)
    draft.major_events = "Événement corrigé"
    draft.revision += 1
    draft.updated_by = secretary
    draft.save()
    second = generate_agenda(
        actor=secretary,
        period_start=monday,
        period_end=sunday,
        agenda_direction=AgendaDirection.PROGRAMS,
    )
    first.refresh_from_db()
    assert second.version == 2
    assert second.snapshot_sha256 != frozen_digest
    assert first.snapshot_sha256 == frozen_digest
    assert agenda_pdf_bytes(first) == first_bytes

    administration = generate_agenda(
        actor=secretary,
        period_start=monday,
        period_end=sunday,
        agenda_direction=AgendaDirection.ADMINISTRATION,
    )
    assert administration.version == 1
    assert version_payload(administration)["agenda_direction_label"] == "Agenda DAF"
    assert b"Agenda DAF" in agenda_pdf_bytes(administration)


@pytest.mark.django_db
def test_user_direction_is_exclusive_and_unclassified_work_appears_in_both(
    assignment, people
) -> None:
    monday = week_start_for(timezone.localdate())
    sunday = monday + timedelta(days=6)
    employee = people["employee"]
    employee.agenda_direction = UserAgendaDirection.PROGRAMS
    employee.save(update_fields=["agenda_direction"])

    programs = build_agenda_snapshot(
        period_start=monday,
        period_end=sunday,
        agenda_direction=AgendaDirection.PROGRAMS,
    )
    administration = build_agenda_snapshot(
        period_start=monday,
        period_end=sunday,
        agenda_direction=AgendaDirection.ADMINISTRATION,
    )
    assert len(programs["units"]) == 1
    assert administration["units"] == []

    employee.agenda_direction = ""
    employee.save(update_fields=["agenda_direction"])
    administration = build_agenda_snapshot(
        period_start=monday,
        period_end=sunday,
        agenda_direction=AgendaDirection.ADMINISTRATION,
    )
    assert administration["agenda_direction_label"] == "Agenda DAF"
    assert len(administration["units"]) == 1


@pytest.mark.django_db
def test_user_explicitly_excluded_from_direction_agendas_appears_in_neither(
    assignment, people
) -> None:
    monday = week_start_for(timezone.localdate())
    sunday = monday + timedelta(days=6)
    employee = people["employee"]
    employee.include_in_direction_agendas = False
    employee.save(update_fields=["include_in_direction_agendas"])

    for direction in (
        AgendaDirection.PROGRAMS,
        AgendaDirection.ADMINISTRATION,
    ):
        snapshot = build_agenda_snapshot(
            period_start=monday,
            period_end=sunday,
            agenda_direction=direction,
        )
        assert snapshot["units"] == []
        assert snapshot["unclassified_users"] == []


def test_next_week_period_is_monday_through_sunday() -> None:
    start, end = next_week_period(timezone.datetime(2026, 8, 5).date())
    assert start.isoformat() == "2026-08-10"
    assert end.isoformat() == "2026-08-16"
