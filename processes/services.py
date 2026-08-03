"""Typed functional services for the mission-order workflow."""

from __future__ import annotations

from collections import deque
from datetime import date
import hashlib
import json
from pathlib import Path
import secrets
from typing import Iterable, Mapping
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from access.models import GrantScope
from access.services import (
    PROCESS_EXPORT_PERMISSION,
    PROCESS_VIEW_PERMISSION,
    active_role_grants,
    has_scoped_permission,
    primary_membership,
    units_in_scope,
)
from accounts.models import User
from processes.models import (
    CaseStatus,
    DocumentKind,
    MissionOrder,
    MissionParticipant,
    MissionType,
    ProcessCase,
    ProcessDefinition,
    ProcessDocument,
    ProcessEvent,
    ProcessQueue,
    ProcessSignature,
    ProcessWorkItem,
    QueueKind,
    ScanStatus,
    TERMINAL_CASE_STATUSES,
    WorkItemStatus,
)
from processes.storage import (
    DocumentStorage,
    MalwareScanner,
    configured_scanner,
    configured_storage,
)
from work.models import OrganizationUnitLink, WorkCalendar, default_work_calendar_id
from work.services import ensure_revision

MISSION_DEFINITION_CODE = "MISSION_ORDER"
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
    }
)
ALLOWED_SUFFIXES = frozenset({".pdf", ".docx", ".jpg", ".jpeg", ".png"})
ACTION_NOTES_REQUIRED = frozenset({"takeover", "request_correction", "reject"})


def mission_definition() -> ProcessDefinition:
    try:
        return ProcessDefinition.objects.get(
            code=MISSION_DEFINITION_CODE, version=1, active=True
        )
    except ProcessDefinition.DoesNotExist as exc:
        raise ValidationError(
            "Le processus d'ordre de mission n'est pas configuré."
        ) from exc


def may_create_mission(user: User) -> bool:
    return bool(user.is_active and primary_membership(user) is not None)


def _reference() -> str:
    return f"OM-{timezone.localdate().year}-{secrets.token_hex(4).upper()}"


def _status_label(status: str) -> str:
    return str(dict(CaseStatus.choices).get(status, status))


def _record_event(
    *,
    case: ProcessCase,
    actor: User,
    kind: str,
    from_status: str,
    message: str = "",
    details: Mapping[str, object] | None = None,
) -> ProcessEvent:
    return ProcessEvent.objects.create(
        case=case,
        actor=actor,
        kind=kind,
        from_status=from_status,
        to_status=case.status,
        message=message.strip(),
        details=dict(details or {}),
    )


def _save_case(case: ProcessCase, *, from_status: str) -> None:
    if from_status in TERMINAL_CASE_STATUSES:
        raise ValidationError("Un dossier terminé ne peut plus être modifié.")
    case.revision += 1
    case.save()


def _validate_people(
    *, initiator: User, mission_type: str, participant_ids: Iterable[int]
) -> list[User]:
    ids = set(participant_ids)
    ids.add(initiator.pk)
    people = list(User.objects.filter(pk__in=ids, is_active=True).order_by("pk"))
    if {person.pk for person in people} != ids:
        raise ValidationError(
            {"participant_ids": "Un participant est inactif ou inconnu."}
        )
    if mission_type == MissionType.INTERNATIONAL and ids != {initiator.pk}:
        raise ValidationError(
            {
                "participant_ids": "Une mission internationale concerne uniquement le demandeur."
            }
        )
    return people


@transaction.atomic
def create_mission_draft(
    *,
    actor: User,
    mission_type: str,
    destination: str,
    purpose: str,
    itinerary: str,
    transport_mode: str,
    transport_company: str,
    departure_date: date,
    return_date: date,
    funding_source: str,
    costs_covered: str,
    vehicle_required: bool,
    vehicle_details: str,
    participant_ids: Iterable[int],
) -> ProcessCase:
    """Create a self-initiated mission draft and its first audit event."""
    membership = primary_membership(actor)
    if not actor.is_active or membership is None:
        raise PermissionDenied("Une appartenance principale active est requise.")
    if mission_type not in MissionType.values:
        raise ValidationError({"mission_type": "Type de mission inconnu."})
    participants = _validate_people(
        initiator=actor, mission_type=mission_type, participant_ids=participant_ids
    )
    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    case = ProcessCase.objects.create(
        definition=mission_definition(),
        reference=_reference(),
        initiator=actor,
        origin_unit=membership.unit,
        origin_unit_name=membership.unit.long_name,
        calendar=calendar,
    )
    MissionOrder.objects.create(
        case=case,
        mission_type=mission_type,
        destination=destination.strip(),
        purpose=purpose.strip(),
        itinerary=itinerary.strip(),
        transport_mode=transport_mode.strip(),
        transport_company=transport_company.strip(),
        departure_date=departure_date,
        return_date=return_date,
        funding_source=funding_source.strip(),
        costs_covered=costs_covered.strip(),
        vehicle_required=vehicle_required,
        vehicle_details=vehicle_details.strip(),
    )
    MissionParticipant.objects.bulk_create(
        [
            MissionParticipant(
                case=case,
                user=person,
                name_snapshot=str(person),
                position_snapshot=person.position,
            )
            for person in participants
        ]
    )
    _record_event(
        case=case,
        actor=actor,
        kind="created",
        from_status="",
        message="Brouillon d'ordre de mission créé.",
    )
    return case


@transaction.atomic
def update_mission_draft(
    *,
    actor: User,
    case: ProcessCase,
    expected_revision: int,
    fields: Mapping[str, object],
    participant_ids: Iterable[int],
) -> ProcessCase:
    locked = (
        ProcessCase.objects.select_for_update()
        .select_related("mission_order")
        .get(pk=case.pk)
    )
    ensure_revision(locked.revision, expected_revision)
    draft_owner = locked.status == CaseStatus.DRAFT and locked.initiator_id == actor.pk
    preparation_actor = False
    if locked.status == CaseStatus.ASSISTANCE:
        item = _current_item(locked, locked=True)
        preparation_actor = bool(
            item.step == QueueKind.ASSISTANCE
            and item.claimed_by_id == actor.pk
            and can_work_queue(actor, item.queue)
        )
    if not draft_owner and not preparation_actor:
        raise PermissionDenied(
            "Seuls le demandeur au brouillon ou l'assistance chargée du dossier peuvent le modifier."
        )
    mission = locked.mission_order
    editable = {
        "mission_type",
        "destination",
        "purpose",
        "itinerary",
        "transport_mode",
        "transport_company",
        "departure_date",
        "return_date",
        "funding_source",
        "costs_covered",
        "vehicle_required",
        "vehicle_details",
        "official_number",
    }
    for name, value in fields.items():
        if name in editable:
            setattr(mission, name, value.strip() if isinstance(value, str) else value)
    participants = _validate_people(
        initiator=actor,
        mission_type=mission.mission_type,
        participant_ids=participant_ids,
    )
    mission.save()
    locked.mission_participants.all().delete()
    MissionParticipant.objects.bulk_create(
        [
            MissionParticipant(
                case=locked,
                user=person,
                name_snapshot=str(person),
                position_snapshot=person.position,
            )
            for person in participants
        ]
    )
    _save_case(locked, from_status=locked.status)
    _record_event(
        case=locked,
        actor=actor,
        kind="draft_updated" if draft_owner else "preparation_updated",
        from_status=locked.status,
        message=(
            "Brouillon mis à jour."
            if draft_owner
            else "Préparation de l'ordre de mission mise à jour."
        ),
    )
    return locked


def _coverage_distance(queue: ProcessQueue, origin_unit_id: int) -> int | None:
    if queue.coverage_unit_id == origin_unit_id:
        return 0
    if queue.coverage_scope == GrantScope.UNIT_ONLY:
        return None
    edges: dict[int, set[int]] = {}
    for parent_id, child_id in OrganizationUnitLink.objects.values_list(
        "supervisor_service_id", "collaborator_service_id"
    ):
        edges.setdefault(parent_id, set()).add(child_id)
    frontier: deque[tuple[int, int]] = deque([(queue.coverage_unit_id, 0)])
    visited: set[int] = set()
    while frontier:
        unit_id, distance = frontier.popleft()
        if unit_id in visited:
            continue
        visited.add(unit_id)
        for child_id in edges.get(unit_id, set()):
            if child_id == origin_unit_id:
                return distance + 1
            frontier.append((child_id, distance + 1))
    return None


def resolve_queue(case: ProcessCase, kind: str) -> ProcessQueue:
    candidates: list[tuple[int, ProcessQueue]] = []
    queues = ProcessQueue.objects.filter(
        definition=case.definition, kind=kind, active=True
    ).select_related("coverage_unit", "handler_unit", "role")
    for queue in queues:
        distance = _coverage_distance(queue, case.origin_unit_id)
        if distance is not None:
            candidates.append((distance, queue))
    if not candidates:
        raise ValidationError(
            {
                "queue": f"Aucune file {_status_label(kind)} ne couvre le service demandeur."
            }
        )
    best_distance = min(item[0] for item in candidates)
    best = [queue for distance, queue in candidates if distance == best_distance]
    if len(best) != 1:
        raise ValidationError(
            {"queue": "Plusieurs files de même précision couvrent ce dossier."}
        )
    return best[0]


def _workday_after(case: ProcessCase, count: int) -> date:
    cursor = timezone.localdate()
    remaining = count
    while remaining:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if case.calendar.is_working_day(cursor):
            remaining -= 1
    return cursor


def _new_work_item(case: ProcessCase, kind: str, days: int = 1) -> ProcessWorkItem:
    return ProcessWorkItem.objects.create(
        case=case,
        queue=resolve_queue(case, kind),
        step=kind,
        due_date=_workday_after(case, days),
    )


def _current_item(case: ProcessCase, *, locked: bool = False) -> ProcessWorkItem:
    queryset = case.work_items.filter(
        status__in=(WorkItemStatus.OPEN, WorkItemStatus.CLAIMED)
    ).select_related("queue", "queue__role", "claimed_by")
    if locked:
        queryset = queryset.select_for_update()
    item = queryset.order_by("-created_at", "-pk").first()
    if item is None:
        raise ValidationError("Ce dossier n'a pas d'action en attente.")
    return item


def can_work_queue(user: User, queue: ProcessQueue) -> bool:
    if not user.is_active:
        return False
    if user.is_superuser or user.is_it_admin:
        return True
    for grant in active_role_grants(user):
        if grant.role_id == queue.role_id and queue.handler_unit_id in units_in_scope(
            grant
        ):
            return True
    return False


def can_view_case(user: User, case: ProcessCase) -> bool:
    if not user.is_active:
        return False
    if user.is_superuser or user.is_it_admin or case.initiator_id == user.pk:
        return True
    if case.mission_participants.filter(user=user).exists():
        return True
    if has_scoped_permission(user, PROCESS_VIEW_PERMISSION, case.origin_unit_id):
        return True
    if (
        case.work_items.filter(claimed_by=user).exists()
        or case.events.filter(actor=user).exists()
    ):
        return True
    try:
        return can_work_queue(user, _current_item(case).queue)
    except ValidationError:
        return False


def can_download_documents(user: User, case: ProcessCase) -> bool:
    if user.is_superuser or user.is_it_admin or case.initiator_id == user.pk:
        return True
    if (
        case.work_items.filter(claimed_by=user).exists()
        or case.events.filter(actor=user).exists()
    ):
        return True
    if ProcessSignature.objects.filter(case=case, signer=user).exists():
        return True
    try:
        return can_work_queue(user, _current_item(case).queue)
    except ValidationError:
        return False


def can_export_case(user: User, case: ProcessCase) -> bool:
    if case.status not in TERMINAL_CASE_STATUSES:
        return False
    return bool(
        can_download_documents(user, case)
        and (
            user.is_superuser
            or user.is_it_admin
            or case.initiator_id == user.pk
            or has_scoped_permission(user, PROCESS_EXPORT_PERMISSION, case.origin_unit_id)
            or ProcessSignature.objects.filter(case=case, signer=user).exists()
        )
    )


def visible_cases(user: User) -> QuerySet[ProcessCase]:
    if user.is_superuser or user.is_it_admin:
        return ProcessCase.objects.all()
    unit_ids: set[int] = set()
    for grant in active_role_grants(user):
        if any(
            permission.codename == PROCESS_VIEW_PERMISSION
            and permission.content_type.app_label == "access"
            for permission in grant.role.group.permissions.all()
        ):
            unit_ids.update(units_in_scope(grant))
    queue_ids = [
        queue.pk
        for queue in ProcessQueue.objects.filter(active=True).select_related("role")
        if can_work_queue(user, queue)
    ]
    return ProcessCase.objects.filter(
        Q(initiator=user)
        | Q(mission_participants__user=user)
        | Q(origin_unit_id__in=unit_ids)
        | Q(work_items__claimed_by=user)
        | Q(work_items__queue_id__in=queue_ids)
        | Q(events__actor=user)
    ).distinct()


def _has_clean_document(case: ProcessCase, kind: str) -> bool:
    return case.documents.filter(
        kind=kind, scan_status=ScanStatus.CLEAN, replaced_by__isnull=True
    ).exists()


def _validate_submission(case: ProcessCase) -> None:
    mission = case.mission_order
    mission.full_clean()
    participant_ids = set(case.mission_participants.values_list("user_id", flat=True))
    if case.initiator_id not in participant_ids:
        raise ValidationError(
            {"participants": "Le demandeur doit participer à la mission."}
        )
    if mission.mission_type == MissionType.INTERNATIONAL and participant_ids != {
        case.initiator_id
    }:
        raise ValidationError(
            {"participants": "Une mission internationale ne peut avoir qu'un voyageur."}
        )
    if not _has_clean_document(case, DocumentKind.TERMS_OF_REFERENCE):
        raise ValidationError({"documents": "Les termes de référence sont obligatoires."})


def _validate_ready_for_signature(case: ProcessCase) -> None:
    _validate_submission(case)
    mission = case.mission_order
    if not _has_clean_document(case, DocumentKind.ORDER_DRAFT):
        raise ValidationError(
            {"documents": "Le projet d'ordre de mission PDF ou DOCX est obligatoire."}
        )
    if mission.mission_type == MissionType.INTERNATIONAL and not _has_clean_document(
        case, DocumentKind.TICKET
    ):
        raise ValidationError(
            {"documents": "Le billet est obligatoire avant la signature."}
        )


def _ensure_claimed_by(item: ProcessWorkItem, actor: User) -> None:
    if item.status != WorkItemStatus.CLAIMED or item.claimed_by_id != actor.pk:
        raise PermissionDenied("Prenez d'abord ce dossier en charge.")
    if not can_work_queue(actor, item.queue):
        raise PermissionDenied("Votre délégation n'autorise plus cette action.")


def _complete_item(item: ProcessWorkItem, note: str = "") -> None:
    item.status = WorkItemStatus.COMPLETED
    item.completed_at = timezone.now()
    item.completion_note = note.strip()
    item.save(update_fields=["status", "completed_at", "completion_note"])


def _close_case(case: ProcessCase, status: str) -> None:
    now = timezone.now()
    case.status = status
    case.current_step = status
    case.closed_at = now
    try:
        case.retention_until = now.date().replace(year=now.year + 3)
    except ValueError:
        case.retention_until = now.date().replace(year=now.year + 3, day=28)


def _canonical_signature(
    case: ProcessCase,
) -> tuple[dict[str, object], list[dict[str, object]], str]:
    mission = case.mission_order
    snapshot: dict[str, object] = {
        "reference": case.reference,
        "definition": f"{case.definition.code}:{case.definition.version}",
        "initiator_id": case.initiator_id,
        "origin_unit": {"id": case.origin_unit_id, "name": case.origin_unit_name},
        "mission": {
            "type": mission.mission_type,
            "destination": mission.destination,
            "purpose": mission.purpose,
            "itinerary": mission.itinerary,
            "transport_mode": mission.transport_mode,
            "transport_company": mission.transport_company,
            "departure_date": mission.departure_date.isoformat(),
            "return_date": mission.return_date.isoformat(),
            "funding_source": mission.funding_source,
            "costs_covered": mission.costs_covered,
            "vehicle_required": mission.vehicle_required,
            "vehicle_details": mission.vehicle_details,
            "official_number": mission.official_number,
        },
        "participants": [
            {
                "user_id": participant.user_id,
                "name": participant.name_snapshot,
                "position": participant.position_snapshot,
            }
            for participant in case.mission_participants.order_by("user_id")
        ],
    }
    manifest = [
        {
            "id": document.pk,
            "kind": document.kind,
            "name": document.original_name,
            "size": document.size,
            "sha256": document.sha256,
        }
        for document in case.documents.filter(
            scan_status=ScanStatus.CLEAN, replaced_by__isnull=True
        ).order_by("kind", "sha256", "pk")
    ]
    encoded = json.dumps(
        {"snapshot": snapshot, "documents": manifest},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return snapshot, manifest, hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def act_on_case(  # noqa: C901
    *,
    actor: User,
    case: ProcessCase,
    expected_revision: int,
    action: str,
    note: str = "",
    confirmation: str = "",
    checklist: Mapping[str, bool] | None = None,
) -> ProcessCase:
    """Execute one authorized transition against a locked current revision."""
    locked = (
        ProcessCase.objects.select_for_update()
        .select_related("definition", "calendar", "mission_order", "origin_unit")
        .get(pk=case.pk)
    )
    ensure_revision(locked.revision, expected_revision)
    before = locked.status
    if action in {"place_legal_hold", "release_legal_hold"}:
        if not actor.is_superuser and not actor.is_it_admin:
            raise PermissionDenied(
                "Seul un administrateur autorisé peut gérer le gel juridique."
            )
        if not note.strip():
            raise ValidationError({"note": "Le motif est obligatoire."})
        enabled = action == "place_legal_hold"
        locked.legal_hold = enabled
        locked.legal_hold_reason = note.strip() if enabled else ""
        locked.revision += 1
        locked.save()
        _record_event(
            case=locked,
            actor=actor,
            kind=action,
            from_status=before,
            message=note,
            details={"legal_hold": enabled},
        )
        return locked
    if before in TERMINAL_CASE_STATUSES:
        raise ValidationError("Un dossier terminé ne peut plus être modifié.")
    if action in ACTION_NOTES_REQUIRED and not note.strip():
        raise ValidationError({"note": "Le motif est obligatoire."})

    if action == "submit":
        if before != CaseStatus.DRAFT or locked.initiator_id != actor.pk:
            raise PermissionDenied("Seul le demandeur peut soumettre son brouillon.")
        _validate_submission(locked)
        days = 2 if locked.mission_order.mission_type == MissionType.INTERNATIONAL else 1
        _new_work_item(locked, QueueKind.ASSISTANCE, days)
        locked.status = CaseStatus.ASSISTANCE
        locked.current_step = QueueKind.ASSISTANCE
        locked.submitted_at = timezone.now()
    elif action == "abandon":
        if before != CaseStatus.DRAFT or locked.initiator_id != actor.pk:
            raise PermissionDenied("Seul le demandeur peut abandonner son brouillon.")
        _close_case(locked, CaseStatus.ABANDONED)
    elif action in {"claim", "takeover"}:
        item = _current_item(locked, locked=True)
        if not can_work_queue(actor, item.queue):
            raise PermissionDenied("Vous n'appartenez pas à cette file de service.")
        if action == "claim" and item.claimed_by_id not in (None, actor.pk):
            raise ValidationError("Ce dossier est déjà pris en charge.")
        previous_actor = item.claimed_by_id
        item.status = WorkItemStatus.CLAIMED
        item.claimed_by = actor
        item.claimed_at = timezone.now()
        item.save(update_fields=["status", "claimed_by", "claimed_at"])
        _save_case(locked, from_status=before)
        _record_event(
            case=locked,
            actor=actor,
            kind=action,
            from_status=before,
            message=note or "Dossier pris en charge.",
            details={"previous_actor_id": previous_actor},
        )
        return locked
    elif action == "send_to_signature":
        if before != CaseStatus.ASSISTANCE:
            raise ValidationError("Le dossier n'est pas en préparation.")
        item = _current_item(locked, locked=True)
        _ensure_claimed_by(item, actor)
        _validate_ready_for_signature(locked)
        _complete_item(item, note)
        _new_work_item(locked, QueueKind.SIGNATURE)
        locked.status = CaseStatus.SIGNATURE
        locked.current_step = QueueKind.SIGNATURE
    elif action in {"request_correction", "reject", "sign"}:
        if before != CaseStatus.SIGNATURE:
            raise ValidationError("Le dossier n'attend pas la décision du DG.")
        item = _current_item(locked, locked=True)
        _ensure_claimed_by(item, actor)
        if action == "request_correction":
            _complete_item(item, note)
            _new_work_item(locked, QueueKind.ASSISTANCE)
            locked.status = CaseStatus.ASSISTANCE
            locked.current_step = QueueKind.ASSISTANCE
        elif action == "reject":
            _complete_item(item, note)
            _close_case(locked, CaseStatus.REJECTED)
        else:
            _validate_ready_for_signature(locked)
            expected = f"SIGNER {locked.reference}"
            if confirmation != expected:
                raise ValidationError(
                    {"confirmation": f"Saisissez exactement : {expected}"}
                )
            snapshot, manifest, digest = _canonical_signature(locked)
            _complete_item(item, note)
            _new_work_item(locked, QueueKind.DISTRIBUTION)
            locked.status = CaseStatus.DISTRIBUTION
            locked.current_step = QueueKind.DISTRIBUTION
            _save_case(locked, from_status=before)
            event = _record_event(
                case=locked,
                actor=actor,
                kind="sign",
                from_status=before,
                message=note or "Ordre de mission signé dans l'application.",
                details={"snapshot_sha256": digest},
            )
            ProcessSignature.objects.create(
                case=locked,
                signer=actor,
                event=event,
                confirmation=confirmation,
                snapshot=snapshot,
                snapshot_sha256=digest,
                document_manifest=manifest,
            )
            return locked
    elif action == "complete_distribution":
        if before != CaseStatus.DISTRIBUTION:
            raise ValidationError("Le dossier n'est pas en distribution.")
        required = {"accounting_copy", "original_delivered", "archive_copy"}
        values = dict(checklist or {})
        if not all(values.get(key) is True for key in required):
            raise ValidationError(
                {"checklist": "Les trois opérations de distribution sont obligatoires."}
            )
        item = _current_item(locked, locked=True)
        _ensure_claimed_by(item, actor)
        _complete_item(item, note)
        if locked.mission_order.vehicle_required:
            _new_work_item(locked, QueueKind.FLEET)
            locked.status = CaseStatus.FLEET
            locked.current_step = QueueKind.FLEET
        else:
            _close_case(locked, CaseStatus.COMPLETED)
    elif action == "complete_fleet":
        if before != CaseStatus.FLEET:
            raise ValidationError("Le dossier n'attend pas le parc automobile.")
        item = _current_item(locked, locked=True)
        _ensure_claimed_by(item, actor)
        _complete_item(item, note)
        _close_case(locked, CaseStatus.COMPLETED)
    else:
        raise ValidationError({"action": "Action inconnue."})

    _save_case(locked, from_status=before)
    _record_event(
        case=locked,
        actor=actor,
        kind=action,
        from_status=before,
        message=note,
        details=dict(checklist or {}),
    )
    return locked


def can_upload_document(user: User, case: ProcessCase) -> bool:
    if case.status in TERMINAL_CASE_STATUSES:
        return False
    if case.status == CaseStatus.DRAFT:
        return case.initiator_id == user.pk
    if case.status != CaseStatus.ASSISTANCE:
        return False
    try:
        item = _current_item(case)
    except ValidationError:
        return False
    return item.claimed_by_id == user.pk and can_work_queue(user, item.queue)


def _matches_declared_format(content: bytes, suffix: str) -> bool:
    if suffix == ".pdf":
        return content.startswith(b"%PDF-")
    if suffix == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if suffix == ".docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
        except (BadZipFile, OSError):
            return False
        return "[Content_Types].xml" in names and any(
            name.startswith("word/") for name in names
        )
    return False


def can_edit_mission(user: User, case: ProcessCase) -> bool:
    if case.status == CaseStatus.DRAFT:
        return case.initiator_id == user.pk
    if case.status != CaseStatus.ASSISTANCE:
        return False
    try:
        item = _current_item(case)
    except ValidationError:
        return False
    return bool(
        item.step == QueueKind.ASSISTANCE
        and item.claimed_by_id == user.pk
        and can_work_queue(user, item.queue)
    )


@transaction.atomic
def add_document(
    *,
    actor: User,
    case: ProcessCase,
    kind: str,
    name: str,
    content_type: str,
    content: bytes,
    expected_revision: int,
    storage: DocumentStorage | None = None,
    scanner: MalwareScanner | None = None,
) -> ProcessDocument:
    locked = ProcessCase.objects.select_for_update().get(pk=case.pk)
    ensure_revision(locked.revision, expected_revision)
    if not can_upload_document(actor, locked):
        raise PermissionDenied("Vous ne pouvez pas ajouter de pièce à ce dossier.")
    if kind not in DocumentKind.values:
        raise ValidationError({"kind": "Type de pièce inconnu."})
    suffix = Path(name).suffix.lower()
    if content_type not in ALLOWED_CONTENT_TYPES or suffix not in ALLOWED_SUFFIXES:
        raise ValidationError({"file": "Formats acceptés : PDF, DOCX, JPG et PNG."})
    if not content or len(content) > int(settings.PROCESS_DOCUMENT_MAX_BYTES):
        raise ValidationError({"file": "La pièce doit peser au maximum 20 Mio."})
    if not _matches_declared_format(content, suffix):
        raise ValidationError(
            {"file": "Le contenu du fichier ne correspond pas à son format déclaré."}
        )
    scan = (scanner or configured_scanner()).scan(content)
    if not scan.clean:
        raise ValidationError({"file": "La pièce a été refusée par l'antivirus."})
    selected_storage = storage or configured_storage()
    key = selected_storage.save(
        case_reference=locked.reference, name=name, content=content
    )
    try:
        document = ProcessDocument.objects.create(
            case=locked,
            kind=kind,
            provider=selected_storage.provider,
            object_key=key,
            original_name=Path(name).name[:255],
            content_type=content_type,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            scan_status=ScanStatus.CLEAN,
            scan_details=scan.details,
            uploaded_by=actor,
        )
        previous = (
            ProcessDocument.objects.filter(
                case=locked, kind=kind, replaced_by__isnull=True
            )
            .exclude(pk=document.pk)
            .order_by("-created_at", "-pk")
            .first()
        )
        if previous is not None:
            ProcessDocument.objects.filter(pk=previous.pk).update(replaced_by=document)
        _save_case(locked, from_status=locked.status)
        _record_event(
            case=locked,
            actor=actor,
            kind="document_uploaded",
            from_status=locked.status,
            message=f"Pièce ajoutée : {document.original_name}",
            details={
                "document_id": document.pk,
                "sha256": document.sha256,
                "replaces_document_id": previous.pk if previous else None,
            },
        )
        return document
    except Exception:
        selected_storage.delete(key)
        raise


def document_bytes(document: ProcessDocument) -> bytes:
    storage = configured_storage()
    if storage.provider != document.provider:
        raise ValidationError("Le fournisseur configuré ne correspond pas à cette pièce.")
    return storage.read(document.object_key)
