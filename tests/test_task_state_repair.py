"""Regression tests for completed assignments below full progression."""

from importlib import import_module

import pytest
from django.apps import apps
from django.utils import timezone

from accounts.models import User
from work.models import AssignmentStatus, ProgressSeriesCache, TaskAssignment
from work.progress_cache import cached_daily_progress_rows


@pytest.mark.django_db
def test_data_migration_repairs_every_inconsistent_completed_task(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    assignment.progress_entries.create(
        entry_date=timezone.localdate(),
        percentage=85,
        note="Une reprise reste necessaire.",
        author=people["employee"],
    )
    TaskAssignment.objects.filter(pk=assignment.pk).update(
        status=AssignmentStatus.COMPLETED,
        completed_at=timezone.now(),
    )
    cached_daily_progress_rows(assignment)
    assert ProgressSeriesCache.objects.filter(assignment=assignment).exists()

    migration = import_module("work.migrations.0009_repair_inconsistent_completed_tasks")
    migration.repair_inconsistent_completed_tasks(apps, None)

    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE
    assert assignment.completed_at is None
    repaired = assignment.activities.get(
        details__reason="inconsistent_completed_progress"
    )
    assert repaired.percentage_before == 100
    assert repaired.percentage_after == 85
    assert not ProgressSeriesCache.objects.filter(assignment=assignment).exists()
