"""Typed database cache for privacy-minimal daily progression series."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable, Mapping

from django.db.models import QuerySet
from django.utils import timezone

from work.models import ProgressSeriesCache, TaskAssignment
from work.services import (
    DailyProgressRow,
    daily_progress_rows_from_entries,
    progress_series_end_date,
)

CACHE_SCHEMA_VERSION = 1


def _as_int(value: object) -> int:
    """Decode one JSON integer without accepting ambiguous container values."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError("Valeur entiere de cache invalide.")


def _as_bool(value: object) -> bool:
    """Decode booleans stored by Django's JSON field."""
    if isinstance(value, bool):
        return value
    if value in (0, 1, "0", "1", "false", "true"):
        return value in (1, "1", "true")
    raise TypeError("Valeur booleenne de cache invalide.")


def row_from_json(payload: Mapping[str, object]) -> DailyProgressRow:
    """Restore one validated typed row from a cache JSON object.

    Args:
        payload: Privacy-minimal row previously produced by ``DailyProgressRow``.

    Returns:
        The typed value consumed by chart and aggregate services.

    Raises:
        KeyError: A required field is absent.
        TypeError: A numeric or boolean field has an unsupported JSON type.
        ValueError: A date or scalar value cannot be decoded.

    """
    return DailyProgressRow(
        task_id=_as_int(payload["task_id"]),
        start_date=date.fromisoformat(str(payload["start_date"])),
        day=date.fromisoformat(str(payload["day"])),
        is_working_day=_as_bool(payload["is_working_day"]),
        due_date=date.fromisoformat(str(payload["due_date"])),
        planned_work_days=Decimal(str(payload["planned_work_days"])),
        elapsed_work_days=_as_int(payload["elapsed_work_days"]),
        remaining_schedule_days=Decimal(str(payload["remaining_schedule_days"])),
        overdue_days=Decimal(str(payload["overdue_days"])),
        percentage=_as_int(payload["percentage"]),
        observed=_as_bool(payload["observed"]),
    )


def rows_from_cache(cache: ProgressSeriesCache) -> tuple[DailyProgressRow, ...]:
    """Decode a cache payload, raising when its shape is stale or corrupted."""
    if cache.schema_version != CACHE_SCHEMA_VERSION or not isinstance(
        cache.payload, list
    ):
        raise ValueError("Schema de cache incompatible.")
    return tuple(row_from_json(item) for item in cache.payload if isinstance(item, dict))


def cached_daily_progress_rows(
    assignment: TaskAssignment,
    *,
    today: date | None = None,
    refresh: bool = False,
) -> tuple[DailyProgressRow, ...]:
    """Read a valid series cache or rebuild it from canonical database rows.

    Args:
        assignment: Task whose schedule and observations define the series.
        today: Explicit calculation boundary, mainly for deterministic exports.
        refresh: Force reconstruction even when the persisted projection is current.

    Returns:
        An ordered, typed row for every represented calendar day.

    """
    current_day = today or timezone.localdate()
    through_date = progress_series_end_date(assignment, current_day)
    if not refresh:
        try:
            cache = assignment.progress_series_cache
        except ProgressSeriesCache.DoesNotExist:
            cache = None
        if (
            cache is not None
            and cache.schema_version == CACHE_SCHEMA_VERSION
            and cache.through_date == through_date
        ):
            try:
                rows = rows_from_cache(cache)
                if rows and rows[-1].day == through_date:
                    return rows
            except (KeyError, TypeError, ValueError):
                pass

    rows = daily_progress_rows_from_entries(
        assignment,
        assignment.progress_entries.all(),
        today=current_day,
    )
    cache, _created = ProgressSeriesCache.objects.update_or_create(
        assignment=assignment,
        defaults={
            "schema_version": CACHE_SCHEMA_VERSION,
            "through_date": through_date,
            "payload": [row.as_json() for row in rows],
        },
    )
    assignment._state.fields_cache["progress_series_cache"] = cache
    return rows


def rebuild_progress_caches(
    assignments: Iterable[TaskAssignment] | QuerySet[TaskAssignment],
    *,
    today: date | None = None,
) -> int:
    """Rebuild caches deterministically.

    Args:
        assignments: Assignments to project, preferably with calendar and history
            already prefetched.
        today: Optional common calculation boundary.

    Returns:
        The number of processed assignments.

    """
    current_day = today or timezone.localdate()
    count = 0
    for assignment in assignments:
        cached_daily_progress_rows(assignment, today=current_day, refresh=True)
        count += 1
    return count
