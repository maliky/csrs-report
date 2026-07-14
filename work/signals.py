"""Small transactional invalidation hooks for rebuildable chart projections."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from work.models import (
    ProgressEntry,
    ProgressSeriesCache,
    TaskAssignment,
    WorkCalendarDay,
)


def invalidate_assignment_cache(assignment_id: int) -> None:
    """Delete one derived cache inside the source mutation transaction."""
    ProgressSeriesCache.objects.filter(assignment_id=assignment_id).delete()


def clear_loaded_projection(assignment: TaskAssignment) -> None:
    """Drop a reverse relation cached on the currently mutated model object."""
    assignment._state.fields_cache.pop("progress_series_cache", None)


@receiver(post_save, sender=ProgressEntry)
@receiver(post_delete, sender=ProgressEntry)
def invalidate_progress_cache(
    sender: type[ProgressEntry], instance: ProgressEntry, **kwargs: object
) -> None:
    """Invalidate a series after an observation is changed or removed."""
    del sender, kwargs
    invalidate_assignment_cache(instance.assignment_id)
    assignment = instance._state.fields_cache.get("assignment")
    if isinstance(assignment, TaskAssignment):
        clear_loaded_projection(assignment)


@receiver(post_save, sender=TaskAssignment)
def invalidate_assignment_projection(
    sender: type[TaskAssignment], instance: TaskAssignment, **kwargs: object
) -> None:
    """Invalidate schedule and state changes without touching source history."""
    del sender, kwargs
    if instance.pk:
        invalidate_assignment_cache(instance.pk)
        clear_loaded_projection(instance)


@receiver(post_save, sender=WorkCalendarDay)
@receiver(post_delete, sender=WorkCalendarDay)
def invalidate_calendar_projections(
    sender: type[WorkCalendarDay], instance: WorkCalendarDay, **kwargs: object
) -> None:
    """Invalidate every assignment retaining a changed calendar version."""
    del sender, kwargs
    ProgressSeriesCache.objects.filter(
        assignment__calendar_id=instance.calendar_id
    ).delete()
