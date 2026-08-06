from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models
from django.db.models import Count
from django.test import override_settings
from django.utils import timezone
from django.utils.crypto import get_random_string
import pytest

from accounts.models import User
from access.models import GrantScope, RoleGrant, ScopedRole
from agenda.models import (
    VisitorVisit,
    WeeklyAgendaDraft,
    WeeklyAgendaVersion,
)
from processes.models import (
    ProcessCase,
    ProcessDefinition,
    ProcessDocument,
    ProcessEvent,
    ProcessSignature,
)
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
    Command,
    PILOT_USERS,
    UNIT_SHORT_NAMES,
    UNIT_SPECS,
)
from work.organogram import canonical_organogram_path


def test_pilot_dashboard_host_is_allowed_by_local_configuration() -> None:
    with override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1"]):
        assert Command._dashboard_request_host() == "localhost"


def test_pilot_dashboard_host_prefers_preproduction_configuration() -> None:
    with override_settings(
        ALLOWED_HOSTS=["localhost", "127.0.0.1", "preprod.example.com"]
    ):
        assert Command._dashboard_request_host() == "preprod.example.com"


def test_canonical_organogram_lives_in_docs() -> None:
    path = canonical_organogram_path()
    assert path.parent.name == "docs"
    assert path.name == "organogram.org"


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
    assert daf.long_name == "Direction administrative et financière"
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
            collaborator_service__code__in=("DAF", "CEX", "DP", "POOL", "PSPI"),
        ).count()
        == 5
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
    assert any("(communication-rse)" in message for message in messages)
    assert not any(
        "Direction administrative et financière" in message for message in messages
    )
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

    retained_aliases = set(Command._existing_scenario_users()) | {
        "dev",
        "secretariat_dg",
        "rh",
    }
    password_hashes = dict(
        User.objects.filter(login_alias__in=retained_aliases).values_list(
            "login_alias", "password"
        )
    )
    User.objects.exclude(login_alias__in=retained_aliases).delete()
    TaskProposal.objects.filter(title="Formaliser le tableau de priorités").update(
        title="Formaliser le tableau de priorites"
    )
    monkeypatch.delenv("CSRS_DEMO_PASSWORD")
    monkeypatch.delenv("CSRS_ADMIN_PASSWORD")

    call_command("seed_pilot_users", refresh_scenarios_only=True, verbosity=0)

    assert User.objects.count() == len(retained_aliases)
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
def test_clean_accounts_prunes_every_noncanonical_user_and_related_data(
    monkeypatch,
) -> None:
    demo_password = f"Demo9!{get_random_string(18)}"
    admin_password = f"Admin9!{get_random_string(18)}"
    monkeypatch.setenv("CSRS_DEMO_PASSWORD", demo_password)
    monkeypatch.setenv("CSRS_ADMIN_PASSWORD", admin_password)
    call_command("seed_pilot_users", verbosity=0)

    dg = User.objects.get(login_alias="dg")
    dg_id = dg.pk
    User.objects.filter(pk=dg_id).update(email="ancienne-dg@demo.invalid")
    duplicate = User.objects.create_user(
        "dg@demo.invalid", demo_password, login_alias="ancienne_dg"
    )
    obsolete = User.objects.create_user(
        "obsolete@example.test", demo_password, login_alias="obsolete"
    )
    obsolete_grant = RoleGrant.objects.create(
        user=obsolete,
        role=ScopedRole.objects.get(code="AGENDA_VIEWER"),
        unit=OrganizationUnit.objects.get(code="CA"),
        scope=GrantScope.UNIT_TREE,
        granted_by=User.objects.get(login_alias="dev"),
        grant_reason="Délégation liée à un ancien compte.",
    )
    obsolete_task = Task.objects.create(
        code="OBSOLETE-ACCOUNT-TASK",
        title="Donnée liée à un ancien compte",
        description="Cette tâche doit disparaître avec son auteur.",
        created_by=obsolete,
    )
    obsolete_visit = VisitorVisit.objects.create(
        party_size=1,
        recorded_by=obsolete,
        updated_by=obsolete,
    )
    obsolete_draft = WeeklyAgendaDraft.objects.create(
        week_start=timezone.localdate() - timedelta(days=timezone.localdate().weekday()),
        updated_by=obsolete,
    )
    obsolete_version = WeeklyAgendaVersion.objects.create(
        draft=obsolete_draft,
        week_start=obsolete_draft.week_start,
        version=1,
        snapshot={},
        snapshot_sha256="0" * 64,
        storage_provider="local",
        storage_key="agenda/obsolete.pdf",
        pdf_sha256="1" * 64,
        pdf_size=1,
        generated_by=obsolete,
    )
    obsolete_process = ProcessCase.objects.create(
        definition=ProcessDefinition.objects.create(
            code="OBSOLETE_CLEANUP", version=1, name="Nettoyage"
        ),
        reference="PROC-OBSOLETE-CLEANUP",
        initiator=obsolete,
        origin_unit=OrganizationUnit.objects.get(code="DG"),
        origin_unit_name="Direction générale",
        calendar_id=TaskAssignment.objects.filter(task__code__startswith="PIL-")
        .values_list("calendar", flat=True)
        .first(),
    )
    obsolete_event = ProcessEvent.objects.create(
        case=obsolete_process,
        actor=obsolete,
        kind="created",
        to_status="draft",
    )
    ProcessDocument.objects.create(
        case=obsolete_process,
        kind="other",
        provider="local",
        object_key="processes/obsolete.txt",
        original_name="obsolete.txt",
        content_type="text/plain",
        size=1,
        sha256="2" * 64,
        scan_status="clean",
        uploaded_by=obsolete,
    )
    ProcessSignature.objects.create(
        case=obsolete_process,
        signer=obsolete,
        event=obsolete_event,
        confirmation="Signature obsolète",
        snapshot={},
        snapshot_sha256="3" * 64,
        document_manifest=[],
    )

    with pytest.raises(CommandError, match="--confirm-prune"):
        call_command(
            "seed_pilot_users",
            prune_noncanonical_users=True,
            reset_password=True,
            verbosity=0,
        )

    output = StringIO()
    call_command(
        "seed_pilot_users",
        prune_noncanonical_users=True,
        reset_password=True,
        dry_run=True,
        stdout=output,
        verbosity=0,
    )
    assert "ancienne_dg" in output.getvalue()
    assert "obsolete" in output.getvalue()
    assert User.objects.filter(pk__in=(duplicate.pk, obsolete.pk)).count() == 2
    assert Task.objects.filter(pk=obsolete_task.pk).exists()
    assert VisitorVisit.objects.filter(pk=obsolete_visit.pk).exists()
    assert WeeklyAgendaVersion._base_manager.filter(pk=obsolete_version.pk).exists()
    assert ProcessCase.objects.filter(pk=obsolete_process.pk).exists()
    assert RoleGrant._base_manager.filter(pk=obsolete_grant.pk).exists()
    assert User.objects.get(pk=dg_id).email == "ancienne-dg@demo.invalid"

    call_command(
        "seed_pilot_users",
        prune_noncanonical_users=True,
        confirm_prune=True,
        reset_password=True,
        verbosity=0,
    )

    expected = {(spec.alias, spec.email) for spec in PILOT_USERS}
    assert len(PILOT_USERS) == 42
    assert set(User.objects.values_list("login_alias", "email")) == expected
    assert User.objects.get(login_alias="dg").pk == dg_id
    assert not Task.objects.filter(pk=obsolete_task.pk).exists()
    assert not VisitorVisit.objects.filter(pk=obsolete_visit.pk).exists()
    assert not WeeklyAgendaVersion._base_manager.filter(pk=obsolete_version.pk).exists()
    assert not ProcessCase.objects.filter(pk=obsolete_process.pk).exists()
    assert not RoleGrant._base_manager.filter(pk=obsolete_grant.pk).exists()


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
        "secretariat_dg",
        "coordination",
        "pilotage",
        "expertise",
        "programmes",
        "daf",
    }
    assert direct_children("pilotage") == {
        "controle",
        "controle_interne",
        "communication",
        "genre",
    }
    assert direct_children("daf") == {
        "finances",
        "kpon",
        "rh",
        "achats",
        "moyens",
        "documentation",
    }
    assert direct_children("programmes") == {
        "biodiversite",
        "sante",
        "agriculture",
        "societe",
        "clinique",
        "uar",
        "qualite",
        "plateforme",
        "stations",
    }
    assert direct_children("kpon") == {"atall"}
    assert direct_children("finances") == {"caissier", "comptable"}
    assert direct_children("biodiversite") == {"faune", "plantes"}
    assert direct_children("sante") == {
        "clinique_epi",
        "epidemiologie",
        "sante_publique",
    }
    assert direct_children("agriculture") == {"agroecologie", "nutrition"}
    assert direct_children("societe") == {"gouvernance", "economie"}
    assert direct_children("plateforme") == {"labo", "instrumentation", "donnees"}
