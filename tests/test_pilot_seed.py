from io import StringIO

from django.core.management import call_command
from django.db import models
from django.db.models import Count
from django.utils import timezone
from django.utils.crypto import get_random_string
import pytest

from accounts.models import User
from work.models import (
    NotificationDelivery,
    OrganizationUnit,
    OrganizationUnitLink,
    OrganizationMembership,
    ProgressEntry,
    ProgressSeriesCache,
    ProposalStatus,
    ReportingLine,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskProposal,
)
from work.management.commands.seed_pilot_users import (
    PILOT_USERS,
    UNIT_SHORT_NAMES,
    UNIT_SPECS,
)


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
    pilot_unit_codes = [code for code, _name, _parent in UNIT_SPECS]
    assert OrganizationUnit.objects.filter(code__in=pilot_unit_codes).count() == len(
        UNIT_SPECS
    )
    assert (
        OrganizationUnitLink.objects.filter(
            supervisor_service__code__in=pilot_unit_codes,
            collaborator_service__code__in=pilot_unit_codes,
        ).count()
        == len(UNIT_SPECS) - 1
    )
    daf = OrganizationUnit.objects.get(code="DAF")
    assert daf.long_name == "Direction administrative et financiere"
    assert daf.short_name == "daf"
    assert (
        dict(
            OrganizationUnit.objects.filter(code__in=pilot_unit_codes).values_list(
                "code", "short_name"
            )
        )
        == UNIT_SHORT_NAMES
    )
    assert (
        OrganizationUnitLink.objects.filter(
            supervisor_service__code="DG",
            collaborator_service__code__in=("DAF", "DRV"),
        ).count()
        == 2
    )
    assert (
        ReportingLine.objects.filter(is_primary=True, end_date__isnull=True).count()
        == len(PILOT_USERS) - 2
    )
    assert (
        OrganizationMembership.objects.filter(
            is_primary=True, end_date__isnull=True
        ).count()
        == len(PILOT_USERS) - 1
    )
    assignments = TaskAssignment.objects.filter(task__code__startswith="PIL-")
    assert assignments.count() == 73
    assert not assignments.filter(organization_unit__isnull=True).exists()
    assert assignments.filter(estimated_work_days__lte=10).count() == 65
    assert assignments.filter(estimated_work_days__gt=10).count() == 8
    assert (
        assignments.filter(
            status="completed", completed_at__date=models.F("due_date")
        ).count()
        == 38
    )
    assert (
        assignments.filter(
            status="completed", completed_at__date__lt=models.F("due_date")
        ).count()
        == 8
    )
    assert assignments.filter(status="closed_early").count() == 5
    assert (
        assignments.filter(
            status="completed", completed_at__date__gt=models.F("due_date")
        ).count()
        == 10
    )
    assert (
        assignments.filter(status="active", due_date__gte=timezone.localdate()).count()
        == 7
    )
    assert (
        assignments.filter(status="active", due_date__lt=timezone.localdate()).count()
        == 5
    )
    assert ProgressSeriesCache.objects.filter(assignment__in=assignments).count() == 73
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
    assert not TaskProposal.objects.filter(organization_unit__isnull=True).exists()
    audit_output = StringIO()
    call_command(
        "audit_organization_scope",
        fail_on_unresolved=True,
        stdout=audit_output,
    )
    assert "affectations_sans_service=0" in audit_output.getvalue()
    assert TaskActivity.objects.filter(assignment__in=assignments).count() >= 100
    assert NotificationDelivery.objects.count() == 0

    original_activity = TaskActivity.objects.filter(
        assignment__in=assignments, kind="progress"
    ).first()
    assert original_activity is not None
    TaskActivity.objects.create(
        assignment=original_activity.assignment,
        kind="progress",
        actor=original_activity.actor,
        message="Correction remplacee lors du prochain chargement.",
        percentage_after=original_activity.percentage_after,
        supersedes=original_activity,
    )

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
    assert any("(formation)" in message for message in messages)
    assert not any("Direction administrative et financiere" in message for message in messages)
    assert not any(" a ete " in message or " apres " in message for message in messages)
    assert TaskActivity.objects.filter(kind="reopened").exists()
    assert (
        TaskActivity.objects.filter(assignment__in=assignments, kind="reopened")
        .values("assignment_id")
        .distinct()
        .count()
        == 3
    )
    assert TaskActivity.objects.filter(kind="validated").exists()
    assert assignments.filter(status="active", due_date__lt=timezone.localdate()).exists()
    assert assignments.filter(
        status="completed", completed_at__date__lt=models.F("due_date")
    ).exists()
    delayed_over_one_week = [
        assignment
        for assignment in assignments.select_related("calendar")
        if assignment.due_date
        < (
            assignment.completed_at.date()
            if assignment.completed_at
            else timezone.localdate()
        )
        and assignment.calendar.workdays_between(
            assignment.due_date,
            assignment.completed_at.date()
            if assignment.completed_at
            else timezone.localdate(),
        )
        > 5
    ]
    assert len(delayed_over_one_week) == 2
    assert any(
        assignment.status == "completed"
        and assignment.progress_entries.order_by("-entry_date").first().percentage == 100
        for assignment in delayed_over_one_week
    )

    retained_aliases = {spec.alias for spec in PILOT_USERS if spec.has_scenarios}
    password_hashes = dict(
        User.objects.filter(login_alias__in=retained_aliases).values_list(
            "login_alias", "password"
        )
    )
    User.objects.exclude(login_alias__in=retained_aliases).delete()
    TaskProposal.objects.filter(
        title="Formaliser le tableau de priorités"
    ).update(title="Formaliser le tableau de priorites")
    monkeypatch.delenv("CSRS_DEMO_PASSWORD")
    monkeypatch.delenv("CSRS_ADMIN_PASSWORD")

    call_command("seed_pilot_users", refresh_scenarios_only=True, verbosity=0)

    assert User.objects.count() == len(retained_aliases) == 16
    assert (
        dict(
            User.objects.filter(login_alias__in=retained_aliases).values_list(
                "login_alias", "password"
            )
        )
        == password_hashes
    )
    assert TaskAssignment.objects.filter(task__code__startswith="PIL-").count() == 73
    assert TaskProposal.objects.count() == 42
    assert not TaskProposal.objects.filter(
        title="Formaliser le tableau de priorites"
    ).exists()
    assert ProgressSeriesCache.objects.count() == 73


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
