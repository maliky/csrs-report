"""Destructive reporting cleanup with explicit scope and durable audit."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.models import User
from agenda.models import AgendaDraft, AgendaVersion, StaffAvailability, VisitorVisit
from processes.storage import configured_storage
from work.models import (
    NotificationDelivery,
    ProgressEntry,
    ReportingDeletionAudit,
    ReportingDeletionKind,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskCodeSequence,
    TaskProposal,
)
from work.services import can_delete_reporting_data


TASK_NOTIFICATION_TYPES = ("new_assignment", "new_comment", "task_reopened")


@dataclass(frozen=True)
class ReportingResetResult:
    audit_id: int | None
    counts: dict[str, int]
    deleted_files: int


def reporting_reset_counts() -> dict[str, int]:
    """Return the exact current scope of a reporting reset."""
    return {
        "tasks": Task.objects.count(),
        "assignments": TaskAssignment.objects.count(),
        "progress_entries": ProgressEntry.objects.count(),
        "activities": TaskActivity.objects.count(),
        "proposals": TaskProposal.objects.count(),
        "task_notifications": NotificationDelivery.objects.filter(
            event_type__in=TASK_NOTIFICATION_TYPES
        ).count(),
        "task_code_sequences": TaskCodeSequence.objects.count(),
        "agenda_drafts": AgendaDraft.objects.count(),
        "agenda_versions": AgendaVersion._base_manager.count(),
        "visits": VisitorVisit.objects.count(),
        "availability": StaffAvailability.objects.count(),
    }


def reset_reporting_data(
    *, actor: User, reason: str, dry_run: bool = False
) -> ReportingResetResult:
    """Remove reporting data while preserving identities and organization data."""
    if not can_delete_reporting_data(actor):
        raise PermissionDenied(
            "Seul un administrateur IT peut reinitialiser les donnees de reporting."
        )
    normalized_reason = reason.strip()
    if len(normalized_reason) < 3:
        raise ValidationError("Le motif doit contenir au moins 3 caracteres.")
    if len(normalized_reason) > 500:
        raise ValidationError("Le motif ne peut pas depasser 500 caracteres.")

    counts = reporting_reset_counts()
    agenda_files = list(
        AgendaVersion._base_manager.order_by("pk").values_list(
            "storage_provider", "storage_key"
        )
    )
    if dry_run:
        return ReportingResetResult(audit_id=None, counts=counts, deleted_files=0)

    storage = configured_storage() if agenda_files else None
    incompatible = sorted(
        {provider for provider, _key in agenda_files if provider != storage.provider}
        if storage is not None
        else set()
    )
    if incompatible:
        raise ValidationError(
            "Le stockage actif ne peut pas supprimer les versions: "
            + ", ".join(incompatible)
        )

    with transaction.atomic():
        audit = ReportingDeletionAudit.objects.create(
            actor=actor,
            kind=ReportingDeletionKind.REPORTING_RESET,
            reason=normalized_reason,
            snapshot={
                "counts": counts,
                "agenda_files": [
                    {"provider": provider, "key": key} for provider, key in agenda_files
                ],
            },
        )
        TaskActivity.objects.filter(supersedes__isnull=False).update(supersedes=None)
        TaskProposal.objects.all().delete()
        Task.objects.all().delete()
        TaskCodeSequence.objects.all().delete()
        NotificationDelivery.objects.filter(
            event_type__in=TASK_NOTIFICATION_TYPES
        ).delete()

        AgendaVersion._base_manager.all().delete()
        AgendaDraft.objects.all().delete()
        VisitorVisit.objects.all().delete()
        StaffAvailability.objects.all().delete()

        Task.history.model._base_manager.all().delete()
        TaskAssignment.history.model._base_manager.all().delete()
        TaskProposal.history.model._base_manager.all().delete()
        ProgressEntry.history.model._base_manager.all().delete()
        AgendaDraft.history.model._base_manager.all().delete()
        VisitorVisit.history.model._base_manager.all().delete()
        StaffAvailability.history.model._base_manager.all().delete()

    failed_keys: list[str] = []
    if storage is not None:
        for _provider, key in agenda_files:
            try:
                storage.delete(key)
            except (OSError, ValidationError):
                failed_keys.append(key)
    if failed_keys:
        raise ValidationError(
            "La base a ete reinitialisee, mais certains PDF n'ont pas pu etre supprimes: "
            + ", ".join(failed_keys)
        )
    return ReportingResetResult(
        audit_id=audit.pk,
        counts=counts,
        deleted_files=len(agenda_files),
    )
