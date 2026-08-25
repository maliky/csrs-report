from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import User
from work.models import (
    AssignmentStatus,
    RecurrenceStatus,
    TaskAssignment,
    TaskProposal,
    TaskRecurrence,
    WorkCalendar,
    WorkCalendarDay,
)
from work.services import (
    cancel_task_recurrence,
    accept_proposal_with_recurrence,
    close_early_with_recurrence,
    record_progress,
    validate_completion_with_recurrence,
    validate_recurrence_schedule,
)


def attach_weekly_series(
    assignment: TaskAssignment, *, created_by: User | None = None
) -> TaskRecurrence:
    assignment.estimated_work_days = Decimal("1")
    assignment.due_date = assignment.calendar.due_date_for(
        assignment.start_date, assignment.estimated_work_days
    )
    series = TaskRecurrence.objects.create(
        employee=assignment.employee,
        created_by=created_by or assignment.manager,
        title=assignment.task.title,
        description=assignment.task.description,
        action=assignment.task.action,
        calendar=assignment.calendar,
        estimated_work_days=assignment.estimated_work_days,
        anchor_start_date=assignment.start_date,
        end_date=assignment.start_date + timedelta(days=21),
    )
    assignment.recurrence = series
    assignment.recurrence_occurrence = 1
    assignment.recurrence_anchor_date = assignment.start_date
    assignment.save()
    return series


@pytest.mark.django_db
def test_validation_creates_one_distinct_following_occurrence(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    series = attach_weekly_series(assignment)
    record_progress(
        user=people["employee"],
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=100,
        note="Terminee",
        blocked=False,
    )
    assignment.refresh_from_db()
    with patch("work.services.timezone.localdate", return_value=assignment.start_date):
        validate_completion_with_recurrence(people["manager"], assignment)

    occurrences = list(series.assignments.order_by("recurrence_occurrence"))
    assert len(occurrences) == 2
    assert occurrences[0].task_id != occurrences[1].task_id
    assert occurrences[1].recurrence_occurrence == 2
    assert occurrences[1].status == AssignmentStatus.PLANNED


@pytest.mark.django_db
def test_holiday_shifts_effective_start_without_moving_weekly_anchor(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    series = attach_weekly_series(assignment)
    next_anchor = assignment.start_date + timedelta(days=7)
    WorkCalendar.objects.filter(pk=assignment.calendar_id).update(is_default=False)
    current_calendar = WorkCalendar.objects.create(
        name="Calendrier courant",
        version="test-recurrence",
        is_default=True,
        active=True,
    )
    WorkCalendarDay.objects.create(
        calendar=current_calendar,
        day=next_anchor,
        name="Jour non ouvre",
        is_working_day=False,
    )
    with patch("work.services.timezone.localdate", return_value=assignment.start_date):
        close_early_with_recurrence(people["manager"], assignment, "Achevee")

    following = series.assignments.get(recurrence_occurrence=2)
    assert following.calendar == current_calendar
    assert following.recurrence_anchor_date == next_anchor
    assert following.start_date > next_anchor


@pytest.mark.django_db
def test_late_closure_permanently_cancels_series(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    series = attach_weekly_series(assignment)
    next_anchor = assignment.start_date + timedelta(days=7)
    with patch("work.services.timezone.localdate", return_value=next_anchor):
        close_early_with_recurrence(people["manager"], assignment, "Trop tard")

    series.refresh_from_db()
    assert series.status == RecurrenceStatus.CANCELLED
    assert series.assignments.count() == 1


@pytest.mark.django_db
def test_originating_employee_cancels_only_future_occurrences(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    series = attach_weekly_series(assignment, created_by=people["employee"])
    initial_status = assignment.status
    cancel_task_recurrence(
        user=people["employee"],
        recurrence=series,
        expected_revision=series.revision,
        reason="Plus necessaire",
    )

    series.refresh_from_db()
    assignment.refresh_from_db()
    assert series.status == RecurrenceStatus.CANCELLED
    assert assignment.status == initial_status


@pytest.mark.django_db
def test_accepting_recurring_proposal_attaches_series(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    workload = Decimal("1")
    proposal = TaskProposal.objects.create(
        employee=people["employee"],
        organization_unit=assignment.organization_unit,
        title="Controle hebdomadaire",
        description="Verifier les donnees",
        action=assignment.task.action,
        calendar=assignment.calendar,
        start_date=assignment.start_date,
        due_date=assignment.calendar.due_date_for(assignment.start_date, workload),
        estimated_work_days=workload,
        recurrence_frequency="weekly",
        recurrence_end_date=assignment.start_date + timedelta(days=21),
    )

    accept_proposal_with_recurrence(
        user=people["manager"],
        proposal=proposal,
        expected_revision=proposal.revision,
    )

    proposal.refresh_from_db()
    assert proposal.accepted_recurrence_id is not None
    assert proposal.accepted_assignment is not None
    assert proposal.accepted_assignment.recurrence_id == proposal.accepted_recurrence_id


@pytest.mark.django_db
def test_weekly_schedule_rejects_overlapping_occurrences(
    assignment: TaskAssignment,
) -> None:
    next_start = assignment.start_date + timedelta(days=7)
    with pytest.raises(ValidationError, match="chevaucher"):
        validate_recurrence_schedule(
            calendar=assignment.calendar,
            start_date=assignment.start_date,
            due_date=next_start,
            estimated_work_days=Decimal("10"),
            frequency="weekly",
            end_date=assignment.start_date + timedelta(days=21),
        )
