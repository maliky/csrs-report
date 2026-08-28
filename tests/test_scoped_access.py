from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from access.models import GrantScope, RoleGrant, ScopedRole
from access.services import grant_role, revoke_role
from accounts.models import User
from work.models import (
    OrganizationMembership,
    OrganizationUnit,
    OrganizationUnitLink,
    Task,
    TaskAssignment,
    TaskProposal,
    WorkCalendar,
    default_work_calendar_id,
)
from work.services import (
    accept_proposal,
    can_manage_assignment,
    can_review_proposal,
    can_view_assignment,
    can_view_employee,
    create_assignment_for_user,
    record_progress,
    set_primary_membership,
    set_primary_supervisor,
    visible_assignments,
)


@pytest.fixture
def scoped_context(db) -> dict[str, object]:
    today = timezone.localdate()
    root = OrganizationUnit.objects.create(
        code="ROOT", short_name="root", long_name="Direction generale"
    )
    daf = OrganizationUnit.objects.create(
        code="DAF-X", short_name="daf", long_name="Direction financiere"
    )
    finances = OrganizationUnit.objects.create(
        code="FIN-X", short_name="finances", long_name="Service finances"
    )
    research = OrganizationUnit.objects.create(
        code="RES-X", short_name="recherche", long_name="Service recherche"
    )
    OrganizationUnitLink.objects.create(supervisor_service=root, collaborator_service=daf)
    OrganizationUnitLink.objects.create(
        supervisor_service=daf, collaborator_service=finances
    )
    OrganizationUnitLink.objects.create(
        supervisor_service=root, collaborator_service=research
    )

    users = {
        name: User.objects.create_user(f"{name}@example.test", first_name=name.title())
        for name in (
            "dg",
            "daf_manager",
            "finance_agent",
            "research_agent",
            "delegate_one",
            "delegate_two",
            "viewer",
            "outsider",
        )
    }
    admin = User.objects.create_superuser(
        "it@example.test", "Secret9!x", login_alias="it"
    )
    users["admin"] = admin
    OrganizationMembership.objects.create(
        user=users["dg"],
        unit=root,
        job_title="DG",
        start_date=today - timedelta(days=100),
        is_primary=True,
    )
    set_primary_supervisor(
        employee=users["daf_manager"],
        supervisor=users["dg"],
        unit_id=daf.pk,
        start_date=today - timedelta(days=90),
    )
    set_primary_supervisor(
        employee=users["finance_agent"],
        supervisor=users["daf_manager"],
        unit_id=finances.pk,
        start_date=today - timedelta(days=80),
    )
    set_primary_supervisor(
        employee=users["research_agent"],
        supervisor=users["dg"],
        unit_id=research.pk,
        start_date=today - timedelta(days=80),
    )
    for key in ("delegate_one", "delegate_two", "viewer"):
        OrganizationMembership.objects.create(
            user=users[key],
            unit=root,
            job_title="Direction adjointe",
            start_date=today - timedelta(days=30),
            is_primary=True,
        )

    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    task = Task.objects.create(
        code="ACCESS-FIN-1",
        title="Verifier les engagements",
        description="Controle financier",
        created_by=users["daf_manager"],
    )
    assignment = TaskAssignment.objects.create(
        task=task,
        employee=users["finance_agent"],
        manager=users["daf_manager"],
        organization_unit=finances,
        calendar=calendar,
        start_date=today - timedelta(days=14),
        due_date=calendar.due_date_for(today - timedelta(days=14), Decimal("5.0")),
        estimated_work_days=Decimal("5.0"),
        status="active",
    )
    research_task = Task.objects.create(
        code="ACCESS-RES-1",
        title="Verifier le protocole",
        description="Controle scientifique",
        created_by=users["dg"],
    )
    research_assignment = TaskAssignment.objects.create(
        task=research_task,
        employee=users["research_agent"],
        manager=users["dg"],
        organization_unit=research,
        calendar=calendar,
        start_date=today - timedelta(days=7),
        due_date=calendar.due_date_for(today - timedelta(days=7), Decimal("3.0")),
        estimated_work_days=Decimal("3.0"),
        status="active",
    )
    return {
        "users": users,
        "root": root,
        "daf": daf,
        "finances": finances,
        "research": research,
        "assignment": assignment,
        "research_assignment": research_assignment,
        "calendar": calendar,
    }


def _grant(
    context: dict[str, object],
    user_key: str,
    role_code: str,
    unit_key: str,
    scope: str = GrantScope.UNIT_TREE,
    *,
    valid_from=None,
    valid_until=None,
) -> RoleGrant:
    users = context["users"]
    assert isinstance(users, dict)
    return grant_role(
        actor=users["admin"],
        user=users[user_key],
        role=ScopedRole.objects.get(code=role_code),
        unit=context[unit_key],
        scope=scope,
        valid_from=valid_from or timezone.now() - timedelta(minutes=1),
        valid_until=valid_until,
        reason="Delegation fonctionnelle approuvee.",
    )


@pytest.mark.django_db
def test_two_delegates_manage_the_same_daf_scope_without_replacing_manager(
    scoped_context: dict[str, object],
) -> None:
    assignment = scoped_context["assignment"]
    users = scoped_context["users"]
    assert isinstance(assignment, TaskAssignment)
    assert isinstance(users, dict)
    original_manager_id = assignment.manager_id

    for user_key in ("delegate_one", "delegate_two"):
        _grant(scoped_context, user_key, "UNIT_MANAGER", "daf")
        assert can_view_assignment(users[user_key], assignment)
        assert can_manage_assignment(users[user_key], assignment)

    record_progress(
        user=users["delegate_one"],
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=25,
        note="Controle delegue effectue.",
        blocked=False,
    )
    assignment.refresh_from_db()
    assert assignment.manager_id == original_manager_id


@pytest.mark.django_db
def test_hierarchy_grant_sync_is_audited_idempotent_and_manager_only(
    scoped_context: dict[str, object],
) -> None:
    users = scoped_context["users"]
    assert isinstance(users, dict)
    first_output = StringIO()
    call_command("sync_hierarchy_role_grants", actor="it", stdout=first_output)

    grants = RoleGrant.objects.filter(role__code="UNIT_MANAGER")
    assert grants.count() == 2
    assert set(grants.values_list("user", "unit__code")) == {
        (users["dg"].pk, "ROOT"),
        (users["daf_manager"].pk, "DAF-X"),
    }
    assert not grants.filter(user=users["finance_agent"]).exists()
    assert set(grants.values_list("granted_by", flat=True)) == {users["admin"].pk}
    assert "creees=2 conservees=0" in first_output.getvalue()

    second_output = StringIO()
    call_command("sync_hierarchy_role_grants", actor="it", stdout=second_output)
    assert grants.count() == 2
    assert "creees=0 conservees=2" in second_output.getvalue()


@pytest.mark.django_db
def test_vice_dg_root_grant_covers_each_direction(
    scoped_context: dict[str, object],
) -> None:
    users = scoped_context["users"]
    assignment = scoped_context["assignment"]
    research_assignment = scoped_context["research_assignment"]
    assert isinstance(users, dict)
    assert isinstance(assignment, TaskAssignment)
    assert isinstance(research_assignment, TaskAssignment)
    _grant(scoped_context, "delegate_one", "UNIT_MANAGER", "root")

    assert can_manage_assignment(users["delegate_one"], assignment)
    assert can_manage_assignment(users["delegate_one"], research_assignment)


@pytest.mark.django_db
def test_exact_unit_and_tree_scopes_are_distinct(
    scoped_context: dict[str, object],
) -> None:
    assignment = scoped_context["assignment"]
    users = scoped_context["users"]
    assert isinstance(assignment, TaskAssignment)
    assert isinstance(users, dict)

    exact = _grant(
        scoped_context,
        "viewer",
        "UNIT_VIEWER",
        "daf",
        GrantScope.UNIT_ONLY,
    )
    assert not can_view_assignment(users["viewer"], assignment)
    revoke_role(actor=users["admin"], grant=exact, reason="Changement de portee.")
    _grant(scoped_context, "viewer", "UNIT_VIEWER", "daf")
    assert can_view_assignment(users["viewer"], assignment)
    assert not can_manage_assignment(users["viewer"], assignment)


@pytest.mark.django_db
def test_temporary_read_grant_exposes_old_scope_then_revokes_immediately(
    scoped_context: dict[str, object],
) -> None:
    assignment = scoped_context["assignment"]
    users = scoped_context["users"]
    assert isinstance(assignment, TaskAssignment)
    assert isinstance(users, dict)
    now = timezone.now()
    grant = _grant(
        scoped_context,
        "viewer",
        "UNIT_VIEWER",
        "daf",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(days=1),
    )
    assert assignment.start_date < timezone.localdate()
    assert can_view_assignment(users["viewer"], assignment)
    assert assignment.pk in visible_assignments(users["viewer"]).values_list(
        "pk", flat=True
    )

    revoke_role(actor=users["admin"], grant=grant, reason="Interim termine.")
    assert not can_view_assignment(users["viewer"], assignment)
    assert grant.history.count() == 2


@pytest.mark.django_db
def test_future_expired_and_inactive_grants_never_authorize(
    scoped_context: dict[str, object],
) -> None:
    assignment = scoped_context["assignment"]
    users = scoped_context["users"]
    daf = scoped_context["daf"]
    assert isinstance(assignment, TaskAssignment)
    assert isinstance(users, dict)
    assert isinstance(daf, OrganizationUnit)
    now = timezone.now()
    _grant(
        scoped_context,
        "viewer",
        "UNIT_VIEWER",
        "daf",
        valid_from=now + timedelta(days=1),
        valid_until=now + timedelta(days=2),
    )
    _grant(
        scoped_context,
        "viewer",
        "UNIT_VIEWER",
        "daf",
        valid_from=now - timedelta(days=2),
        valid_until=now - timedelta(days=1),
    )
    assert not can_view_assignment(users["viewer"], assignment)

    active = _grant(scoped_context, "delegate_two", "UNIT_VIEWER", "daf")
    assert can_view_assignment(users["delegate_two"], assignment)
    active.role.active = False
    active.role.save(update_fields=["active"])
    assert not can_view_assignment(users["delegate_two"], assignment)
    active.role.active = True
    active.role.save(update_fields=["active"])
    daf.active = False
    daf.save(update_fields=["active"])
    assert not can_view_assignment(users["delegate_two"], assignment)


@pytest.mark.django_db
def test_only_it_can_grant_revoke_and_grants_cannot_be_deleted(
    scoped_context: dict[str, object],
) -> None:
    users = scoped_context["users"]
    assert isinstance(users, dict)
    role = ScopedRole.objects.get(code="UNIT_VIEWER")
    with pytest.raises(PermissionDenied):
        grant_role(
            actor=users["outsider"],
            user=users["viewer"],
            role=role,
            unit=scoped_context["daf"],
            scope=GrantScope.UNIT_TREE,
            valid_from=timezone.now(),
            valid_until=None,
            reason="Tentative non autorisee.",
        )
    grant = _grant(scoped_context, "viewer", "UNIT_VIEWER", "daf")
    with pytest.raises(ValidationError, match="couvre deja"):
        _grant(scoped_context, "viewer", "UNIT_VIEWER", "daf")
    with pytest.raises(PermissionDenied):
        revoke_role(
            actor=users["outsider"], grant=grant, reason="Tentative non autorisee."
        )
    with pytest.raises(ValidationError, match="revoquee"):
        grant.delete()


@pytest.mark.django_db
def test_only_natural_manager_accepts_proposal(
    scoped_context: dict[str, object],
) -> None:
    users = scoped_context["users"]
    calendar = scoped_context["calendar"]
    finances = scoped_context["finances"]
    assert isinstance(users, dict)
    assert isinstance(calendar, WorkCalendar)
    assert isinstance(finances, OrganizationUnit)
    today = timezone.localdate()
    proposal = TaskProposal.objects.create(
        employee=users["finance_agent"],
        organization_unit=finances,
        title="Rapprocher les factures",
        description="Controler les pieces",
        calendar=calendar,
        start_date=today,
        due_date=calendar.due_date_for(today, Decimal("2.0")),
        estimated_work_days=Decimal("2.0"),
    )
    _grant(scoped_context, "delegate_one", "UNIT_MANAGER", "daf")

    assert not can_review_proposal(users["delegate_one"], proposal)
    with pytest.raises(PermissionDenied):
        accept_proposal(users["delegate_one"], proposal)
    accepted = accept_proposal(users["daf_manager"], proposal)

    assert accepted.manager == users["daf_manager"]
    assert accepted.organization_unit == finances
    proposal.refresh_from_db()
    assert proposal.reviewed_by == users["daf_manager"]


@pytest.mark.django_db
def test_delegated_pages_filter_other_units_and_enforce_posts(
    client, scoped_context: dict[str, object]
) -> None:
    users = scoped_context["users"]
    assignment = scoped_context["assignment"]
    research_assignment = scoped_context["research_assignment"]
    assert isinstance(users, dict)
    assert isinstance(assignment, TaskAssignment)
    assert isinstance(research_assignment, TaskAssignment)
    _grant(scoped_context, "viewer", "UNIT_VIEWER", "daf")
    client.force_login(users["viewer"])

    detail = client.get(reverse("assignment-detail", args=[assignment.pk]))
    hidden = client.get(reverse("assignment-detail", args=[research_assignment.pk]))
    edit = client.get(reverse("assignment-edit", args=[assignment.pk]))
    team = client.get(reverse("team-summary"))

    assert detail.status_code == 200
    assert hidden.status_code == 404
    assert edit.status_code == 403
    assert team.status_code == 200
    assert "Finance_Agent" in team.content.decode()


@pytest.mark.django_db
def test_viewer_reads_proposals_but_only_manager_can_decide(
    client, scoped_context: dict[str, object]
) -> None:
    users = scoped_context["users"]
    calendar = scoped_context["calendar"]
    finances = scoped_context["finances"]
    assert isinstance(users, dict)
    assert isinstance(calendar, WorkCalendar)
    assert isinstance(finances, OrganizationUnit)
    today = timezone.localdate()
    proposal = TaskProposal.objects.create(
        employee=users["finance_agent"],
        organization_unit=finances,
        title="Actualiser le plan de tresorerie",
        description="Consolider les besoins",
        calendar=calendar,
        start_date=today,
        due_date=calendar.due_date_for(today, Decimal("2.0")),
        estimated_work_days=Decimal("2.0"),
    )
    _grant(scoped_context, "viewer", "UNIT_VIEWER", "daf")
    client.force_login(users["viewer"])

    listing = client.get(reverse("proposal-list"))
    decision = client.post(
        reverse("proposal-decide", args=[proposal.pk]), {"action": "accept"}
    )

    assert proposal.title in listing.content.decode()
    assert "Valider" not in listing.content.decode()
    assert decision.status_code == 403


@pytest.mark.django_db
def test_manager_grant_limits_assignment_form_to_its_unit_tree(
    client, scoped_context: dict[str, object]
) -> None:
    users = scoped_context["users"]
    assert isinstance(users, dict)
    _grant(scoped_context, "delegate_one", "UNIT_MANAGER", "daf")
    client.force_login(users["delegate_one"])

    form = client.get(reverse("assignment-create"))
    content = form.content.decode()

    assert form.status_code == 200
    assert "Finance_Agent" in content
    assert "Research_Agent" not in content


@pytest.mark.django_db
def test_new_task_keeps_unit_snapshot_after_membership_transfer(
    scoped_context: dict[str, object],
) -> None:
    users = scoped_context["users"]
    calendar = scoped_context["calendar"]
    finances = scoped_context["finances"]
    research = scoped_context["research"]
    assert isinstance(users, dict)
    assert isinstance(calendar, WorkCalendar)
    assert isinstance(finances, OrganizationUnit)
    assert isinstance(research, OrganizationUnit)
    today = timezone.localdate()
    assignment = create_assignment_for_user(
        manager=users["daf_manager"],
        employee=users["finance_agent"],
        title="Consolider la tresorerie",
        description="Produire la situation",
        action=None,
        start_date=today,
        due_date=calendar.due_date_for(today, Decimal("2.0")),
        estimated_work_days=Decimal("2.0"),
        calendar=calendar,
    )
    _grant(scoped_context, "delegate_one", "UNIT_VIEWER", "finances")
    set_primary_membership(
        user=users["finance_agent"], unit_id=research.pk, start_date=today
    )
    assignment.refresh_from_db()

    assert assignment.organization_unit == finances
    assert can_view_assignment(users["delegate_one"], assignment)
    assert can_view_employee(users["delegate_one"], users["finance_agent"])
