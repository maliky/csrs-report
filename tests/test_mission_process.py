from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, override_settings
from django.utils import timezone

from access.models import GrantScope, RoleGrant, ScopedRole
from accounts.models import User
from processes.exports import export_case_zip
from processes.models import (
    CaseStatus,
    DocumentKind,
    MissionType,
    ProcessCase,
    ProcessEvent,
    ProcessQueue,
    QueueKind,
    WorkItemStatus,
)
from processes.services import (
    act_on_case,
    add_document,
    create_mission_draft,
    resolve_queue,
    update_mission_draft,
)
from processes.storage import ScanResult
from work.models import (
    OrganizationMembership,
    OrganizationUnit,
    OrganizationUnitLink,
)


class CleanScanner:
    def scan(self, content: bytes) -> ScanResult:
        assert content
        return ScanResult(clean=True, details="test: OK")


class MemoryStorage:
    provider = "local"

    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def save(self, *, case_reference: str, name: str, content: bytes) -> str:
        key = f"{case_reference}/{len(self.items)}-{name}"
        self.items[key] = content
        return key

    def read(self, key: str) -> bytes:
        return self.items[key]

    def delete(self, key: str) -> None:
        self.items.pop(key, None)


@pytest.fixture
def mission_context(db) -> dict[str, object]:
    today = timezone.localdate()
    root = OrganizationUnit.objects.create(
        code="DG-PROC", short_name="dg", long_name="Direction générale processus"
    )
    requester_unit = OrganizationUnit.objects.create(
        code="RES-PROC", short_name="res", long_name="Direction de la recherche"
    )
    assistant_unit = OrganizationUnit.objects.create(
        code="AST-PROC", short_name="assist", long_name="Assistance de direction"
    )
    fleet_unit = OrganizationUnit.objects.create(
        code="FLT-PROC", short_name="parc", long_name="Parc automobile"
    )
    OrganizationUnitLink.objects.create(
        supervisor_service=root, collaborator_service=requester_unit
    )
    users = {
        name: User.objects.create_user(
            f"{name}@example.test", password="Secret9!x", first_name=name.title()
        )
        for name in ("requester", "assistant", "signer", "secretary", "fleet", "outsider")
    }
    for name, unit in (
        ("requester", requester_unit),
        ("assistant", assistant_unit),
        ("signer", root),
        ("secretary", assistant_unit),
        ("fleet", fleet_unit),
        ("outsider", requester_unit),
    ):
        OrganizationMembership.objects.create(
            user=users[name],
            unit=unit,
            job_title=name,
            start_date=today - timedelta(days=30),
            is_primary=True,
        )
    definition = ProcessCase._meta.get_field("definition").remote_field.model.objects.get(
        code="MISSION_ORDER", version=1
    )
    queue_specs = (
        (QueueKind.ASSISTANCE, "MISSION_ASSISTANCE", assistant_unit),
        (QueueKind.SIGNATURE, "MISSION_SIGNER", root),
        (QueueKind.DISTRIBUTION, "MISSION_SECRETARIAT", assistant_unit),
        (QueueKind.FLEET, "MISSION_FLEET", fleet_unit),
    )
    queues = {}
    for kind, role_code, handler in queue_specs:
        role = ScopedRole.objects.get(code=role_code)
        queues[kind] = ProcessQueue.objects.create(
            definition=definition,
            kind=kind,
            name=f"File {kind}",
            role=role,
            handler_unit=handler,
            coverage_unit=root,
            coverage_scope=GrantScope.UNIT_TREE,
        )
        actor_name = {
            QueueKind.ASSISTANCE: "assistant",
            QueueKind.SIGNATURE: "signer",
            QueueKind.DISTRIBUTION: "secretary",
            QueueKind.FLEET: "fleet",
        }[kind]
        RoleGrant.objects.create(
            user=users[actor_name],
            role=role,
            unit=handler,
            scope=GrantScope.UNIT_TREE,
            granted_by=users["signer"],
            grant_reason="Responsabilité de test du processus.",
        )
    return {
        "users": users,
        "root": root,
        "requester_unit": requester_unit,
        "assistant_unit": assistant_unit,
        "queues": queues,
    }


def _draft(context: dict[str, object], *, international: bool = False) -> ProcessCase:
    users = context["users"]
    assert isinstance(users, dict)
    today = timezone.localdate()
    return create_mission_draft(
        actor=users["requester"],
        mission_type=(
            MissionType.INTERNATIONAL if international else MissionType.DOMESTIC
        ),
        destination="Bouaké" if not international else "Dakar",
        purpose="Participer à l'atelier annuel de coordination scientifique.",
        itinerary="Abidjan — Bouaké — Abidjan",
        transport_mode="Véhicule de service",
        transport_company="",
        departure_date=today + timedelta(days=10),
        return_date=today + timedelta(days=12),
        funding_source="Projet de recherche",
        costs_covered="Transport et perdiem",
        vehicle_required=False,
        vehicle_details="",
        participant_ids=[],
    )


def _upload(
    case: ProcessCase,
    actor: User,
    kind: str,
    storage: MemoryStorage,
) -> None:
    add_document(
        actor=actor,
        case=case,
        kind=kind,
        name=f"{kind}.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 credible test content",
        expected_revision=case.revision,
        storage=storage,
        scanner=CleanScanner(),
    )
    case.refresh_from_db()


@pytest.mark.django_db
def test_domestic_mission_runs_through_claim_signature_and_distribution(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    storage = MemoryStorage()
    case = _draft(mission_context)
    _upload(case, users["requester"], DocumentKind.TERMS_OF_REFERENCE, storage)

    case = act_on_case(
        actor=users["requester"], case=case, expected_revision=2, action="submit"
    )
    assert case.status == CaseStatus.ASSISTANCE
    item = case.work_items.get(status=WorkItemStatus.OPEN)
    expected = 1
    cursor = timezone.localdate()
    while expected:
        cursor += timedelta(days=1)
        if case.calendar.is_working_day(cursor):
            expected -= 1
    assert item.due_date == cursor

    case = act_on_case(
        actor=users["assistant"], case=case, expected_revision=3, action="claim"
    )
    _upload(case, users["assistant"], DocumentKind.ORDER_DRAFT, storage)
    case = act_on_case(
        actor=users["assistant"],
        case=case,
        expected_revision=5,
        action="send_to_signature",
    )
    case = act_on_case(
        actor=users["signer"], case=case, expected_revision=6, action="claim"
    )
    case = act_on_case(
        actor=users["signer"],
        case=case,
        expected_revision=7,
        action="sign",
        confirmation=f"SIGNER {case.reference}",
    )
    assert case.status == CaseStatus.DISTRIBUTION
    assert case.signature.snapshot_sha256

    case = act_on_case(
        actor=users["secretary"], case=case, expected_revision=8, action="claim"
    )
    case = act_on_case(
        actor=users["secretary"],
        case=case,
        expected_revision=9,
        action="complete_distribution",
        checklist={
            "accounting_copy": True,
            "original_delivered": True,
            "archive_copy": True,
        },
    )
    assert case.status == CaseStatus.COMPLETED
    assert case.closed_at is not None
    assert case.retention_until is not None
    with pytest.raises(ValidationError, match="terminé"):
        act_on_case(
            actor=users["requester"],
            case=case,
            expected_revision=10,
            action="submit",
        )


@pytest.mark.django_db
def test_international_ticket_is_required_only_before_signature_queue(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    storage = MemoryStorage()
    case = _draft(mission_context, international=True)
    _upload(case, users["requester"], DocumentKind.TERMS_OF_REFERENCE, storage)
    case = act_on_case(
        actor=users["requester"], case=case, expected_revision=2, action="submit"
    )
    case = act_on_case(
        actor=users["assistant"], case=case, expected_revision=3, action="claim"
    )
    _upload(case, users["assistant"], DocumentKind.ORDER_DRAFT, storage)
    with pytest.raises(ValidationError, match="billet"):
        act_on_case(
            actor=users["assistant"],
            case=case,
            expected_revision=5,
            action="send_to_signature",
        )
    _upload(case, users["assistant"], DocumentKind.TICKET, storage)
    case = act_on_case(
        actor=users["assistant"],
        case=case,
        expected_revision=6,
        action="send_to_signature",
    )
    assert case.status == CaseStatus.SIGNATURE


@pytest.mark.django_db
def test_queue_routing_prefers_exact_service_and_blocks_equal_ambiguity(
    mission_context: dict[str, object],
) -> None:
    case = _draft(mission_context)
    queues = mission_context["queues"]
    assert isinstance(queues, dict)
    broad = queues[QueueKind.ASSISTANCE]
    exact = ProcessQueue.objects.create(
        definition=broad.definition,
        kind=QueueKind.ASSISTANCE,
        name="Assistance recherche",
        role=broad.role,
        handler_unit=broad.handler_unit,
        coverage_unit=mission_context["requester_unit"],
        coverage_scope=GrantScope.UNIT_ONLY,
    )
    assert resolve_queue(case, QueueKind.ASSISTANCE) == exact
    ProcessQueue.objects.create(
        definition=broad.definition,
        kind=QueueKind.ASSISTANCE,
        name="Assistance recherche bis",
        role=broad.role,
        handler_unit=broad.handler_unit,
        coverage_unit=mission_context["requester_unit"],
        coverage_scope=GrantScope.UNIT_ONLY,
    )
    with pytest.raises(ValidationError, match="même précision"):
        resolve_queue(case, QueueKind.ASSISTANCE)


@pytest.mark.django_db
def test_claim_requires_active_role_and_takeover_requires_reason(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    storage = MemoryStorage()
    case = _draft(mission_context)
    _upload(case, users["requester"], DocumentKind.TERMS_OF_REFERENCE, storage)
    case = act_on_case(
        actor=users["requester"], case=case, expected_revision=2, action="submit"
    )
    with pytest.raises(PermissionDenied):
        act_on_case(
            actor=users["outsider"], case=case, expected_revision=3, action="claim"
        )
    case = act_on_case(
        actor=users["assistant"], case=case, expected_revision=3, action="claim"
    )
    with pytest.raises(ValidationError, match="motif"):
        act_on_case(
            actor=users["outsider"], case=case, expected_revision=4, action="takeover"
        )
    replacement_grant = RoleGrant.objects.create(
        user=users["outsider"],
        role=ScopedRole.objects.get(code="MISSION_ASSISTANCE"),
        unit=mission_context["assistant_unit"],
        scope=GrantScope.UNIT_TREE,
        granted_by=users["signer"],
        grant_reason="Remplacement temporaire de l'assistance.",
    )
    case = act_on_case(
        actor=users["outsider"],
        case=case,
        expected_revision=4,
        action="takeover",
        note="Remplacement pendant une absence approuvée.",
    )
    assert (
        case.work_items.get(status=WorkItemStatus.CLAIMED).claimed_by == users["outsider"]
    )
    assert (
        case.events.get(kind="takeover").details["previous_actor_id"]
        == users["assistant"].pk
    )
    replacement_grant.revoked_at = timezone.now()
    replacement_grant.revoked_by = users["signer"]
    replacement_grant.revoke_reason = "Fin du remplacement temporaire."
    replacement_grant.save()
    with pytest.raises(PermissionDenied, match="délégation"):
        act_on_case(
            actor=users["outsider"],
            case=case,
            expected_revision=5,
            action="send_to_signature",
        )


@pytest.mark.django_db
def test_claimed_assistance_can_prepare_fields_but_signer_cannot_edit(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    storage = MemoryStorage()
    case = _draft(mission_context)
    _upload(case, users["requester"], DocumentKind.TERMS_OF_REFERENCE, storage)
    case = act_on_case(
        actor=users["requester"], case=case, expected_revision=2, action="submit"
    )
    case = act_on_case(
        actor=users["assistant"], case=case, expected_revision=3, action="claim"
    )
    mission = case.mission_order
    case = update_mission_draft(
        actor=users["assistant"],
        case=case,
        expected_revision=4,
        fields={
            "mission_type": mission.mission_type,
            "destination": mission.destination,
            "purpose": mission.purpose,
            "itinerary": mission.itinerary,
            "transport_mode": mission.transport_mode,
            "transport_company": mission.transport_company,
            "departure_date": mission.departure_date,
            "return_date": mission.return_date,
            "funding_source": mission.funding_source,
            "costs_covered": mission.costs_covered,
            "vehicle_required": mission.vehicle_required,
            "vehicle_details": mission.vehicle_details,
            "official_number": "OM/DG/2026/0042",
        },
        participant_ids=case.mission_participants.values_list("user_id", flat=True),
    )
    assert case.mission_order.official_number == "OM/DG/2026/0042"
    with pytest.raises(PermissionDenied):
        update_mission_draft(
            actor=users["signer"],
            case=case,
            expected_revision=5,
            fields={"official_number": "ALTÉRÉ"},
            participant_ids=[users["requester"].pk],
        )


@pytest.mark.django_db
def test_document_content_must_match_its_declared_format(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    case = _draft(mission_context)
    with pytest.raises(ValidationError, match="format déclaré"):
        add_document(
            actor=users["requester"],
            case=case,
            kind=DocumentKind.TERMS_OF_REFERENCE,
            name="faux.pdf",
            content_type="application/pdf",
            content=b"ceci n'est pas un pdf",
            expected_revision=1,
            storage=MemoryStorage(),
            scanner=CleanScanner(),
        )


@pytest.mark.django_db
def test_process_event_and_signature_evidence_are_immutable(
    mission_context: dict[str, object],
) -> None:
    event = _draft(mission_context).events.get(kind="created")
    event.message = "Tentative de réécriture"
    with pytest.raises(ValidationError, match="modifié"):
        event.save()
    with pytest.raises(ValidationError, match="supprimé"):
        ProcessEvent.objects.filter(pk=event.pk).delete()


@pytest.mark.django_db
def test_api_rejects_a_stale_case_revision(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    client = Client()
    client.force_login(users["requester"])
    case = _draft(mission_context)
    response = client.post(
        f"/api/v1/processes/{case.pk}/actions/",
        data={"revision": 99, "action": "abandon"},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_revision"


@pytest.mark.django_db
def test_document_rules_reject_sensitive_download_for_uninvolved_viewer(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    storage = MemoryStorage()
    case = _draft(mission_context)
    _upload(case, users["requester"], DocumentKind.TERMS_OF_REFERENCE, storage)
    document = case.documents.get()
    client = Client()
    client.force_login(users["outsider"])
    response = client.get(f"/api/v1/processes/{case.pk}/documents/{document.pk}/content/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_document_metadata_is_immutable_after_registration(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    case = _draft(mission_context)
    _upload(case, users["requester"], DocumentKind.TERMS_OF_REFERENCE, MemoryStorage())
    document = case.documents.get()
    document.original_name = "renomme.pdf"
    with pytest.raises(ValidationError, match="modifiée"):
        document.save()
    with pytest.raises(ValidationError, match="supprimée"):
        document.delete()


@pytest.mark.django_db
def test_new_document_version_replaces_metadata_without_rewriting_old_record(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    case = _draft(mission_context)
    storage = MemoryStorage()
    _upload(case, users["requester"], DocumentKind.TERMS_OF_REFERENCE, storage)
    first = case.documents.get()
    _upload(case, users["requester"], DocumentKind.TERMS_OF_REFERENCE, storage)
    first.refresh_from_db()
    assert first.replaced_by_id is not None
    assert (
        case.documents.filter(
            kind=DocumentKind.TERMS_OF_REFERENCE, replaced_by__isnull=True
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_authorized_admin_can_place_and_release_legal_hold_on_closed_case(
    mission_context: dict[str, object],
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    admin = User.objects.create_superuser("audit@example.test", "Secret9!x")
    case = _draft(mission_context)
    case.status = CaseStatus.ABANDONED
    case.current_step = CaseStatus.ABANDONED
    case.closed_at = timezone.now()
    case.save()
    with pytest.raises(PermissionDenied):
        act_on_case(
            actor=users["requester"],
            case=case,
            expected_revision=1,
            action="place_legal_hold",
            note="Audit en cours.",
        )
    case = act_on_case(
        actor=admin,
        case=case,
        expected_revision=1,
        action="place_legal_hold",
        note="Audit institutionnel en cours.",
    )
    assert case.legal_hold is True
    case = act_on_case(
        actor=admin,
        case=case,
        expected_revision=2,
        action="release_legal_hold",
        note="Audit clôturé sans réserve.",
    )
    assert case.legal_hold is False
    assert list(case.events.values_list("kind", flat=True))[-2:] == [
        "place_legal_hold",
        "release_legal_hold",
    ]


@pytest.mark.django_db
def test_closed_case_export_contains_pdf_originals_and_checksum_manifest(
    mission_context: dict[str, object], tmp_path
) -> None:
    users = mission_context["users"]
    assert isinstance(users, dict)
    case = _draft(mission_context)
    with override_settings(PROCESS_DOCUMENT_ROOT=tmp_path):
        add_document(
            actor=users["requester"],
            case=case,
            kind=DocumentKind.TERMS_OF_REFERENCE,
            name="tdr.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 original",
            expected_revision=case.revision,
            scanner=CleanScanner(),
        )
        case.refresh_from_db()
        case.status = CaseStatus.ABANDONED
        case.current_step = CaseStatus.ABANDONED
        case.closed_at = timezone.now()
        case.save()
        payload = export_case_zip(case)
    with ZipFile(BytesIO(payload)) as archive:
        assert "audit.pdf" in archive.namelist()
        assert archive.read("audit.pdf").startswith(b"%PDF-1.4")
        assert "manifest.json" in archive.namelist()
        assert any(name.startswith("pieces/") for name in archive.namelist())
        assert case.documents.get().sha256.encode() in archive.read("manifest.json")
