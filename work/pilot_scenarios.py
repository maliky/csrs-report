"""Deterministic, typed scenarios for the CSRS illustration population."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from math import ceil
from typing import Callable


IsWorkingDay = Callable[[date], bool]


class ScenarioKind(StrEnum):
    """Business outcome represented by one illustration assignment."""

    ON_TIME = "on_time"
    EARLY_COMPLETED = "early_completed"
    CLOSED_EARLY = "closed_early"
    SLIGHT_LATE_COMPLETED = "slight_late_completed"
    ACTIVE_ON_SCHEDULE = "active_on_schedule"
    ACTIVE_SLIGHT_LATE = "active_slight_late"
    REOPENED_COMPLETED = "reopened_completed"
    REOPENED_ACTIVE = "reopened_active"
    BIG_LATE_COMPLETED = "big_late_completed"
    BIG_LATE_ACTIVE = "big_late_active"


@dataclass(frozen=True)
class ProgressMilestone:
    """One real progression observation in a generated task history."""

    day: date
    percentage: int
    blocked: bool = False


@dataclass(frozen=True)
class PilotScenario:
    """Complete calendar and state narrative for one illustration task."""

    kind: ScenarioKind
    workload: Decimal
    start_date: date
    due_date: date
    milestones: tuple[ProgressMilestone, ...]
    completion_date: date | None = None
    validation_dates: tuple[date, ...] = ()
    reopen_date: date | None = None
    close_date: date | None = None


@dataclass(frozen=True)
class _ScenarioDates:
    """Internal dates selected before milestones are calculated."""

    due_date: date
    completion_date: date | None = None
    validation_dates: tuple[date, ...] = ()
    reopen_date: date | None = None
    close_date: date | None = None


SCENARIO_TOTAL = 73
EXPECTED_SCENARIO_COUNTS = {
    ScenarioKind.ON_TIME: 38,
    ScenarioKind.EARLY_COMPLETED: 8,
    ScenarioKind.CLOSED_EARLY: 5,
    ScenarioKind.SLIGHT_LATE_COMPLETED: 7,
    ScenarioKind.ACTIVE_ON_SCHEDULE: 7,
    ScenarioKind.ACTIVE_SLIGHT_LATE: 3,
    ScenarioKind.REOPENED_COMPLETED: 2,
    ScenarioKind.REOPENED_ACTIVE: 1,
    ScenarioKind.BIG_LATE_COMPLETED: 1,
    ScenarioKind.BIG_LATE_ACTIVE: 1,
}

_NON_ON_TIME_KINDS = (
    ScenarioKind.EARLY_COMPLETED,
    ScenarioKind.SLIGHT_LATE_COMPLETED,
    ScenarioKind.ACTIVE_ON_SCHEDULE,
    ScenarioKind.CLOSED_EARLY,
    ScenarioKind.EARLY_COMPLETED,
    ScenarioKind.SLIGHT_LATE_COMPLETED,
    ScenarioKind.ACTIVE_ON_SCHEDULE,
    ScenarioKind.ACTIVE_SLIGHT_LATE,
    ScenarioKind.EARLY_COMPLETED,
    ScenarioKind.CLOSED_EARLY,
    ScenarioKind.SLIGHT_LATE_COMPLETED,
    ScenarioKind.ACTIVE_ON_SCHEDULE,
    ScenarioKind.BIG_LATE_COMPLETED,
    ScenarioKind.EARLY_COMPLETED,
    ScenarioKind.SLIGHT_LATE_COMPLETED,
    ScenarioKind.ACTIVE_ON_SCHEDULE,
    ScenarioKind.CLOSED_EARLY,
    ScenarioKind.EARLY_COMPLETED,
    ScenarioKind.ACTIVE_SLIGHT_LATE,
    ScenarioKind.SLIGHT_LATE_COMPLETED,
    ScenarioKind.ACTIVE_ON_SCHEDULE,
    ScenarioKind.BIG_LATE_ACTIVE,
    ScenarioKind.EARLY_COMPLETED,
    ScenarioKind.CLOSED_EARLY,
    ScenarioKind.SLIGHT_LATE_COMPLETED,
    ScenarioKind.ACTIVE_ON_SCHEDULE,
    ScenarioKind.REOPENED_COMPLETED,
    ScenarioKind.EARLY_COMPLETED,
    ScenarioKind.SLIGHT_LATE_COMPLETED,
    ScenarioKind.ACTIVE_SLIGHT_LATE,
    ScenarioKind.CLOSED_EARLY,
    ScenarioKind.REOPENED_COMPLETED,
    ScenarioKind.EARLY_COMPLETED,
    ScenarioKind.REOPENED_ACTIVE,
    ScenarioKind.ACTIVE_ON_SCHEDULE,
)

_LONG_TASK_INDICES = (1, 9, 18, 27, 36, 45, 54, 63)


def scenario_kind_for(index: int) -> ScenarioKind:
    """Return the stable business outcome assigned to one task index.

    Args:
        index: Zero-based position in the 73-task illustration population.

    Returns:
        The scenario kind allocated to that task.

    Raises:
        ValueError: The index falls outside the illustration population.

    """
    if not 0 <= index < SCENARIO_TOTAL:
        raise ValueError(f"Indice de scenario hors limites: {index}.")
    if index % 2 == 0 or index == 1:
        return ScenarioKind.ON_TIME
    return _NON_ON_TIME_KINDS[(index - 3) // 2]


def scenario_counts() -> dict[ScenarioKind, int]:
    """Return the actual deterministic distribution of scenario kinds."""
    return dict(Counter(scenario_kind_for(index) for index in range(SCENARIO_TOTAL)))


def shift_workdays(day: date, amount: int, is_working_day: IsWorkingDay) -> date:
    """Shift a date by a signed number of retained-calendar workdays.

    Args:
        day: Date excluded from the count.
        amount: Positive or negative number of working days to cross.
        is_working_day: Calendar predicate retained by the assignment.

    Returns:
        The working date reached after the requested shift.

    """
    if amount == 0:
        return day
    cursor = day
    direction = 1 if amount > 0 else -1
    remaining = abs(amount)
    while remaining:
        cursor += timedelta(days=direction)
        if is_working_day(cursor):
            remaining -= 1
    return cursor


def workload_for(index: int) -> Decimal:
    """Return a credible workload while retaining exactly eight exceptions.

    Args:
        index: Zero-based task position.

    Returns:
        A workload between 2 and 10 days for 65 tasks, or 12 to 20 days for
        one of the eight accepted longer assignments.

    """
    scenario_kind_for(index)
    if index in _LONG_TASK_INDICES:
        rank = _LONG_TASK_INDICES.index(index)
        return Decimal(12 + 2 * (rank % 5)).quantize(Decimal("0.1"))
    base = Decimal(2 + (index * 3) % 8)
    if index % 6 == 0:
        base += Decimal("0.5")
    return base.quantize(Decimal("0.1"))


def _completed_due_date(index: int, today: date, is_working_day: IsWorkingDay) -> date:
    lookback_span = 16 if index in _LONG_TASK_INDICES else 38
    lookback = 4 + (index * 7) % lookback_span
    return shift_workdays(today, -lookback, is_working_day)


def _milestones(
    *,
    index: int,
    start: date,
    end: date,
    final_percentage: int,
    is_working_day: IsWorkingDay,
) -> tuple[ProgressMilestone, ...]:
    total = 0
    cursor = start
    while cursor < end:
        cursor += timedelta(days=1)
        total += int(is_working_day(cursor))
    offsets = sorted({0, max(1, total // 3), max(1, 2 * total // 3), total})
    offsets = [offset for offset in offsets if offset <= total]
    days = tuple(shift_workdays(start, offset, is_working_day) for offset in offsets)
    points: list[ProgressMilestone] = []
    previous = 0
    for position, milestone_day in enumerate(days):
        if position == len(days) - 1:
            percentage = final_percentage
        else:
            raw = final_percentage * (position + 1) / len(days)
            percentage = max(5, int(raw // 5) * 5)
            if index % 5 == 0 and position == 1:
                percentage = previous
            percentage = min(percentage, final_percentage - 5)
        blocked = len(days) >= 3 and position == 1 and index % 7 == 0
        points.append(ProgressMilestone(milestone_day, percentage, blocked))
        previous = percentage
    return tuple(points)


def _active_final_percentage(index: int) -> int:
    return 45 + 5 * (index % 10)


def _active_dates(
    kind: ScenarioKind,
    index: int,
    workload_days: int,
    today: date,
    is_working_day: IsWorkingDay,
) -> _ScenarioDates:
    if kind == ScenarioKind.ACTIVE_ON_SCHEDULE:
        maximum_future = max(1, min(5, workload_days - 1))
        due_date = shift_workdays(today, 1 + index % maximum_future, is_working_day)
        return _ScenarioDates(due_date)
    if kind == ScenarioKind.ACTIVE_SLIGHT_LATE:
        return _ScenarioDates(shift_workdays(today, -(1 + index % 2), is_working_day))
    if kind == ScenarioKind.BIG_LATE_ACTIVE:
        return _ScenarioDates(shift_workdays(today, -7, is_working_day))
    due_date = shift_workdays(today, -3, is_working_day)
    reopen_date = shift_workdays(due_date, 1, is_working_day)
    return _ScenarioDates(due_date, validation_dates=(due_date,), reopen_date=reopen_date)


def _finished_dates(
    kind: ScenarioKind,
    index: int,
    workload_days: int,
    today: date,
    is_working_day: IsWorkingDay,
) -> _ScenarioDates:
    if kind == ScenarioKind.BIG_LATE_COMPLETED:
        due_date = shift_workdays(today, -12, is_working_day)
        completion_date = shift_workdays(due_date, 7, is_working_day)
        return _ScenarioDates(
            due_date,
            completion_date=completion_date,
            validation_dates=(completion_date,),
        )
    if kind == ScenarioKind.SLIGHT_LATE_COMPLETED:
        due_date = shift_workdays(today, -(5 + index % 24), is_working_day)
        completion_date = shift_workdays(due_date, 1 + index % 2, is_working_day)
        return _ScenarioDates(
            due_date,
            completion_date=completion_date,
            validation_dates=(completion_date,),
        )
    if kind == ScenarioKind.REOPENED_COMPLETED:
        due_date = shift_workdays(today, -(8 + index % 10), is_working_day)
        reopen_date = shift_workdays(due_date, 1, is_working_day)
        completion_date = shift_workdays(due_date, 3 + index % 2, is_working_day)
        return _ScenarioDates(
            due_date,
            completion_date=completion_date,
            validation_dates=(due_date, completion_date),
            reopen_date=reopen_date,
        )

    due_date = _completed_due_date(index, today, is_working_day)
    if kind in (ScenarioKind.EARLY_COMPLETED, ScenarioKind.CLOSED_EARLY):
        early_days = min(1 + index % 2, max(1, workload_days - 1))
        completion_date = shift_workdays(due_date, -early_days, is_working_day)
        if kind == ScenarioKind.CLOSED_EARLY:
            return _ScenarioDates(
                due_date,
                completion_date=completion_date,
                close_date=completion_date,
            )
        return _ScenarioDates(
            due_date,
            completion_date=completion_date,
            validation_dates=(completion_date,),
        )
    return _ScenarioDates(
        due_date, completion_date=due_date, validation_dates=(due_date,)
    )


def _reopened_milestones(
    *,
    kind: ScenarioKind,
    index: int,
    start_date: date,
    dates: _ScenarioDates,
    today: date,
    is_working_day: IsWorkingDay,
) -> tuple[ProgressMilestone, ...]:
    if dates.reopen_date is None:
        raise ValueError("Date de reouverture absente.")
    milestones = list(
        _milestones(
            index=index,
            start=start_date,
            end=dates.due_date,
            final_percentage=100,
            is_working_day=is_working_day,
        )
    )
    reopened_percentage = 65 + 5 * (index % 3)
    milestones.append(ProgressMilestone(dates.reopen_date, reopened_percentage))
    if kind == ScenarioKind.REOPENED_COMPLETED:
        if dates.completion_date is None:
            raise ValueError("Date de fin absente pour une tache rouverte.")
        milestones.append(ProgressMilestone(dates.completion_date, 100))
    else:
        last_day = today
        if not is_working_day(last_day):
            last_day = shift_workdays(last_day, -1, is_working_day)
        if last_day > dates.reopen_date:
            milestones.append(
                ProgressMilestone(last_day, min(90, reopened_percentage + 15))
            )
    return tuple(milestones)


def _regular_final_percentage(kind: ScenarioKind, index: int) -> int:
    if kind in (
        ScenarioKind.ON_TIME,
        ScenarioKind.EARLY_COMPLETED,
        ScenarioKind.SLIGHT_LATE_COMPLETED,
        ScenarioKind.BIG_LATE_COMPLETED,
    ):
        return 100
    if kind == ScenarioKind.CLOSED_EARLY:
        return 40 + 5 * (index % 9)
    return _active_final_percentage(index)


def build_pilot_scenario(
    index: int, *, today: date, is_working_day: IsWorkingDay
) -> PilotScenario:
    """Build one coherent scenario against a retained working calendar.

    Args:
        index: Stable zero-based task position.
        today: True application date used for active task boundaries.
        is_working_day: Calendar predicate used for every offset.

    Returns:
        An immutable task narrative ready to persist.

    """
    kind = scenario_kind_for(index)
    workload = workload_for(index)
    workload_days = ceil(workload)
    if kind in (
        ScenarioKind.ACTIVE_ON_SCHEDULE,
        ScenarioKind.ACTIVE_SLIGHT_LATE,
        ScenarioKind.REOPENED_ACTIVE,
        ScenarioKind.BIG_LATE_ACTIVE,
    ):
        dates = _active_dates(kind, index, workload_days, today, is_working_day)
    else:
        dates = _finished_dates(kind, index, workload_days, today, is_working_day)
    start_date = shift_workdays(dates.due_date, -workload_days, is_working_day)

    if kind in (ScenarioKind.REOPENED_COMPLETED, ScenarioKind.REOPENED_ACTIVE):
        progress = _reopened_milestones(
            kind=kind,
            index=index,
            start_date=start_date,
            dates=dates,
            today=today,
            is_working_day=is_working_day,
        )
    else:
        end_date = dates.completion_date or today
        if not is_working_day(end_date):
            end_date = shift_workdays(end_date, -1, is_working_day)
        progress = _milestones(
            index=index,
            start=start_date,
            end=end_date,
            final_percentage=_regular_final_percentage(kind, index),
            is_working_day=is_working_day,
        )

    return PilotScenario(
        kind=kind,
        workload=workload,
        start_date=start_date,
        due_date=dates.due_date,
        milestones=progress,
        completion_date=dates.completion_date,
        validation_dates=dates.validation_dates,
        reopen_date=dates.reopen_date,
        close_date=dates.close_date,
    )
