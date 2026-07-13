import pytest
from django.core import mail
from django.utils import timezone

from accounts.models import User
from work.models import NotificationStatus, TaskAssignment
from work.notifications import (
    deliver_due_notifications,
    queue_assignment_notification,
    queue_comment_notification,
)


@pytest.mark.django_db
def test_assignment_and_comment_notifications_use_bounded_outbox(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    first = queue_assignment_notification(assignment)
    second = queue_comment_notification(assignment, people["employee"])
    assert first.recipient == people["employee"]
    assert second is not None and second.recipient == people["manager"]
    result = deliver_due_notifications()
    assert result.sent == 2
    assert len(mail.outbox) == 2
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == second.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_smtp_failure_records_only_exception_type(
    monkeypatch, assignment: TaskAssignment
) -> None:
    delivery = queue_assignment_notification(assignment)

    def fail_send(*args, **kwargs):
        raise OSError("recipient@example.test must not be persisted in the error")

    monkeypatch.setattr("work.notifications.send_mail", fail_send)
    result = deliver_due_notifications()
    delivery.refresh_from_db()
    assert result.retried == 1
    assert delivery.attempts == 1
    assert delivery.last_error_type == "OSError"
    assert "@" not in delivery.last_error_type
    assert delivery.next_attempt_at > timezone.now()
