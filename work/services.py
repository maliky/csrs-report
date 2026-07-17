"""Typed functional domain services for CSRS Report."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from math import ceil
from statistics import mean, median
from typing import Iterable, Iterator, TypeAlias, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify

from access.services import (
    MANAGE_PERMISSION,
    PROPOSAL_PERMISSION,
    VIEW_PERMISSION,
    has_scoped_permission,
    member_user_ids,
    primary_membership,
    scoped_unit_ids,
)
from accounts.models import User
from work.models import (
    AssignmentStatus,
    ActivityKind,
    Holiday,
    InstitutionalAction,
    OrganizationMembership,
    ProgressEntry,
    ProposalStatus,
    ReportingLine,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskCodeSequence,
    TaskProposal,
    WorkCalendar,
)

ACTIVE_STATES = (
    AssignmentStatus.PLANNED,
    AssignmentStatus.ACTIVE,
    AssignmentStatus.AWAITING_VALIDATION,
)
DecimalPairT: TypeAlias = tuple[Decimal, Decimal]


@dataclass(frozen=True)
class Projection:
    """Remaining-work projection for one assignment."""

    current_percentage: int
    baseline_days: Decimal
    observed_days: Decimal | None

    @property
    def effective_days(self) -> Decimal:
        return (
            self.observed_days if self.observed_days is not None else self.baseline_days
        )


@dataclass(frozen=True)
class WorkloadBreakdown:
    """Proportional workload split displayed consistently across the UI."""

    total_days: Decimal
    completed_days: Decimal
    remaining_days: Decimal


@dataclass(frozen=True)
class ProgressPoint:
    """One progression value positioned on a business-day axis."""

    workday_offset: int
    percentage: int
    entry_date: date
    observed: bool = True


@dataclass(frozen=True)
class DailyProgressRow:
    """One calendar-day row exposed to charts and authenticated JSON clients."""

    task_id: int
    start_date: date
    day: date
    is_working_day: bool
    due_date: date
    planned_work_days: Decimal
    elapsed_work_days: int
    remaining_schedule_days: Decimal
    overdue_days: Decimal
    percentage: int
    observed: bool

    def as_json(self) -> dict[str, object]:
        """Return a stable, privacy-minimal JSON representation."""
        payload = asdict(self)
        for key in ("start_date", "day", "due_date"):
            payload[key] = cast(date, payload[key]).isoformat()
        for key in (
            "planned_work_days",
            "remaining_schedule_days",
            "overdue_days",
        ):
            payload[key] = float(cast(Decimal, payload[key]))
        return payload


class DeadlineLevel(StrEnum):
    """Visual urgency derived from the consumed assignment schedule."""

    NORMAL = "normal"
    ATTENTION = "attention"
    WARNING = "warning"
    URGENT = "urgent"
    OVERDUE = "overdue"
    COMPLETED = "completed"


@dataclass(frozen=True)
class TaskProgressSeries:
    """Compact per-task progression profile for the team dashboard."""

    assignment: TaskAssignment
    points: tuple[ProgressPoint, ...]
    today: date
    observation_count: int
    planned_days: Decimal
    displayed_days: Decimal
    overrun_days: Decimal
    percentage: int
    workload: WorkloadBreakdown
    action_key: str
    deadline_level: DeadlineLevel
    blocked: bool
    late: bool
    missing_update: bool


@dataclass(frozen=True)
class EmployeeSummary:
    """One row in a direct-team period dashboard."""

    employee: User
    task_count: int
    mean_progress: Decimal
    median_progress: Decimal
    remaining_total: Decimal
    remaining_mean: Decimal
    blocked_count: int
    late_count: int
    missing_update_count: int
    progress_delta: Decimal = Decimal("0.00")
    trend: tuple["WeeklyTrendPoint", ...] = ()
    task_series: tuple[TaskProgressSeries, ...] = ()


@dataclass(frozen=True)
class TeamNode:
    """One recursively expandable collaborator in the organization tree."""

    summary: EmployeeSummary
    children: tuple["TeamNode", ...]


@dataclass(frozen=True)
class TeamNodeOverview:
    """Lightweight hierarchy node that never calculates chart series."""

    employee: User
    task_count: int
    children: tuple["TeamNodeOverview", ...]


@dataclass(frozen=True)
class WeeklyTrendPoint:
    """Mean employee progress at one week-end within a reporting period."""

    end_date: date
    mean_progress: Decimal


@dataclass(frozen=True)
class ReportingPeriod:
    """A normalized week or calendar month used by reporting views.

    Attributes:
        kind: Either ``week`` or ``month``.
        start: Inclusive first date.
        end: Inclusive last date.

    """

    kind: str
    start: date
    end: date

    @property
    def query(self) -> str:
        """Return the canonical query string without a leading question mark."""
        if self.kind == "month":
            return f"month={self.start:%Y-%m}"
        return f"week={self.start:%Y-%m-%d}"

    @property
    def label(self) -> str:
        """Return a concise French period label."""
        if self.kind == "month":
            month_names = (
                "janvier",
                "fevrier",
                "mars",
                "avril",
                "mai",
                "juin",
                "juillet",
                "aout",
                "septembre",
                "octobre",
                "novembre",
                "decembre",
            )
            return f"{month_names[self.start.month - 1]} {self.start.year}"
        return f"semaine du {self.start:%d/%m/%Y}"


@dataclass(frozen=True)
class AssignmentSnapshot:
    """Read-only assignment indicators at the end of a reporting period."""

    assignment: TaskAssignment
    percentage: int
    status: str
    status_label: str
    progress_delta: int
    projection: Projection
    workload: WorkloadBreakdown
    deadline_level: DeadlineLevel
    latest: ProgressEntry | None
    comments: tuple[TaskActivity, ...]


@dataclass(frozen=True)
class ActivityFeedItem:
    """One visible activity paired with the author's service short name."""

    activity: TaskActivity
    actor_short_name: str


def week_start_for(day: date) -> date:
    """Return the Monday containing day."""
    return day - timedelta(days=day.weekday())


def reporting_period(*, week: str = "", month: str = "", today: date) -> ReportingPeriod:
    """Parse reporting query values, preferring a valid calendar month.

    Args:
        week: ISO date located anywhere in the requested week.
        month: Calendar month formatted as ``YYYY-MM``.
        today: Fallback date, passed explicitly to keep the function deterministic.

    Returns:
        A normalized inclusive reporting period.

    """
    if month:
        try:
            start = date.fromisoformat(f"{month}-01")
            return ReportingPeriod(
                "month", start, start.replace(day=monthrange(start.year, start.month)[1])
            )
        except ValueError:
            pass
    if week:
        try:
            monday = week_start_for(date.fromisoformat(week))
            return ReportingPeriod("week", monday, monday + timedelta(days=6))
        except ValueError:
            pass
    monday = week_start_for(today)
    return ReportingPeriod("week", monday, monday + timedelta(days=6))


def adjacent_period(period: ReportingPeriod, direction: int) -> ReportingPeriod:
    """Return the previous or next period of the same kind."""
    if period.kind == "week":
        start = period.start + timedelta(days=7 * direction)
        return ReportingPeriod("week", start, start + timedelta(days=6))
    boundary = (
        period.start - timedelta(days=1)
        if direction < 0
        else period.end + timedelta(days=1)
    )
    start = boundary.replace(day=1)
    return ReportingPeriod(
        "month", start, start.replace(day=monthrange(start.year, start.month)[1])
    )


def holiday_days(start: date, end: date) -> set[date]:
    """Return configured holidays in an inclusive interval."""
    return set(
        Holiday.objects.filter(day__range=(start, end)).values_list("day", flat=True)
    )


def business_days_between(
    start: date, end: date, calendar: WorkCalendar | None = None
) -> int:
    """Count workdays after start through end using a retained calendar.

    The optional calendar-free path is kept for old reports and treats ``Holiday``
    as the legacy global calendar. New assignments always pass their version.
    """
    if end <= start:
        return 0
    if calendar is not None:
        return calendar.workdays_between(start, end)
    holidays = holiday_days(start, end)
    cursor = start + timedelta(days=1)
    total = 0
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in holidays:
            total += 1
        cursor += timedelta(days=1)
    return total


def due_date_for(start: date, workload: Decimal, calendar: WorkCalendar) -> date:
    """Calculate the due workday, rounding decimal workloads upward."""
    return calendar.due_date_for(start, workload)


def workload_for(start: date, due: date, calendar: WorkCalendar) -> Decimal:
    """Calculate the whole working-day duration represented by a due date."""
    return Decimal(calendar.workdays_between(start, due)).quantize(Decimal("0.1"))


def iter_calendar_days(start: date, end: date) -> Iterator[date]:
    """Yield every calendar day inclusively without persisting synthetic rows."""
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def daily_progress_rows(
    assignment: TaskAssignment, *, today: date | None = None
) -> tuple[DailyProgressRow, ...]:
    """Derive the full daily chart series from real progress observations.

    Every calendar day states whether it is worked. Missing observations carry
    the last known percentage and are explicitly marked as unobserved. Open work
    extends to the true current day; closed work stops at ``completed_at``.
    """
    return daily_progress_rows_from_entries(
        assignment,
        assignment.progress_entries.all(),
        today=today or timezone.localdate(),
    )


def progress_series_end_date(assignment: TaskAssignment, today: date) -> date:
    """Return the last calendar day represented by an assignment series."""
    end = (
        min(today, assignment.completed_at.date())
        if assignment.completed_at is not None
        else today
    )
    return max(assignment.start_date, end)


def daily_progress_rows_from_entries(
    assignment: TaskAssignment,
    progress_entries: Iterable[ProgressEntry],
    *,
    today: date,
) -> tuple[DailyProgressRow, ...]:
    """Build a daily series from an explicit collection of persisted entries.

    This pure-data boundary lets aggregate exports prefetch every progression in
    one query while the regular task route keeps the same public behavior.

    Args:
        assignment: Assignment providing dates, workload, and retained calendar.
        progress_entries: Persisted observations available to the caller.
        today: True current day used to stop an open assignment.

    Returns:
        Calendar-day rows with work status and carried values marked unobserved.

    """
    end = progress_series_end_date(assignment, today)
    entries = {
        item.entry_date: item
        for item in sorted(
            (
                item
                for item in progress_entries
                if assignment.start_date <= item.entry_date <= end
            ),
            key=lambda item: (item.entry_date, item.updated_at),
        )
    }
    calendar_overrides = {
        item.day: item.is_working_day for item in assignment.calendar.days.all()
    }
    percentage = 0
    elapsed = 0
    rows: list[DailyProgressRow] = []
    due_offset = Decimal(ceil(assignment.estimated_work_days))
    for day in iter_calendar_days(assignment.start_date, end):
        is_working_day = calendar_overrides.get(day, day.weekday() < 5)
        if day > assignment.start_date and is_working_day:
            elapsed += 1
        entry = entries.get(day)
        if entry is not None:
            percentage = entry.percentage
        elapsed_decimal = Decimal(elapsed)
        rows.append(
            DailyProgressRow(
                task_id=assignment.pk,
                start_date=assignment.start_date,
                day=day,
                is_working_day=is_working_day,
                due_date=assignment.due_date,
                planned_work_days=assignment.estimated_work_days,
                elapsed_work_days=elapsed,
                remaining_schedule_days=max(
                    Decimal("0.0"), assignment.estimated_work_days - elapsed_decimal
                ),
                overdue_days=max(Decimal("0.0"), elapsed_decimal - due_offset),
                percentage=percentage,
                observed=entry is not None,
            )
        )
    return tuple(rows)


def current_progress(assignment: TaskAssignment, until: date | None = None) -> int:
    """Return the latest percentage, optionally limited to a date."""
    entries = assignment.progress_entries.all()
    if until:
        entries = entries.filter(entry_date__lte=until)
    entry = entries.order_by("-entry_date", "-updated_at").first()
    return entry.percentage if entry else 0


def effective_assignment_status(status: str, percentage: int) -> str:
    """Return a user-visible status coherent with the latest progression.

    Args:
        status: Persisted ``TaskAssignment`` status.
        percentage: Latest progress known for the requested reporting boundary.

    Returns:
        ``active`` instead of an impossible ``completed`` status below 100 percent.

    """
    if status == AssignmentStatus.COMPLETED and percentage < 100:
        return AssignmentStatus.ACTIVE
    return status


def assignment_status_label(status: str) -> str:
    """Return the French label for a normalized assignment status."""
    return str(dict(AssignmentStatus.choices)[status])


def workload_breakdown(total_days: Decimal, percentage: int) -> WorkloadBreakdown:
    """Split a workload proportionally using one shared calculation."""
    bounded = max(0, min(100, percentage))
    completed = (total_days * Decimal(bounded) / Decimal(100)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    remaining = (total_days - completed).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return WorkloadBreakdown(total_days, completed, remaining)


def deadline_level(
    assignment: TaskAssignment, *, on_day: date, percentage: int
) -> DeadlineLevel:
    """Classify deadline urgency using 50, 75 and 90 percent schedule thresholds."""
    if percentage == 100:
        return DeadlineLevel.COMPLETED
    if on_day > assignment.due_date:
        return DeadlineLevel.OVERDUE
    if on_day <= assignment.start_date:
        return DeadlineLevel.NORMAL
    total = max(
        1,
        business_days_between(
            assignment.start_date, assignment.due_date, assignment.calendar
        ),
    )
    consumed = business_days_between(assignment.start_date, on_day, assignment.calendar)
    ratio = consumed * 100 / total
    if ratio >= 90:
        return DeadlineLevel.URGENT
    if ratio >= 75:
        return DeadlineLevel.WARNING
    if ratio >= 50:
        return DeadlineLevel.ATTENTION
    return DeadlineLevel.NORMAL


def task_progress_series(
    assignment: TaskAssignment,
    period: ReportingPeriod,
    *,
    daily_rows: Iterable[DailyProgressRow] | None = None,
) -> TaskProgressSeries:
    """Build a task profile from the same real daily series as the JSON route."""
    today = timezone.localdate()
    rows = (
        tuple(daily_rows)
        if daily_rows is not None
        else daily_progress_rows(assignment, today=today)
    )
    points = [
        ProgressPoint(
            row.elapsed_work_days,
            row.percentage,
            row.day,
            row.observed,
        )
        for row in rows
    ]
    percentage = points[-1].percentage if points else 0
    effective_end = points[-1].entry_date if points else assignment.start_date
    current_offset = points[-1].workday_offset if points else 0
    planned = assignment.estimated_work_days
    elapsed = Decimal(current_offset)
    displayed = max(Decimal(ceil(planned)), elapsed, Decimal("1.0"))
    latest = (
        assignment.progress_entries.filter(entry_date__lte=effective_end)
        .order_by("-entry_date", "-updated_at")
        .first()
    )
    return TaskProgressSeries(
        assignment=assignment,
        points=tuple(points),
        today=today,
        observation_count=sum(point.observed for point in points),
        planned_days=planned,
        displayed_days=displayed,
        overrun_days=max(Decimal("0.0"), elapsed - Decimal(ceil(planned))),
        percentage=percentage,
        workload=workload_breakdown(planned, percentage),
        action_key=assignment.task.action.code
        if assignment.task.action
        else "sans-action",
        deadline_level=deadline_level(
            assignment, on_day=effective_end, percentage=percentage
        ),
        blocked=bool(latest and latest.blocked),
        late=assignment.due_date < effective_end and percentage < 100,
        missing_update=latest is None or latest.entry_date < period.start,
    )


def remaining_projection(
    assignment: TaskAssignment, until: date | None = None
) -> Projection:
    """Combine initial workload and positive observed progress velocity."""
    entries = list(
        assignment.progress_entries.filter(
            **({"entry_date__lte": until} if until else {})
        ).order_by("entry_date", "updated_at")
    )
    current = entries[-1].percentage if entries else 0
    baseline = (
        assignment.estimated_work_days * Decimal(100 - current) / Decimal(100)
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    observed: Decimal | None = None
    distinct: list[ProgressEntry] = []
    for entry in entries:
        if distinct and distinct[-1].entry_date == entry.entry_date:
            distinct[-1] = entry
        else:
            distinct.append(entry)
    if len(distinct) >= 2:
        first, last = distinct[0], distinct[-1]
        elapsed = business_days_between(
            first.entry_date, last.entry_date, assignment.calendar
        )
        gained = last.percentage - first.percentage
        if elapsed > 0 and gained > 0 and last.percentage < 100:
            observed = (
                Decimal(100 - last.percentage) * Decimal(elapsed) / Decimal(gained)
            ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        elif last.percentage == 100:
            observed = Decimal("0.0")
    return Projection(current, baseline, observed)


def active_lines(on_day: date | None = None) -> QuerySet[ReportingLine]:
    """Return reporting lines active on the requested day."""
    target = on_day or timezone.localdate()
    return ReportingLine.objects.filter(start_date__lte=target).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=target)
    )


def primary_manager(employee: User, on_day: date | None = None) -> User | None:
    """Return an employee's active primary manager."""
    line = (
        active_lines(on_day)
        .filter(employee=employee, is_primary=True)
        .select_related("supervisor")
        .first()
    )
    return line.supervisor if line else None


def organization_unit_for_employee(
    employee: User, on_day: date | None = None
) -> int | None:
    """Resolve the employee's primary unit at a historical date."""
    membership = primary_membership(employee, on_day)
    if membership is not None:
        return membership.unit_id
    line = (
        active_lines(on_day)
        .filter(employee=employee, is_primary=True)
        .order_by("-start_date", "-pk")
        .first()
    )
    return line.unit_id if line is not None else None


def can_self_assign(user: User) -> bool:
    """Allow an organizational root user to create personal assignments."""
    return user.is_active and not user.is_it_admin and primary_manager(user) is None


def is_direct_supervisor(supervisor: User, employee: User) -> bool:
    return active_lines().filter(supervisor=supervisor, employee=employee).exists()


def is_primary_supervisor(supervisor: User, employee: User) -> bool:
    return (
        active_lines()
        .filter(supervisor=supervisor, employee=employee, is_primary=True)
        .exists()
    )


def can_view_employee(supervisor: User, employee: User) -> bool:
    """Check cycle-safe downward visibility through the full organization graph."""
    if supervisor == employee or supervisor.is_it_admin or supervisor.is_superuser:
        return True
    return employee.pk in visible_employee_ids(supervisor)


def hierarchy_employee_ids(supervisor: User) -> frozenset[int]:
    """Return the supervisor and active reporting descendants, cycle safely."""
    edges: dict[int, set[int]] = {}
    for manager_id, employee_id in active_lines().values_list(
        "supervisor_id", "employee_id"
    ):
        edges.setdefault(manager_id, set()).add(employee_id)
    queue: deque[int] = deque([supervisor.pk])
    visited = {supervisor.pk}
    while queue:
        person_id = queue.popleft()
        for child_id in edges.get(person_id, set()):
            if child_id not in visited:
                visited.add(child_id)
                queue.append(child_id)
    return frozenset(visited)


def visible_employee_ids(supervisor: User) -> frozenset[int]:
    """Combine hierarchy, current memberships, and historical scoped work."""
    hierarchy_ids = set(hierarchy_employee_ids(supervisor))
    unit_ids = scoped_unit_ids(supervisor, VIEW_PERMISSION)
    hierarchy_ids.update(member_user_ids(unit_ids))
    if unit_ids:
        hierarchy_ids.update(
            TaskAssignment.objects.filter(organization_unit_id__in=unit_ids).values_list(
                "employee_id", flat=True
            )
        )
    return frozenset(hierarchy_ids)


def can_view_assignment(user: User, assignment: TaskAssignment) -> bool:
    return (
        assignment.employee_id in hierarchy_employee_ids(user)
        or user.is_it_admin
        or user.is_superuser
        or has_scoped_permission(
            user, VIEW_PERMISSION, assignment.organization_unit_id
        )
    )


def is_self_managed_assignment(user: User, assignment: TaskAssignment) -> bool:
    """Return whether the organizational root owns and manages the assignment."""
    return (
        assignment.employee_id == user.pk
        and assignment.manager_id == user.pk
        and can_self_assign(user)
    )


def can_manage_assignment(user: User, assignment: TaskAssignment) -> bool:
    self_managed = is_self_managed_assignment(user, assignment)
    return (
        user.is_it_admin
        or user.is_superuser
        or self_managed
        or has_scoped_permission(
            user, MANAGE_PERMISSION, assignment.organization_unit_id
        )
        or (
            assignment.manager_id == user.pk
            and is_primary_supervisor(user, assignment.employee)
        )
    )


def can_comment_assignment(user: User, assignment: TaskAssignment) -> bool:
    return (
        user == assignment.employee
        or user.is_it_admin
        or user.is_superuser
        or is_direct_supervisor(user, assignment.employee)
        or has_scoped_permission(
            user, MANAGE_PERMISSION, assignment.organization_unit_id
        )
    )


def can_assign_employee(manager: User, employee: User, on_day: date) -> bool:
    """Check task creation against hierarchy, self-management, or delegation."""
    if manager.is_it_admin or manager.is_superuser:
        return True
    if manager == employee and can_self_assign(manager):
        return True
    if active_lines(on_day).filter(
        supervisor=manager, employee=employee, is_primary=True
    ).exists():
        return True
    return has_scoped_permission(
        manager,
        MANAGE_PERMISSION,
        organization_unit_for_employee(employee, on_day),
    )


def assignable_employee_ids(manager: User, on_day: date | None = None) -> frozenset[int]:
    """Return active people available in the assignment form."""
    target = on_day or timezone.localdate()
    if manager.is_it_admin or manager.is_superuser:
        return frozenset(User.objects.filter(is_active=True).values_list("pk", flat=True))
    employee_ids = set(
        active_lines(target)
        .filter(supervisor=manager, is_primary=True, employee__is_active=True)
        .values_list("employee_id", flat=True)
    )
    managed_units = scoped_unit_ids(manager, MANAGE_PERMISSION)
    employee_ids.update(member_user_ids(managed_units, target))
    if can_self_assign(manager):
        employee_ids.add(manager.pk)
    return frozenset(employee_ids)


@transaction.atomic
def set_primary_membership(
    *, user: User, unit_id: int, start_date: date
) -> OrganizationMembership:
    """Ensure one open primary service membership without erasing old records."""
    current = list(
        OrganizationMembership.objects.select_for_update().filter(
            user=user, is_primary=True, end_date__isnull=True
        )
    )
    same = next((item for item in current if item.unit_id == unit_id), None)
    if same is not None:
        update_fields: list[str] = []
        if start_date < same.start_date:
            same.start_date = start_date
            update_fields.append("start_date")
        if not same.job_title and user.position:
            same.job_title = user.position
            update_fields.append("job_title")
        if update_fields:
            same.save(update_fields=update_fields)
        return same
    for membership in current:
        membership.is_primary = False
        membership.save(update_fields=["is_primary"])
    membership = OrganizationMembership(
        user=user,
        unit_id=unit_id,
        job_title=user.position,
        start_date=start_date,
        is_primary=True,
    )
    membership.save()
    return membership


@transaction.atomic
def set_primary_supervisor(
    *, employee: User, supervisor: User, unit_id: int, start_date: date
) -> ReportingLine:
    """Set one primary line and transfer active assignment responsibility."""
    if employee == supervisor:
        raise ValidationError("Une personne ne peut pas etre son propre responsable.")
    set_primary_membership(user=employee, unit_id=unit_id, start_date=start_date)
    old_lines = list(
        ReportingLine.objects.select_for_update().filter(
            employee=employee, is_primary=True, end_date__isnull=True
        )
    )
    if any(line.supervisor_id == supervisor.pk for line in old_lines):
        return next(line for line in old_lines if line.supervisor_id == supervisor.pk)
    old_managers = {line.supervisor_id for line in old_lines}
    for line in old_lines:
        line.is_primary = False
        line.save(update_fields=["is_primary"])
    existing_line = ReportingLine.objects.filter(
        employee=employee, supervisor=supervisor, end_date__isnull=True
    ).first()
    if existing_line:
        existing_line.is_primary = True
        existing_line.unit_id = unit_id
        existing_line.full_clean()
        existing_line.save(update_fields=["is_primary", "unit"])
        line = existing_line
    else:
        line = ReportingLine(
            employee=employee,
            supervisor=supervisor,
            unit_id=unit_id,
            start_date=start_date,
            is_primary=True,
        )
        line.full_clean()
        line.save()
    assignments = TaskAssignment.objects.select_for_update().filter(
        employee=employee, manager_id__in=old_managers, status__in=ACTIVE_STATES
    )
    for assignment in assignments:
        task = assignment.task
        if task.assignments.exclude(pk=assignment.pk).exists():
            task.pk = None
            task.code = f"{task.code[:25]}-R{employee.pk}-{assignment.pk}"
            task.created_by = supervisor
            task.save()
            assignment.task = task
        elif task.created_by_id in old_managers:
            task.created_by = supervisor
            task.save(update_fields=["created_by"])
        assignment.manager = supervisor
        assignment.save(update_fields=["manager", "task"])
    return line


def ensure_manage(user: User, assignment: TaskAssignment) -> None:
    if not can_manage_assignment(user, assignment):
        raise PermissionDenied(
            "Seul le responsable principal peut effectuer cette action."
        )


def visible_activities(assignment: TaskAssignment) -> QuerySet[TaskActivity]:
    """Return current user-facing activities while retaining corrected audit rows."""
    return assignment.activities.filter(superseded_by__isnull=True).select_related(
        "actor", "progress_entry"
    )


def activity_feed(assignment: TaskAssignment) -> tuple[ActivityFeedItem, ...]:
    """Build the dated task feed with one short service label per author.

    Args:
        assignment: Task assignment whose visible, non-superseded events are read.

    Returns:
        Reverse-chronological events enriched without changing their audit rows.

    """
    activities = tuple(visible_activities(assignment).order_by("-occurred_at", "-pk"))
    actor_ids = {activity.actor_id for activity in activities}
    memberships_by_actor: dict[int, list[OrganizationMembership]] = {}
    for membership in (
        OrganizationMembership.objects.filter(user_id__in=actor_ids)
        .select_related("unit")
        .order_by("-is_primary", "-start_date", "-pk")
    ):
        memberships_by_actor.setdefault(membership.user_id, []).append(membership)
    lines_by_actor: dict[int, list[ReportingLine]] = {}
    for line in (
        ReportingLine.objects.filter(employee_id__in=actor_ids)
        .select_related("unit")
        .order_by("-is_primary", "-start_date", "-pk")
    ):
        lines_by_actor.setdefault(line.employee_id, []).append(line)

    def short_name(activity: TaskActivity) -> str:
        event_day = timezone.localtime(activity.occurred_at).date()
        for membership in memberships_by_actor.get(activity.actor_id, []):
            if membership.start_date <= event_day and (
                membership.end_date is None or membership.end_date >= event_day
            ):
                return membership.unit.short_name
        for line in lines_by_actor.get(activity.actor_id, []):
            if line.start_date <= event_day and (
                line.end_date is None or line.end_date >= event_day
            ):
                return line.unit.short_name
        return (
            activity.actor.login_alias.upper()
            if activity.actor.login_alias
            else activity.actor.position or str(activity.actor)
        )

    return tuple(
        ActivityFeedItem(activity=activity, actor_short_name=short_name(activity))
        for activity in activities
    )


@transaction.atomic
def next_task_code(action: InstitutionalAction | None, year: int) -> str:
    """Allocate ``ACTION-YEAR-0001`` or ``TACHE-YEAR-0001`` transactionally."""
    sequence, _created = TaskCodeSequence.objects.select_for_update().get_or_create(
        action=action, year=year, defaults={"next_value": 1}
    )
    normalized_action = (
        slugify(action.code).upper()[:30].rstrip("-") if action else "TACHE"
    )
    value = sequence.next_value
    candidate = f"{normalized_action}-{year}-{value:04d}"
    while Task.objects.filter(code=candidate).exists():
        value += 1
        candidate = f"{normalized_action}-{year}-{value:04d}"
    sequence.next_value = value + 1
    sequence.save(update_fields=["next_value"])
    return candidate


@transaction.atomic
def create_assignment_for_user(
    *,
    manager: User,
    employee: User,
    title: str,
    description: str,
    action: InstitutionalAction | None,
    start_date: date,
    due_date: date,
    estimated_work_days: Decimal,
    calendar: WorkCalendar,
) -> TaskAssignment:
    """Create one classified task and its independently planned assignment."""
    unit_id = organization_unit_for_employee(employee, start_date)
    if unit_id is None:
        raise ValidationError(
            "Le collaborateur doit avoir une appartenance organisationnelle."
        )
    if not can_assign_employee(manager, employee, start_date):
        raise PermissionDenied("Vous ne pouvez pas affecter une tache a cette personne.")
    accountable_manager = (
        manager
        if manager == employee
        else primary_manager(employee, start_date) or manager
    )
    code = next_task_code(action, start_date.year)
    task = Task(
        code=code,
        title=title,
        description=description,
        action=action,
        created_by=manager,
    )
    task.full_clean()
    task.save()
    assignment = TaskAssignment(
        task=task,
        employee=employee,
        manager=accountable_manager,
        organization_unit_id=unit_id,
        calendar=calendar,
        start_date=start_date,
        due_date=due_date,
        estimated_work_days=estimated_work_days,
        status=AssignmentStatus.PLANNED,
    )
    assignment.full_clean()
    assignment.save()
    return assignment


@transaction.atomic
def update_assignment_schedule(
    *,
    user: User,
    assignment: TaskAssignment,
    start_date: date,
    due_date: date,
    estimated_work_days: Decimal,
) -> None:
    """Apply a coherent schedule and append its visible audit event."""
    ensure_manage(user, assignment)
    old = {
        "start_date": assignment.start_date.isoformat(),
        "due_date": assignment.due_date.isoformat(),
        "estimated_work_days": str(assignment.estimated_work_days),
    }
    assignment.start_date = start_date
    assignment.due_date = due_date
    assignment.estimated_work_days = estimated_work_days
    assignment.full_clean()
    assignment.save(update_fields=["start_date", "due_date", "estimated_work_days"])
    new = {
        "start_date": start_date.isoformat(),
        "due_date": due_date.isoformat(),
        "estimated_work_days": str(estimated_work_days),
    }
    if old != new:
        TaskActivity.objects.create(
            assignment=assignment,
            kind=ActivityKind.SCHEDULE,
            actor=user,
            message="Planification mise à jour.",
            details={"before": old, "after": new},
        )


@transaction.atomic
def record_progress(
    *,
    user: User,
    assignment: TaskAssignment,
    entry_date: date,
    percentage: int,
    note: str,
    blocked: bool,
) -> ProgressEntry:
    """Create or correct one daily progress entry under the correction rules."""
    assignment = (
        TaskAssignment.objects.select_for_update()
        .select_related("employee", "manager", "task")
        .get(pk=assignment.pk)
    )
    employee_edit = user == assignment.employee
    manager_edit = can_manage_assignment(user, assignment)
    if not employee_edit and not manager_edit:
        raise PermissionDenied("Vous ne pouvez pas modifier cette progression.")
    if assignment.status == AssignmentStatus.CLOSED_EARLY:
        raise ValidationError("Une tâche clôturée ne peut plus recevoir de progression.")
    if employee_edit and entry_date != timezone.localdate():
        raise PermissionDenied("Une saisie passee doit etre corrigee par le responsable.")
    if not (user.is_it_admin or user.is_superuser) and percentage % 5:
        raise ValidationError("La progression doit etre saisie par pas de 5 %.")
    previous = current_progress(assignment)
    if (percentage < previous or blocked) and not note.strip():
        raise ValidationError(
            "Une note est obligatoire pour une regression ou un point d'attention."
        )
    was_completed = assignment.status == AssignmentStatus.COMPLETED
    existing = ProgressEntry.objects.filter(
        assignment=assignment, entry_date=entry_date
    ).first()
    previous_activity = None
    if existing is not None:
        previous_activity = (
            visible_activities(assignment)
            .filter(kind=ActivityKind.PROGRESS, progress_entry=existing)
            .order_by("-occurred_at", "-pk")
            .first()
        )
        existing.percentage = percentage
        existing.note = note.strip()
        existing.blocked = blocked
        existing.author = user
        existing.save()
        entry = existing
    else:
        entry = ProgressEntry.objects.create(
            assignment=assignment,
            entry_date=entry_date,
            percentage=percentage,
            note=note.strip(),
            blocked=blocked,
            author=user,
        )
    activity_message = note.strip() or f"Progression enregistrée à {percentage} %."
    TaskActivity.objects.create(
        assignment=assignment,
        kind=ActivityKind.PROGRESS,
        actor=user,
        message=activity_message,
        percentage_before=previous,
        percentage_after=percentage,
        progress_entry=entry,
        supersedes=previous_activity,
    )
    if was_completed and percentage == 100:
        pass
    elif percentage == 100:
        assignment.status = AssignmentStatus.AWAITING_VALIDATION
        assignment.completed_at = None
    elif was_completed:
        assignment.status = AssignmentStatus.ACTIVE
        assignment.completed_at = None
        TaskActivity.objects.create(
            assignment=assignment,
            kind=ActivityKind.REOPENED,
            actor=user,
            message=(
                f"Tâche rouverte de {previous} % à {percentage} %. {note.strip()}"
            ).strip(),
            percentage_before=previous,
            percentage_after=percentage,
        )
        from work.notifications import queue_reopening_notification

        queue_reopening_notification(assignment, user)
    elif assignment.status == AssignmentStatus.AWAITING_VALIDATION:
        assignment.status = AssignmentStatus.ACTIVE
    elif assignment.status == AssignmentStatus.PLANNED:
        assignment.status = AssignmentStatus.ACTIVE
    assignment.save(update_fields=["status", "completed_at"])
    return entry


@transaction.atomic
def validate_completion(user: User, assignment: TaskAssignment) -> None:
    assignment = (
        TaskAssignment.objects.select_for_update()
        .select_related("employee", "manager")
        .get(pk=assignment.pk)
    )
    ensure_manage(user, assignment)
    if assignment.status != AssignmentStatus.AWAITING_VALIDATION:
        raise ValidationError("Cette tâche n’est pas en attente de validation.")
    if current_progress(assignment) != 100:
        raise ValidationError("Une tâche doit être réalisée à 100 % avant validation.")
    assignment.status = AssignmentStatus.COMPLETED
    assignment.completed_at = timezone.now()
    assignment.save(update_fields=["status", "completed_at"])
    TaskActivity.objects.create(
        assignment=assignment,
        kind=ActivityKind.VALIDATED,
        actor=user,
        message="Achèvement validé.",
        percentage_before=100,
        percentage_after=100,
    )


@transaction.atomic
def reject_completion(user: User, assignment: TaskAssignment, reason: str) -> None:
    ensure_manage(user, assignment)
    if not reason.strip():
        raise ValidationError("Un motif est obligatoire.")
    assignment.status = AssignmentStatus.ACTIVE
    assignment.save(update_fields=["status"])
    TaskActivity.objects.create(
        assignment=assignment,
        kind=ActivityKind.REJECTED,
        actor=user,
        message=reason.strip(),
        percentage_before=current_progress(assignment),
        percentage_after=current_progress(assignment),
    )
    from work.notifications import queue_comment_notification

    queue_comment_notification(assignment, user)


@transaction.atomic
def close_early(user: User, assignment: TaskAssignment, reason: str) -> None:
    ensure_manage(user, assignment)
    if not reason.strip():
        raise ValidationError("Un motif est obligatoire.")
    assignment.status = AssignmentStatus.CLOSED_EARLY
    assignment.closed_reason = reason.strip()
    assignment.completed_at = timezone.now()
    assignment.save(update_fields=["status", "closed_reason", "completed_at"])
    TaskActivity.objects.create(
        assignment=assignment,
        kind=ActivityKind.CLOSED,
        actor=user,
        message=reason.strip(),
        percentage_before=current_progress(assignment),
        percentage_after=current_progress(assignment),
    )


@transaction.atomic
def add_observation(
    *, user: User, assignment: TaskAssignment, message: str
) -> TaskActivity:
    """Append a general observation under direct-participant permissions."""
    if not can_comment_assignment(user, assignment):
        raise PermissionDenied("Vous ne pouvez pas commenter cette tâche.")
    cleaned = message.strip()
    if not cleaned:
        raise ValidationError("Une observation est obligatoire.")
    activity = TaskActivity.objects.create(
        assignment=assignment,
        kind=ActivityKind.COMMENT,
        actor=user,
        message=cleaned,
    )
    from work.notifications import queue_comment_notification

    queue_comment_notification(assignment, user)
    return activity


@transaction.atomic
def accept_proposal(
    user: User, proposal: TaskProposal, code: str | None = None
) -> TaskAssignment:
    """Turn an employee proposal into a managed task assignment."""
    if not can_review_proposal(user, proposal):
        raise PermissionDenied(
            "Vous ne pouvez pas accepter cette proposition."
        )
    unit_id = proposal.organization_unit_id or organization_unit_for_employee(
        proposal.employee, proposal.start_date
    )
    if unit_id is None:
        raise ValidationError("La proposition n'est rattachee a aucun service.")
    accountable_manager = primary_manager(proposal.employee, proposal.start_date) or user
    task = Task.objects.create(
        code=code or next_task_code(proposal.action, proposal.start_date.year),
        title=proposal.title,
        description=proposal.description,
        action=proposal.action,
        created_by=user,
    )
    assignment = TaskAssignment(
        task=task,
        employee=proposal.employee,
        manager=accountable_manager,
        organization_unit_id=unit_id,
        calendar=proposal.calendar,
        start_date=proposal.start_date,
        due_date=proposal.due_date,
        estimated_work_days=proposal.estimated_work_days,
        status=AssignmentStatus.PLANNED,
    )
    assignment.full_clean()
    assignment.save()
    proposal.status = ProposalStatus.ACCEPTED
    proposal.reviewed_by = user
    proposal.organization_unit_id = unit_id
    proposal.accepted_assignment = assignment
    proposal.decided_at = timezone.now()
    proposal.save(
        update_fields=[
            "status",
            "reviewed_by",
            "organization_unit",
            "accepted_assignment",
            "decided_at",
        ]
    )
    from work.notifications import queue_assignment_notification

    queue_assignment_notification(assignment)
    return assignment


@transaction.atomic
def reject_proposal(user: User, proposal: TaskProposal, reason: str) -> None:
    if not can_review_proposal(user, proposal):
        raise PermissionDenied(
            "Vous ne pouvez pas refuser cette proposition."
        )
    cleaned_reason = reason.strip()
    if not cleaned_reason:
        raise ValidationError("Un motif de rejet est obligatoire.")
    proposal.status = ProposalStatus.REJECTED
    proposal.reviewed_by = user
    proposal.decision_note = cleaned_reason
    proposal.decided_at = timezone.now()
    proposal.save(update_fields=["status", "reviewed_by", "decision_note", "decided_at"])


def can_review_proposal(user: User, proposal: TaskProposal) -> bool:
    """Authorize proposal decisions through hierarchy or scoped management."""
    if proposal.employee_id == user.pk and not (user.is_it_admin or user.is_superuser):
        return False
    return (
        user.is_it_admin
        or user.is_superuser
        or is_primary_supervisor(user, proposal.employee)
        or has_scoped_permission(
            user, PROPOSAL_PERMISSION, proposal.organization_unit_id
        )
    )


def reviewable_proposals(user: User) -> QuerySet[TaskProposal]:
    """Return proposals the user may decide, without including mere readers."""
    queryset = TaskProposal.objects.exclude(employee=user)
    if user.is_it_admin or user.is_superuser:
        return queryset
    direct_ids = active_lines().filter(
        supervisor=user, is_primary=True
    ).values_list("employee_id", flat=True)
    delegated_units = scoped_unit_ids(user, PROPOSAL_PERMISSION)
    return queryset.filter(
        Q(employee_id__in=direct_ids)
        | Q(organization_unit_id__in=delegated_units)
    )


def visible_team_proposals(user: User) -> QuerySet[TaskProposal]:
    """Return team proposals visible through hierarchy or a read delegation."""
    queryset = TaskProposal.objects.exclude(employee=user)
    if user.is_it_admin or user.is_superuser:
        return queryset
    direct_ids = active_lines().filter(
        supervisor=user, is_primary=True
    ).values_list("employee_id", flat=True)
    delegated_units = scoped_unit_ids(user, VIEW_PERMISSION)
    return queryset.filter(
        Q(employee_id__in=direct_ids)
        | Q(organization_unit_id__in=delegated_units)
    )


def weekly_assignments(employee: User, monday: date) -> QuerySet[TaskAssignment]:
    """Return assignments overlapping the selected Monday-to-Sunday week."""
    sunday = monday + timedelta(days=6)
    return (
        TaskAssignment.objects.filter(employee=employee, start_date__lte=sunday)
        .filter(Q(completed_at__isnull=True) | Q(completed_at__date__gte=monday))
        .select_related("task", "employee", "manager", "task__action")
    )


def period_assignments(
    employee: User,
    period: ReportingPeriod,
    *,
    include_progress_cache: bool = True,
    viewer: User | None = None,
) -> QuerySet[TaskAssignment]:
    """Return assignments that overlap an inclusive reporting period.

    Args:
        employee: Person whose assigned work is requested.
        period: Inclusive week or month to display.
        include_progress_cache: Join cached daily rows for curve consumers.
        viewer: Optional requester used to filter delegated, unit-scoped access.

    Returns:
        Assignments with the relations required by cards and team profiles.

    """
    related = ["task", "employee", "manager", "task__action", "calendar"]
    if include_progress_cache:
        related.append("progress_series_cache")
    queryset = TaskAssignment.objects.filter(
        employee=employee, start_date__lte=period.end
    )
    if viewer is not None:
        queryset = queryset.filter(pk__in=visible_assignments(viewer).values("pk"))
    return (
        queryset
        .filter(Q(completed_at__isnull=True) | Q(completed_at__date__gte=period.start))
        .select_related(*related)
        .prefetch_related("calendar__days", "progress_entries", "activities__actor")
    )


def assignment_snapshot(
    assignment: TaskAssignment, period: ReportingPeriod
) -> AssignmentSnapshot:
    """Build display indicators using only observations available in the period."""
    latest = (
        assignment.progress_entries.filter(entry_date__lte=period.end)
        .order_by("-entry_date", "-updated_at")
        .first()
    )
    before = current_progress(assignment, period.start - timedelta(days=1))
    current = latest.percentage if latest else 0
    status = effective_assignment_status(assignment.status, current)
    comments = tuple(
        visible_activities(assignment)
        .filter(
            kind__in=(ActivityKind.COMMENT, ActivityKind.PROGRESS),
            occurred_at__date__lte=period.end,
        )
        .exclude(message="")
        .order_by("-occurred_at", "-pk")
    )
    workload = workload_breakdown(assignment.estimated_work_days, current)
    return AssignmentSnapshot(
        assignment=assignment,
        percentage=current,
        status=status,
        status_label=assignment_status_label(status),
        progress_delta=current - before,
        projection=remaining_projection(assignment, period.end),
        workload=workload,
        deadline_level=deadline_level(
            assignment, on_day=min(period.end, timezone.localdate()), percentage=current
        ),
        latest=latest,
        comments=comments,
    )


def summarize_employee(employee: User, monday: date) -> EmployeeSummary:
    """Aggregate one employee row for the selected week."""
    sunday = monday + timedelta(days=6)
    assignments = list(weekly_assignments(employee, monday))
    if not assignments:
        zero = Decimal("0.0")
        return EmployeeSummary(employee, 0, zero, zero, zero, zero, 0, 0, 0)
    percentages = [current_progress(item, sunday) for item in assignments]
    projections = [
        workload_breakdown(item.estimated_work_days, percentage).remaining_days
        for item, percentage in zip(assignments, percentages, strict=True)
    ]
    latest_entries = [
        item.progress_entries.filter(entry_date__lte=sunday)
        .order_by("-entry_date", "-updated_at")
        .first()
        for item in assignments
    ]
    remaining_total = sum(projections, Decimal("0.0"))

    def quantize(value: int | float) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"))

    return EmployeeSummary(
        employee=employee,
        task_count=len(assignments),
        mean_progress=quantize(mean(percentages)),
        median_progress=quantize(median(percentages)),
        remaining_total=remaining_total,
        remaining_mean=(remaining_total / len(assignments)).quantize(Decimal("0.1")),
        blocked_count=sum(1 for entry in latest_entries if entry and entry.blocked),
        late_count=sum(
            1
            for assignment, percentage in zip(assignments, percentages, strict=True)
            if assignment.due_date < sunday and percentage < 100
        ),
        missing_update_count=sum(
            1
            for entry in latest_entries
            if entry is None or not (monday <= entry.entry_date <= sunday)
        ),
        progress_delta=quantize(
            mean(
                current_progress(item, sunday)
                - current_progress(item, monday - timedelta(days=1))
                for item in assignments
            )
        ),
    )


def summarize_employee_period(
    employee: User,
    period: ReportingPeriod,
    *,
    assignments: Iterable[TaskAssignment] | None = None,
    include_task_series: bool = True,
) -> EmployeeSummary:
    """Aggregate one employee over a week or calendar month."""
    period_items = (
        list(assignments)
        if assignments is not None
        else list(period_assignments(employee, period))
    )
    if not period_items:
        zero = Decimal("0.0")
        return EmployeeSummary(employee, 0, zero, zero, zero, zero, 0, 0, 0, zero, ())
    snapshots = [assignment_snapshot(item, period) for item in period_items]
    percentages = [item.percentage for item in snapshots]
    remaining = [item.workload.remaining_days for item in snapshots]
    total = sum(remaining, Decimal("0.0"))

    def decimal_mean(values: Iterable[int]) -> Decimal:
        return Decimal(str(mean(values))).quantize(Decimal("0.01"))

    trend: list[WeeklyTrendPoint] = []
    cursor = min(period.start + timedelta(days=6), period.end)
    while cursor <= period.end:
        visible = [item for item in period_items if item.start_date <= cursor]
        if visible:
            trend.append(
                WeeklyTrendPoint(
                    cursor,
                    decimal_mean(current_progress(item, cursor) for item in visible),
                )
            )
        if cursor == period.end:
            break
        cursor = min(cursor + timedelta(days=7), period.end)

    series = (
        tuple(task_progress_series(item, period) for item in period_items)
        if include_task_series
        else ()
    )
    return EmployeeSummary(
        employee=employee,
        task_count=len(period_items),
        mean_progress=decimal_mean(percentages),
        median_progress=Decimal(str(median(percentages))).quantize(Decimal("0.01")),
        remaining_total=total,
        remaining_mean=(total / len(period_items)).quantize(Decimal("0.1")),
        blocked_count=sum(1 for item in snapshots if item.latest and item.latest.blocked),
        late_count=sum(
            1
            for item in snapshots
            if item.assignment.due_date < period.end and item.percentage < 100
        ),
        missing_update_count=sum(
            1
            for item in snapshots
            if item.latest is None or item.latest.entry_date < period.start
        ),
        progress_delta=decimal_mean(item.progress_delta for item in snapshots),
        trend=tuple(trend),
        task_series=series,
    )


def direct_employee_period_summaries(
    manager: User, period: ReportingPeriod
) -> list[EmployeeSummary]:
    """Build period summaries for each active direct collaborator."""
    employees = User.objects.filter(
        reporting_lines__in=active_lines(period.end).filter(supervisor=manager)
    ).distinct()
    return [summarize_employee_period(employee, period) for employee in employees]


def team_tree(manager: User, period: ReportingPeriod) -> tuple[TeamNode, ...]:
    """Build all descendant subteams without a hard-coded depth limit."""
    lines = list(
        active_lines(period.end)
        .filter(is_primary=True)
        .select_related("employee")
        .order_by("employee__position", "employee__email")
    )
    edges: dict[int, list[User]] = {}
    for line in lines:
        edges.setdefault(line.supervisor_id, []).append(line.employee)

    def build(parent_id: int, visited: frozenset[int]) -> tuple[TeamNode, ...]:
        nodes: list[TeamNode] = []
        for employee in edges.get(parent_id, []):
            if employee.pk in visited:
                continue
            descendants = build(employee.pk, visited | {employee.pk})
            nodes.append(
                TeamNode(
                    summary=summarize_employee_period(employee, period),
                    children=descendants,
                )
            )
        return tuple(nodes)

    return build(manager.pk, frozenset({manager.pk}))


def team_tree_overview(
    manager: User, period: ReportingPeriod
) -> tuple[TeamNodeOverview, ...]:
    """Build hierarchy headers and task counts without reading progress series."""
    lines = list(
        active_lines(period.end)
        .filter(is_primary=True)
        .select_related("employee")
        .order_by("employee__position", "employee__email")
    )
    visible_ids = set(visible_employee_ids(manager))
    visible_ids.discard(manager.pk)
    edges: dict[int, list[User]] = {}
    for line in lines:
        if line.employee_id not in visible_ids:
            continue
        if line.supervisor_id in visible_ids or line.supervisor_id == manager.pk:
            edges.setdefault(line.supervisor_id, []).append(line.employee)
    represented = {employee.pk for employees in edges.values() for employee in employees}
    detached_ids = visible_ids - represented
    for employee in User.objects.filter(pk__in=detached_ids).order_by(
        "position", "email"
    ):
        edges.setdefault(manager.pk, []).append(employee)
    employee_ids = visible_ids
    task_counts = {
        item["employee_id"]: item["task_count"]
        for item in visible_assignments(manager).filter(
            employee_id__in=employee_ids,
            start_date__lte=period.end,
        )
        .filter(Q(completed_at__isnull=True) | Q(completed_at__date__gte=period.start))
        .values("employee_id")
        .annotate(task_count=Count("pk"))
    }

    def build(parent_id: int, visited: frozenset[int]) -> tuple[TeamNodeOverview, ...]:
        nodes: list[TeamNodeOverview] = []
        for employee in edges.get(parent_id, []):
            if employee.pk in visited:
                continue
            nodes.append(
                TeamNodeOverview(
                    employee=employee,
                    task_count=int(task_counts.get(employee.pk, 0)),
                    children=build(employee.pk, visited | {employee.pk}),
                )
            )
        return tuple(nodes)

    return build(manager.pk, frozenset({manager.pk}))


def direct_employee_summaries(manager: User, monday: date) -> list[EmployeeSummary]:
    """Build one summary row per direct employee, never one table per employee."""
    employees = User.objects.filter(
        reporting_lines__in=active_lines().filter(supervisor=manager)
    ).distinct()
    return [summarize_employee(employee, monday) for employee in employees]


def visible_assignments(user: User) -> QuerySet[TaskAssignment]:
    """Return all assignments currently visible through the organization graph."""
    queryset = (
        TaskAssignment.objects.select_related(
            "task",
            "task__action",
            "employee",
            "manager",
            "calendar",
            "progress_series_cache",
        )
        .prefetch_related("calendar__days", "progress_entries")
        .order_by("employee_id", "task__code", "pk")
    )
    if user.is_it_admin or user.is_superuser:
        return queryset
    hierarchy_ids = hierarchy_employee_ids(user)
    delegated_units = scoped_unit_ids(user, VIEW_PERMISSION)
    return queryset.filter(
        Q(employee_id__in=hierarchy_ids)
        | Q(organization_unit_id__in=delegated_units)
    )
