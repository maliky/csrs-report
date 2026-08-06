"""Transactional agenda writes and deterministic weekly aggregation."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max, Q, QuerySet
from django.utils import timezone

from accounts.models import User
from access.services import (
    AGENDA_PREPARE_PERMISSION,
    AGENDA_VIEW_PERMISSION,
    AVAILABILITY_PERMISSION,
    VISITOR_PERMISSION,
    has_active_permission,
)
from agenda.models import (
    AvailabilityKind,
    StaffAvailability,
    VisitorVisit,
    WeeklyAgendaDraft,
    WeeklyAgendaVersion,
)
from processes.storage import configured_storage
from work.models import OrganizationMembership, TaskAssignment
from work.services import (
    ReportingPeriod,
    StaleRevisionError,
    assignment_snapshot,
    ensure_revision,
    week_start_for,
)


def normalize_week(value: date) -> date:
    return week_start_for(value)


def can_manage_visits(user: User) -> bool:
    return has_active_permission(user, VISITOR_PERMISSION)


def can_manage_availability(user: User) -> bool:
    return has_active_permission(user, AVAILABILITY_PERMISSION)


def can_prepare_agenda(user: User) -> bool:
    return has_active_permission(user, AGENDA_PREPARE_PERMISSION)


def can_view_agenda(user: User) -> bool:
    return can_prepare_agenda(user) or has_active_permission(user, AGENDA_VIEW_PERMISSION)


def _ensure(permission: bool, message: str) -> None:
    if not permission:
        raise PermissionDenied(message)


@transaction.atomic
def create_visit(
    *, actor: User, party_size: int, visitor_names: list[str]
) -> VisitorVisit:
    _ensure(can_manage_visits(actor), "Vous ne pouvez pas enregistrer de visite.")
    visit = VisitorVisit(
        party_size=party_size,
        visitor_names=visitor_names,
        recorded_by=actor,
        updated_by=actor,
    )
    visit.save()
    return visit


@transaction.atomic
def mark_visit_departed(
    *, actor: User, visit: VisitorVisit, expected_revision: int
) -> VisitorVisit:
    _ensure(can_manage_visits(actor), "Vous ne pouvez pas enregistrer ce départ.")
    locked = VisitorVisit.objects.select_for_update().get(pk=visit.pk)
    ensure_revision(locked.revision, expected_revision)
    if locked.cancelled_at:
        raise ValidationError("Cette visite est annulée.")
    if locked.departed_at:
        return locked
    locked.departed_at = max(timezone.now(), locked.arrived_at)
    locked.updated_by = actor
    locked.revision += 1
    locked.save(update_fields=["departed_at", "updated_by", "revision", "updated_at"])
    return locked


@transaction.atomic
def create_availability(
    *,
    actor: User,
    employee: User,
    kind: str,
    start_date: date,
    end_date: date,
    note: str,
) -> StaffAvailability:
    _ensure(
        can_manage_availability(actor),
        "Vous ne pouvez pas enregistrer d’indisponibilité.",
    )
    if kind not in AvailabilityKind.values:
        raise ValidationError({"kind": "Type d’indisponibilité inconnu."})
    item = StaffAvailability(
        employee=employee,
        kind=kind,
        start_date=start_date,
        end_date=end_date,
        note=note.strip(),
        recorded_by=actor,
        updated_by=actor,
    )
    item.save()
    return item


@transaction.atomic
def update_availability(
    *,
    actor: User,
    item: StaffAvailability,
    expected_revision: int,
    kind: str,
    start_date: date,
    end_date: date,
    note: str,
) -> StaffAvailability:
    _ensure(
        can_manage_availability(actor),
        "Vous ne pouvez pas modifier cette indisponibilité.",
    )
    locked = StaffAvailability.objects.select_for_update().get(pk=item.pk)
    ensure_revision(locked.revision, expected_revision)
    if locked.cancelled_at:
        raise ValidationError("Cette indisponibilité est annulée.")
    locked.kind = kind
    locked.start_date = start_date
    locked.end_date = end_date
    locked.note = note.strip()
    locked.updated_by = actor
    locked.revision += 1
    locked.save()
    return locked


@transaction.atomic
def cancel_availability(
    *, actor: User, item: StaffAvailability, expected_revision: int, reason: str
) -> StaffAvailability:
    _ensure(
        can_manage_availability(actor),
        "Vous ne pouvez pas annuler cette indisponibilité.",
    )
    locked = StaffAvailability.objects.select_for_update().get(pk=item.pk)
    ensure_revision(locked.revision, expected_revision)
    if locked.cancelled_at:
        return locked
    if not reason.strip():
        raise ValidationError({"reason": "Le motif est obligatoire."})
    locked.cancelled_at = timezone.now()
    locked.cancellation_reason = reason.strip()
    locked.updated_by = actor
    locked.revision += 1
    locked.save()
    return locked


@transaction.atomic
def save_draft(
    *, actor: User, week_start: date, major_events: str, expected_revision: int | None
) -> WeeklyAgendaDraft:
    _ensure(can_prepare_agenda(actor), "Vous ne pouvez pas préparer cet agenda.")
    monday = normalize_week(week_start)
    draft = (
        WeeklyAgendaDraft.objects.select_for_update().filter(week_start=monday).first()
    )
    if draft is None:
        if expected_revision not in (None, 0):
            raise StaleRevisionError(0)
        return WeeklyAgendaDraft.objects.create(
            week_start=monday,
            major_events=major_events.strip(),
            updated_by=actor,
        )
    ensure_revision(draft.revision, expected_revision)
    draft.major_events = major_events.strip()
    draft.updated_by = actor
    draft.revision += 1
    draft.save()
    return draft


def _local_bounds(monday: date) -> tuple[datetime, datetime]:
    zone = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(monday, time.min), zone),
        timezone.make_aware(datetime.combine(monday + timedelta(days=6), time.max), zone),
    )


def _person(user: User) -> dict[str, object]:
    return {"id": user.pk, "name": str(user), "position": user.position}


def build_week_snapshot(*, week_start: date, major_events: str = "") -> dict[str, object]:
    """Aggregate only active work and explicitly entered weekly context."""
    monday = normalize_week(week_start)
    sunday = monday + timedelta(days=6)
    start_at, end_at = _local_bounds(monday)
    visits = VisitorVisit.objects.filter(cancelled_at__isnull=True).filter(
        Q(arrived_at__range=(start_at, end_at)) | Q(departed_at__range=(start_at, end_at))
    )
    arrivals = visits.filter(arrived_at__range=(start_at, end_at))
    departures = visits.filter(departed_at__range=(start_at, end_at))

    availability = (
        StaffAvailability.objects.filter(
            cancelled_at__isnull=True,
            start_date__lte=sunday,
            end_date__gte=monday,
        )
        .select_related("employee")
        .order_by("kind", "start_date", "employee__last_name", "employee__first_name")
    )

    assignments = list(
        TaskAssignment.objects.filter(employee__is_active=True)
        .filter(
            Q(start_date__lte=sunday)
            & (Q(completed_at__isnull=True) | Q(completed_at__date__gte=monday))
            | Q(progress_entries__entry_date__range=(monday, sunday))
            | Q(activities__occurred_at__date__range=(monday, sunday))
        )
        .select_related("task", "employee", "manager", "organization_unit", "calendar")
        .prefetch_related("progress_entries", "activities__actor")
        .distinct()
    )
    employee_ids = {assignment.employee_id for assignment in assignments}
    memberships: dict[int, OrganizationMembership] = {}
    for membership in (
        OrganizationMembership.objects.filter(
            user_id__in=employee_ids,
            is_primary=True,
            start_date__lte=sunday,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=sunday))
        .select_related("unit")
        .order_by("user_id", "-start_date", "-pk")
    ):
        memberships.setdefault(membership.user_id, membership)

    period = ReportingPeriod("week", monday, sunday)
    grouped: dict[int, dict[str, object]] = {}
    employee_rows: dict[tuple[int, int], dict[str, object]] = {}
    for assignment in assignments:
        employee_membership = memberships.get(assignment.employee_id)
        unit = (
            employee_membership.unit
            if employee_membership
            else assignment.organization_unit
        )
        if unit is None:
            continue
        unit_row = grouped.setdefault(
            unit.pk,
            {
                "id": unit.pk,
                "code": unit.code,
                "name": unit.long_name,
                "display_order": unit.display_order,
                "employees": [],
            },
        )
        employee_key = (unit.pk, assignment.employee_id)
        employee_row = employee_rows.get(employee_key)
        if employee_row is None:
            employee_row = {
                "person": _person(assignment.employee),
                "completion_rate": 0,
                "tasks": [],
            }
            employee_rows[employee_key] = employee_row
            cast(list[dict[str, object]], unit_row["employees"]).append(employee_row)
        summary = assignment_snapshot(assignment, period)
        weekly_comments = [
            item
            for item in summary.comments
            if monday <= timezone.localtime(item.occurred_at).date() <= sunday
        ]
        observation = weekly_comments[0].message if weekly_comments else ""
        cast(list[dict[str, object]], employee_row["tasks"]).append(
            {
                "id": assignment.pk,
                "title": assignment.task.title,
                "status": summary.status,
                "status_label": summary.status_label,
                "percentage": summary.percentage,
                "progress_delta": summary.progress_delta,
                "observation": observation,
            }
        )

    for unit_data in grouped.values():
        employees = cast(list[dict[str, object]], unit_data["employees"])
        employees.sort(
            key=lambda row: str(cast(dict[str, object], row["person"])["name"])
        )
        for employee in employees:
            tasks = cast(list[dict[str, object]], employee["tasks"])
            tasks.sort(key=lambda row: str(row["title"]))
            average = Decimal(
                sum(cast(int, task["percentage"]) for task in tasks)
            ) / Decimal(len(tasks))
            employee["completion_rate"] = int(
                average.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )

    def visit_rows(queryset: QuerySet[VisitorVisit]) -> list[dict[str, object]]:
        return [
            {
                "id": visit.pk,
                "party_size": visit.party_size,
                "visitor_names": visit.visitor_names,
                "arrived_at": visit.arrived_at.isoformat(),
                "departed_at": visit.departed_at.isoformat()
                if visit.departed_at
                else None,
            }
            for visit in queryset
        ]

    return {
        "schema_version": 1,
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "major_events": major_events.strip(),
        "arrivals": visit_rows(arrivals),
        "departures": visit_rows(departures),
        "availability": [
            {
                "id": item.pk,
                "kind": item.kind,
                "kind_label": item.get_kind_display(),
                "employee": _person(item.employee),
                "start_date": item.start_date.isoformat(),
                "end_date": item.end_date.isoformat(),
                "note": item.note,
            }
            for item in availability
        ],
        "units": sorted(
            grouped.values(),
            key=lambda row: (cast(int, row["display_order"]), str(row["name"])),
        ),
    }


def snapshot_digest(snapshot: dict[str, object]) -> str:
    canonical = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


@transaction.atomic
def generate_agenda(*, actor: User, week_start: date) -> WeeklyAgendaVersion:
    _ensure(can_prepare_agenda(actor), "Vous ne pouvez pas générer cet agenda.")
    monday = normalize_week(week_start)
    draft, _created = WeeklyAgendaDraft.objects.select_for_update().get_or_create(
        week_start=monday, defaults={"updated_by": actor}
    )
    snapshot = build_week_snapshot(week_start=monday, major_events=draft.major_events)
    generated_at = timezone.now()
    next_version = (
        WeeklyAgendaVersion.objects.filter(week_start=monday).aggregate(Max("version"))[
            "version__max"
        ]
        or 0
    ) + 1
    from agenda.pdf import render_weekly_agenda_pdf

    pdf = render_weekly_agenda_pdf(
        snapshot, generated_at=generated_at, version=next_version
    )
    storage = configured_storage()
    key = storage.save(
        case_reference=f"agenda-{monday.isoformat()}",
        name=f"agenda-{monday.isoformat()}-v{next_version}.pdf",
        content=pdf,
    )
    try:
        return WeeklyAgendaVersion.objects.create(
            draft=draft,
            week_start=monday,
            version=next_version,
            snapshot=snapshot,
            snapshot_sha256=snapshot_digest(snapshot),
            storage_provider=storage.provider,
            storage_key=key,
            pdf_sha256=sha256(pdf).hexdigest(),
            pdf_size=len(pdf),
            generated_by=actor,
            generated_at=generated_at,
        )
    except Exception:
        storage.delete(key)
        raise


def agenda_pdf_bytes(version: WeeklyAgendaVersion) -> bytes:
    storage = configured_storage()
    if storage.provider != version.storage_provider:
        raise ValidationError(
            "Le fournisseur de stockage de cette version est indisponible."
        )
    return storage.read(version.storage_key)
