"""Typed workload projection loaded lazily by the team dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from work.models import ProgressEntry, TaskAssignment
from work.services import (
    DeadlineLevel,
    ReportingPeriod,
    WorkloadBreakdown,
    deadline_level,
    effective_assignment_status,
    period_assignments,
    workload_breakdown,
)


@dataclass(frozen=True)
class TeamTaskBar:
    """One inexpensive task workload bar for the team dashboard."""

    assignment: TaskAssignment
    percentage: int
    workload: WorkloadBreakdown
    status: str
    deadline_level: DeadlineLevel
    blocked: bool
    late: bool
    missing_update: bool
    today: date

    def as_json(self) -> dict[str, object]:
        """Return privacy-minimal workload metadata without historical rows."""
        assignment = self.assignment
        return {
            "task_id": assignment.pk,
            "task_title": assignment.task.title,
            "detail_url": reverse("assignment-detail", args=[assignment.pk]),
            "status": self.status,
            "percentage": self.percentage,
            "planned_work_days": float(self.workload.total_days),
            "completed_work_days": float(self.workload.completed_days),
            "remaining_work_days": float(self.workload.remaining_days),
            "deadline_level": str(self.deadline_level),
            "blocked": self.blocked,
            "late": self.late,
            "missing_update": self.missing_update,
            "start_date": assignment.start_date.isoformat(),
            "today": self.today.isoformat(),
            "due_date": assignment.due_date.isoformat(),
        }


@dataclass(frozen=True)
class EmployeeProfileDataset:
    """Lean task-bar response for one employee and reporting period."""

    employee: User
    tasks: tuple[TeamTaskBar, ...]
    period: ReportingPeriod

    def as_json(self) -> dict[str, object]:
        """Return the stable same-origin team dashboard response."""
        return {
            "employee_id": self.employee.pk,
            "period": {
                "kind": self.period.kind,
                "start": self.period.start.isoformat(),
                "end": self.period.end.isoformat(),
            },
            "tasks": [task.as_json() for task in self.tasks],
        }


def _latest_entry(
    assignment: TaskAssignment, period: ReportingPeriod
) -> ProgressEntry | None:
    """Return the latest prefetched entry visible in the selected period."""
    visible = [
        entry
        for entry in assignment.progress_entries.all()
        if entry.entry_date <= period.end
    ]
    if not visible:
        return None
    return max(visible, key=lambda entry: (entry.entry_date, entry.updated_at, entry.pk))


def _task_bar(
    assignment: TaskAssignment, period: ReportingPeriod, today: date
) -> TeamTaskBar:
    """Build one bar from persisted task and latest progress values."""
    latest = _latest_entry(assignment, period)
    percentage = latest.percentage if latest else 0
    status = effective_assignment_status(assignment.status, percentage)
    effective_day = min(period.end, today)
    return TeamTaskBar(
        assignment=assignment,
        percentage=percentage,
        workload=workload_breakdown(assignment.estimated_work_days, percentage),
        status=status,
        deadline_level=deadline_level(
            assignment, on_day=effective_day, percentage=percentage
        ),
        blocked=bool(latest and latest.blocked),
        late=assignment.due_date < effective_day and percentage < 100,
        missing_update=latest is None or latest.entry_date < period.start,
        today=today,
    )


def employee_profile_dataset(
    employee: User, period: ReportingPeriod, *, viewer: User | None = None
) -> EmployeeProfileDataset:
    """Build bars without calculating or transferring progress histories.

    Args:
        employee: Authorized person whose task bars are requested.
        period: Week or month selected on the team dashboard.
        viewer: Optional requester whose unit scope filters the returned tasks.

    Returns:
        Typed task metadata derived from persisted assignments and progress.

    """
    assignments = list(
        period_assignments(
            employee,
            period,
            include_progress_cache=False,
            viewer=viewer,
        )
        .prefetch_related(None)
        .prefetch_related("progress_entries")
    )
    today = timezone.localdate()
    return EmployeeProfileDataset(
        employee=employee,
        tasks=tuple(_task_bar(item, period, today) for item in assignments),
        period=period,
    )
