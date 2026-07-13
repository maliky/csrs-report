"""Bounded email notification outbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from work.models import NotificationDelivery, NotificationStatus, TaskAssignment

MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class DeliveryResult:
    sent: int
    retried: int
    failed: int


def queue_assignment_notification(assignment: TaskAssignment) -> NotificationDelivery:
    """Notify an employee about a newly assigned task."""
    return NotificationDelivery.objects.create(
        recipient=assignment.employee,
        event_type="new_assignment",
        subject="Nouvelle tache dans CSRS Report",
        body=(
            f"Une nouvelle tache vous a ete affectee : {assignment.task.title}. "
            "Connectez-vous a CSRS Report pour consulter les details."
        ),
    )


def queue_comment_notification(
    assignment: TaskAssignment, author: User
) -> NotificationDelivery | None:
    """Notify the other main participant without copying comment text."""
    recipient = (
        assignment.manager if author == assignment.employee else assignment.employee
    )
    if recipient == author:
        return None
    return NotificationDelivery.objects.create(
        recipient=recipient,
        event_type="new_comment",
        subject="Nouveau commentaire dans CSRS Report",
        body=(
            f"Un nouveau commentaire concerne la tache {assignment.task.title}. "
            "Connectez-vous a CSRS Report pour le lire."
        ),
    )


def queue_reopening_notification(
    assignment: TaskAssignment, author: User
) -> NotificationDelivery | None:
    """Notify the primary manager when completed work is explicitly reopened."""
    if assignment.manager == author:
        return None
    return NotificationDelivery.objects.create(
        recipient=assignment.manager,
        event_type="task_reopened",
        subject="Tache rouverte dans CSRS Report",
        body=(
            f"La tache {assignment.task.title} a ete rouverte apres une nouvelle "
            "progression. Connectez-vous a CSRS Report pour consulter l'historique."
        ),
    )


def _retry_delay(attempts: int) -> timedelta:
    return timedelta(minutes=min(60, 2 ** max(0, attempts - 1)))


def deliver_due_notifications(limit: int = 50) -> DeliveryResult:
    """Send a bounded batch and retain only the exception type on failure."""
    sent = retried = failed = 0
    now = timezone.now()
    ids = list(
        NotificationDelivery.objects.filter(
            status=NotificationStatus.PENDING,
            next_attempt_at__lte=now,
        )
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    for delivery_id in ids:
        with transaction.atomic():
            delivery = (
                NotificationDelivery.objects.select_for_update()
                .select_related("recipient")
                .get(pk=delivery_id)
            )
            delivery.attempts += 1
            try:
                send_mail(
                    delivery.subject,
                    delivery.body,
                    None,
                    [delivery.recipient.email],
                    fail_silently=False,
                )
            except Exception as error:  # Boundary around external SMTP failures.
                delivery.last_error_type = type(error).__name__
                if delivery.attempts >= MAX_ATTEMPTS:
                    delivery.status = NotificationStatus.FAILED
                    failed += 1
                else:
                    delivery.next_attempt_at = now + _retry_delay(delivery.attempts)
                    retried += 1
                delivery.save(
                    update_fields=[
                        "attempts",
                        "last_error_type",
                        "status",
                        "next_attempt_at",
                    ]
                )
            else:
                delivery.status = NotificationStatus.SENT
                delivery.sent_at = now
                delivery.last_error_type = ""
                delivery.save(
                    update_fields=["attempts", "status", "sent_at", "last_error_type"]
                )
                sent += 1
    return DeliveryResult(sent=sent, retried=retried, failed=failed)
