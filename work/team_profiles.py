"""Typed JSON projection loaded lazily by the team dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from django.urls import reverse

from accounts.models import User
from work.progress_cache import cached_daily_progress_rows
from work.services import (
    DailyProgressRow,
    EmployeeSummary,
    ReportingPeriod,
    TaskProgressSeries,
    effective_assignment_status,
    period_assignments,
    summarize_employee_period,
    task_progress_series,
)


@dataclass(frozen=True)
class CachedTaskProfile:
    """One calculated task profile paired with its cached daily rows."""

    series: TaskProgressSeries
    rows: tuple[DailyProgressRow, ...]

    def as_json(self) -> dict[str, object]:
        """Return chart metadata without observations, authors, or descriptions."""
        assignment = self.series.assignment
        status = effective_assignment_status(assignment.status, self.series.percentage)
        return {
            "task_id": assignment.pk,
            "task_title": assignment.task.title,
            "detail_url": reverse("assignment-detail", args=[assignment.pk]),
            "status": status,
            "is_open": status not in ("completed", "closed_early"),
            "action_code": self.series.action_key,
            "percentage": self.series.percentage,
            "observation_count": self.series.observation_count,
            "planned_work_days": float(self.series.planned_days),
            "displayed_days": float(self.series.displayed_days),
            "overrun_days": float(self.series.overrun_days),
            "remaining_work_days": float(self.series.workload.remaining_days),
            "deadline_level": str(self.series.deadline_level),
            "blocked": self.series.blocked,
            "late": self.series.late,
            "missing_update": self.series.missing_update,
            "start_date": assignment.start_date.isoformat(),
            "today": self.series.today.isoformat(),
            "due_date": assignment.due_date.isoformat(),
            "progress": [row.as_json() for row in self.rows],
        }


@dataclass(frozen=True)
class EmployeeProfileDataset:
    """Aggregate indicators and cached task profiles for one employee."""

    summary: EmployeeSummary
    tasks: tuple[CachedTaskProfile, ...]
    period: ReportingPeriod

    def as_json(self) -> dict[str, object]:
        """Return the stable same-origin team dashboard response."""
        summary = self.summary
        return {
            "employee_id": summary.employee.pk,
            "period": {
                "kind": self.period.kind,
                "start": self.period.start.isoformat(),
                "end": self.period.end.isoformat(),
            },
            "summary": {
                "task_count": summary.task_count,
                "mean_progress": float(summary.mean_progress),
                "median_progress": float(summary.median_progress),
                "remaining_total": float(summary.remaining_total),
                "remaining_mean": float(summary.remaining_mean),
                "blocked_count": summary.blocked_count,
                "late_count": summary.late_count,
                "missing_update_count": summary.missing_update_count,
                "progress_delta": float(summary.progress_delta),
            },
            "tasks": [task.as_json() for task in self.tasks],
        }


def employee_profile_dataset(
    employee: User, period: ReportingPeriod
) -> EmployeeProfileDataset:
    """Build one lazy dashboard payload and reuse persisted chart projections.

    Args:
        employee: Authorized person whose task profiles are requested.
        period: Week or month selected on the team dashboard.

    Returns:
        Typed aggregate indicators and privacy-minimal task chart profiles.

    """
    assignments = list(period_assignments(employee, period))
    summary = summarize_employee_period(
        employee,
        period,
        assignments=assignments,
        include_task_series=False,
    )
    tasks: list[CachedTaskProfile] = []
    for assignment in assignments:
        rows = cached_daily_progress_rows(assignment)
        tasks.append(
            CachedTaskProfile(
                series=task_progress_series(assignment, period, daily_rows=rows),
                rows=rows,
            )
        )
    return EmployeeProfileDataset(summary=summary, tasks=tuple(tasks), period=period)
