"""Typed, permission-scoped data exchange for Observable notebooks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import cast

from django.conf import settings
from django.core import signing
from django.utils import timezone

from accounts.models import User
from work.models import TaskAssignment
from work.progress_cache import cached_daily_progress_rows
from work.services import (
    DailyProgressRow,
    effective_assignment_status,
    visible_assignments,
)

TOKEN_SALT = "work.observable.progress.v1"


def can_use_observable(user: User) -> bool:
    """Return whether the technical developer may issue and use export tokens."""
    return bool(user.is_active and user.is_superuser)


@dataclass(frozen=True)
class ObservableTask:
    """Privacy-minimal metadata identifying one visible assignment."""

    task_id: int
    task_code: str
    task_title: str
    action_code: str | None
    employee_id: int
    status: str
    start_date: date
    due_date: date
    planned_work_days: Decimal
    completed_on: date | None

    @classmethod
    def from_assignment(
        cls, assignment: TaskAssignment, percentage: int
    ) -> "ObservableTask":
        """Create export metadata without names, email addresses, or notes."""
        status = effective_assignment_status(assignment.status, percentage)
        return cls(
            task_id=assignment.pk,
            task_code=assignment.task.code,
            task_title=assignment.task.title,
            action_code=(assignment.task.action.code if assignment.task.action else None),
            employee_id=assignment.employee_id,
            status=status,
            start_date=assignment.start_date,
            due_date=assignment.due_date,
            planned_work_days=assignment.estimated_work_days,
            completed_on=(
                assignment.completed_at.date()
                if status == "completed" and assignment.completed_at
                else None
            ),
        )

    def as_json(self) -> dict[str, object]:
        """Return JSON-safe task metadata."""
        payload = asdict(self)
        for key in ("start_date", "due_date"):
            payload[key] = cast(date, payload[key]).isoformat()
        completed_on = cast(date | None, payload["completed_on"])
        payload["completed_on"] = completed_on.isoformat() if completed_on else None
        payload["planned_work_days"] = float(cast(Decimal, payload["planned_work_days"]))
        return payload


@dataclass(frozen=True)
class ObservableProgress:
    """One chart row linked to its assignment metadata by ``task_id``."""

    progress: DailyProgressRow

    def as_json(self) -> dict[str, object]:
        """Preserve the established per-task progression schema."""
        return self.progress.as_json()


@dataclass(frozen=True)
class ObservableDataset:
    """All assignments and daily progression rows visible to one user."""

    tasks: tuple[ObservableTask, ...]
    progress: tuple[ObservableProgress, ...]

    def as_json(self) -> dict[str, object]:
        """Return the stable versioned payload consumed by Observable."""
        return {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "task_count": len(self.tasks),
            "progress_row_count": len(self.progress),
            "tasks": [task.as_json() for task in self.tasks],
            "progress": [row.as_json() for row in self.progress],
        }


def observable_dataset(user: User, *, today: date | None = None) -> ObservableDataset:
    """Build one aggregate export under the user's current read permissions.

    Args:
        user: Active token owner whose organization scope must be applied.
        today: Optional deterministic endpoint for tests.

    Returns:
        Visible task metadata and daily histories, with progress prefetched once.

    """
    current_day = today or timezone.localdate()
    assignments = tuple(visible_assignments(user))
    assignment_rows = tuple(
        (assignment, cached_daily_progress_rows(assignment, today=current_day))
        for assignment in assignments
    )
    tasks = tuple(
        ObservableTask.from_assignment(
            assignment,
            rows[-1].percentage if rows else 0,
        )
        for assignment, rows in assignment_rows
    )
    progress = tuple(
        ObservableProgress(row) for _assignment, rows in assignment_rows for row in rows
    )
    return ObservableDataset(tasks=tasks, progress=progress)


def create_export_token(user: User) -> str:
    """Create a timestamped bearer token containing only the issuing user id."""
    return signing.dumps({"user_id": user.pk}, salt=TOKEN_SALT, compress=True)


def export_token_user_id(token: str) -> int:
    """Validate a bearer token and return its user id.

    Raises:
        django.core.signing.BadSignature: If the token is malformed or expired.

    """
    payload = signing.loads(
        token,
        salt=TOKEN_SALT,
        max_age=settings.OBSERVABLE_EXPORT_TOKEN_MAX_AGE_SECONDS,
    )
    if not isinstance(payload, dict):
        raise signing.BadSignature("Format de jeton invalide.")
    user_id = payload.get("user_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise signing.BadSignature("Identifiant de jeton invalide.")
    return user_id
