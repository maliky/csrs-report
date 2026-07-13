from django.core.management import call_command
from django.db import models
from django.db.models import Count
from django.utils import timezone
from django.utils.crypto import get_random_string
import pytest

from accounts.models import User
from work.models import (
    NotificationDelivery,
    ProgressEntry,
    ProposalStatus,
    ReportingLine,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskProposal,
)
from work.management.commands.seed_pilot_users import PILOT_USERS


@pytest.mark.django_db
def test_pilot_seed_is_dry_runnable_replacing_legacy_and_idempotent(
    monkeypatch,
) -> None:
    demo_password = f"Demo9!{get_random_string(18)}"
    admin_password = f"Admin9!{get_random_string(18)}"
    monkeypatch.setenv("CSRS_DEMO_PASSWORD", demo_password)
    monkeypatch.setenv("CSRS_ADMIN_PASSWORD", admin_password)
    call_command("seed_demo", verbosity=0)
    assert User.objects.count() == 3

    call_command(
        "seed_pilot_users",
        dry_run=True,
        replace_legacy=True,
        reset_password=True,
        verbosity=0,
    )
    assert User.objects.count() == 3

    call_command(
        "seed_pilot_users",
        replace_legacy=True,
        reset_password=True,
        verbosity=0,
    )
    assert User.objects.count() == len(PILOT_USERS)
    assert not User.objects.filter(email__endswith="@example.invalid").exists()
    assert (
        ReportingLine.objects.filter(is_primary=True, end_date__isnull=True).count()
        == len(PILOT_USERS) - 2
    )
    assignments = TaskAssignment.objects.filter(task__code__startswith="PIL-")
    assert assignments.count() == 73
    progress_count = ProgressEntry.objects.filter(assignment__in=assignments).count()
    long_running = assignments.filter(task__code__endswith="-01").exclude(
        task__code__startswith="PIL-DG-"
    )
    signatures = {
        tuple(
            assignment.progress_entries.order_by("entry_date").values_list(
                "entry_date", "percentage"
            )
        )
        for assignment in long_running
    }
    assert len(signatures) == long_running.count()
    assert TaskProposal.objects.count() == 42
    assert TaskActivity.objects.filter(assignment__in=assignments).count() >= 100
    assert NotificationDelivery.objects.count() == 0

    call_command("seed_pilot_users", verbosity=0)
    assert User.objects.count() == len(PILOT_USERS)
    assert (
        ReportingLine.objects.filter(is_primary=True, end_date__isnull=True).count()
        == len(PILOT_USERS) - 2
    )
    assert TaskAssignment.objects.filter(task__code__startswith="PIL-").count() == 73
    assert TaskProposal.objects.count() == 42
    assert (
        ProgressEntry.objects.filter(assignment__task__code__startswith="PIL-").count()
        == progress_count
    )

    dev = User.objects.get(login_alias="dev")
    assert dev.is_superuser and dev.is_staff and dev.is_it_admin
    assert dev.check_password(admin_password)
    assert User.objects.exclude(login_alias="dev").filter(is_superuser=True).count() == 0
    assert all(
        user.check_password(demo_password)
        for user in User.objects.exclude(login_alias="dev")
    )

    statuses = dict(
        TaskProposal.objects.values_list("status").annotate(total=Count("id"))
    )
    assert statuses == {
        ProposalStatus.ACCEPTED: 14,
        ProposalStatus.REJECTED: 14,
        ProposalStatus.SUBMITTED: 14,
    }
    forbidden = ("test", "fictif", "scenario", "demo", "pilote")
    visible_text = " ".join(
        [
            *Task.objects.values_list("title", flat=True),
            *Task.objects.values_list("description", flat=True),
            *ProgressEntry.objects.values_list("note", flat=True),
            *TaskActivity.objects.values_list("message", flat=True),
            *TaskProposal.objects.values_list("title", flat=True),
            *TaskProposal.objects.values_list("description", flat=True),
        ]
    ).lower()
    assert not any(word in visible_text for word in forbidden)
    assert not Task.objects.filter(
        code__startswith="PIL-", title__contains=" — "
    ).exists()
    messages = list(
        TaskActivity.objects.filter(assignment__in=assignments).values_list(
            "message", flat=True
        )
    )
    assert len(messages) == len(set(messages))
    assert TaskActivity.objects.filter(kind="reopened").exists()
    assert TaskActivity.objects.filter(kind="validated").exists()
    assert assignments.filter(status="active", due_date__lt=timezone.localdate()).exists()
    assert assignments.filter(
        status="completed", completed_at__date__lt=models.F("due_date")
    ).exists()


@pytest.mark.django_db
def test_pilot_hierarchy_matches_revised_tree(monkeypatch) -> None:
    monkeypatch.setenv("CSRS_DEMO_PASSWORD", f"Demo9!{get_random_string(18)}")
    monkeypatch.setenv("CSRS_ADMIN_PASSWORD", f"Admin9!{get_random_string(18)}")
    call_command("seed_pilot_users", verbosity=0)

    def direct_children(alias: str) -> set[str]:
        return set(
            ReportingLine.objects.filter(
                supervisor__login_alias=alias,
                is_primary=True,
                end_date__isnull=True,
            ).values_list("employee__login_alias", flat=True)
        )

    assert direct_children("dg") == {
        "daf",
        "drv",
        "drd",
        "ct",
        "rse",
        "genre",
        "ethique",
        "suivi",
        "controle",
    }
    assert direct_children("daf") == {
        "finances",
        "kpon",
        "rh",
        "i2a",
        "achats",
        "documentation",
    }
    assert direct_children("drv") == {
        "formation",
        "valorisation",
        "capitalisation",
    }
    assert direct_children("drd") == {
        "recherche",
        "clinique",
        "observatoire",
        "labo",
        "microscopie",
        "uar",
        "ressources",
    }
    assert direct_children("kpon") == {"atall"}
    assert direct_children("valorisation") == {
        "communication",
        "partenariat",
        "jardinier",
    }
    assert direct_children("recherche") == {
        "sante",
        "environnement",
        "securite",
        "societe",
        "biodiversite",
        "agriculture",
    }
    assert direct_children("patrimoine") == {"stations"}
