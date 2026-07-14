"""Correctness tests for the rebuildable progression chart projection."""

from datetime import datetime, time, timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import User
from work.models import AssignmentStatus, ProgressSeriesCache, TaskAssignment
from work.progress_cache import cached_daily_progress_rows


@pytest.mark.django_db
def test_second_cache_read_does_not_recalculate_daily_rows(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    assignment.progress_entries.create(
        entry_date=timezone.localdate(),
        percentage=35,
        author=people["employee"],
    )
    expected = cached_daily_progress_rows(assignment)

    with patch("work.progress_cache.daily_progress_rows_from_entries") as calculate_rows:
        actual = cached_daily_progress_rows(assignment)

    assert actual == expected
    calculate_rows.assert_not_called()
    assert ProgressSeriesCache.objects.filter(assignment=assignment).count() == 1


@pytest.mark.django_db
def test_progress_and_schedule_mutations_invalidate_the_cache(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    entry = assignment.progress_entries.create(
        entry_date=timezone.localdate(),
        percentage=20,
        author=people["employee"],
    )
    cached_daily_progress_rows(assignment)

    entry.percentage = 45
    entry.save(update_fields=["percentage", "updated_at"])
    assert not ProgressSeriesCache.objects.filter(assignment=assignment).exists()
    assert cached_daily_progress_rows(assignment)[-1].percentage == 45

    assignment.status = AssignmentStatus.AWAITING_VALIDATION
    assignment.save(update_fields=["status"])
    assert not ProgressSeriesCache.objects.filter(assignment=assignment).exists()


@pytest.mark.django_db
def test_calendar_mutation_invalidates_every_dependent_cache(
    assignment: TaskAssignment,
) -> None:
    cached_daily_progress_rows(assignment)
    override = assignment.calendar.days.first()
    assert override is not None

    override.delete()

    assert not ProgressSeriesCache.objects.filter(assignment=assignment).exists()


@pytest.mark.django_db
def test_open_cache_extends_but_completed_cache_keeps_its_closing_day(
    assignment: TaskAssignment,
) -> None:
    first_day = assignment.start_date + timedelta(days=2)
    initial = cached_daily_progress_rows(assignment, today=first_day)
    extended = cached_daily_progress_rows(assignment, today=first_day + timedelta(days=1))
    assert len(extended) == len(initial) + 1

    assignment.completed_at = timezone.make_aware(datetime.combine(first_day, time(16)))
    assignment.status = AssignmentStatus.COMPLETED
    assignment.save(update_fields=["completed_at", "status"])
    completed = cached_daily_progress_rows(
        assignment, today=first_day + timedelta(days=10)
    )

    assert completed[-1].day == first_day
    cache = ProgressSeriesCache.objects.get(assignment=assignment)
    assert cache.through_date == first_day


@pytest.mark.django_db
def test_management_command_can_prebuild_one_cache(
    assignment: TaskAssignment, capsys: pytest.CaptureFixture[str]
) -> None:
    call_command("rebuild_progress_caches", assignment_ids=[assignment.pk])

    assert ProgressSeriesCache.objects.filter(assignment=assignment).exists()
    assert "1 cache(s) reconstruit(s)" in capsys.readouterr().out
