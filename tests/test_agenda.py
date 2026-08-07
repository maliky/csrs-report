from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from accounts.models import User
from access.models import GrantScope, RoleGrant, ScopedRole
from agenda.models import StaffAvailability, VisitorVisit, WeeklyAgendaDraft
from agenda.services import (
    agenda_pdf_bytes,
    build_week_snapshot,
    generate_agenda,
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
    draft_url = "/api/v1/agenda/draft/"

    response = client.put(
        draft_url,
        {
            "week_start": monday.isoformat(),
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
            "week_start": monday.isoformat(),
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
            "week_start": monday.isoformat(),
            "major_events": "Comité hebdomadaire confirmé",
            "revision": 1,
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 2

    generated = client.post(
        "/api/v1/agenda/versions/",
        {"week_start": monday.isoformat()},
        content_type="application/json",
    )
    assert generated.status_code == 201
    assert generated.json()["version"] == 1

    pdf = client.get(generated.json()["pdf_url"])
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_week_snapshot_groups_tasks_and_uses_end_of_week_progress(
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

    snapshot = build_week_snapshot(week_start=monday, major_events="Réunion du CA")
    assert snapshot["major_events"] == "Réunion du CA"
    assert len(snapshot["units"]) == 1
    employee = snapshot["units"][0]["employees"][0]
    assert employee["completion_rate"] == 65
    assert employee["tasks"][0]["percentage"] == 65
    assert employee["tasks"][0]["progress_delta"] == 40
    assert employee["tasks"][0]["observation"] == "Livrable transmis"


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
    WeeklyAgendaDraft.objects.create(
        week_start=monday,
        major_events="Comité hebdomadaire",
        updated_by=secretary,
    )

    first = generate_agenda(actor=secretary, week_start=monday)
    first_bytes = agenda_pdf_bytes(first)
    assert first.version == 1
    assert first_bytes.startswith(b"%PDF")
    assert first.pdf_size == len(first_bytes)
    frozen_digest = first.snapshot_sha256

    draft = WeeklyAgendaDraft.objects.get(week_start=monday)
    draft.major_events = "Événement corrigé"
    draft.revision += 1
    draft.updated_by = secretary
    draft.save()
    second = generate_agenda(actor=secretary, week_start=monday)
    first.refresh_from_db()
    assert second.version == 2
    assert second.snapshot_sha256 != frozen_digest
    assert first.snapshot_sha256 == frozen_digest
    assert agenda_pdf_bytes(first) == first_bytes
