from datetime import timedelta
from importlib import import_module
from io import StringIO

from django.apps import apps
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.urls import reverse
from django.utils import timezone
import pytest

from accounts.agenda_directions import classify_agenda_direction
from accounts.forms import InstitutionUserChangeForm
from accounts.models import AgendaDirection, User
from work.admin import OrganizationUnitAdminForm, ReportingLineAdminForm
from work.models import (
    OrganizationMembership,
    OrganizationUnit,
    OrganizationUnitLink,
    ReportingLine,
)
from work.services import (
    organization_state_token,
    unit_hierarchy_state_token,
    update_unit_hierarchy,
    update_user_organization,
)


def create_it_admin(alias: str = "it_admin") -> User:
    return User.objects.create_user(
        f"{alias}@example.test",
        login_alias=alias,
        is_active=True,
        is_staff=True,
        is_superuser=True,
        is_it_admin=True,
    )


@pytest.mark.django_db
def test_user_history_excludes_credentials_and_tracks_groups() -> None:
    actor = create_it_admin()
    user = User.objects.create_user(
        "member@example.test", login_alias="member", first_name="Initial"
    )
    assert "password" not in {field.name for field in user.history.model._meta.fields}
    assert "last_login" not in {field.name for field in user.history.model._meta.fields}

    user.first_name = "Corrige"
    user._history_user = actor  # type: ignore[attr-defined]
    user.save(update_fields=["first_name"])
    group = Group.objects.create(name="Groupe technique")
    user.groups.add(group)

    latest = user.history.latest()
    assert latest.first_name == "Corrige"
    assert latest.history_user == actor
    assert latest.groups.filter(group=group).exists()


@pytest.mark.django_db
def test_populated_history_baseline_covers_users_units_links_and_m2m() -> None:
    user = User.objects.create_user("baseline@example.test", login_alias="baseline")
    group = Group.objects.create(name="Baseline")
    user.groups.add(group)
    parent = OrganizationUnit.objects.create(
        code="BASE-P", short_name="Parent", long_name="Parent"
    )
    child = OrganizationUnit.objects.create(
        code="BASE-C", short_name="Enfant", long_name="Enfant"
    )
    link = OrganizationUnitLink.objects.create(
        supervisor_service=parent, collaborator_service=child
    )
    accounts_migration = import_module("accounts.migrations.0004_populate_user_history")
    work_migration = import_module("work.migrations.0019_populate_organization_history")

    accounts_migration.populate_user_history(apps, None)
    work_migration.populate_organization_history(apps, None)

    assert user.history.filter(
        history_change_reason=accounts_migration.BASELINE_REASON
    ).exists()
    user_baseline = user.history.filter(
        history_change_reason=accounts_migration.BASELINE_REASON
    ).latest()
    assert user_baseline.groups.filter(group=group).exists()
    assert parent.history.filter(
        history_change_reason=work_migration.BASELINE_REASON
    ).exists()
    assert link.history.filter(
        history_change_reason=work_migration.BASELINE_REASON
    ).exists()


def test_agenda_direction_unit_rule_prioritizes_branches_then_unit_kind() -> None:
    parents = {
        "DP": "DG",
        "DP-CELL": "DP",
        "DAF": "DG",
        "DAF-LAB": "DAF",
        "FREE-LAB": "DG",
        "FREE-CELL": "PSPI",
        "PSPI": "DG",
        "DG": None,
    }

    assert (
        classify_agenda_direction(
            unit_code="DP-CELL", unit_kind="cell", parent_by_code=parents
        )
        == AgendaDirection.PROGRAMS
    )
    assert (
        classify_agenda_direction(
            unit_code="DAF-LAB", unit_kind="laboratory", parent_by_code=parents
        )
        == AgendaDirection.ADMINISTRATION
    )
    assert (
        classify_agenda_direction(
            unit_code="FREE-LAB", unit_kind="laboratory", parent_by_code=parents
        )
        == AgendaDirection.PROGRAMS
    )
    assert (
        classify_agenda_direction(
            unit_code="FREE-CELL", unit_kind="cell", parent_by_code=parents
        )
        == AgendaDirection.ADMINISTRATION
    )
    assert (
        classify_agenda_direction(
            unit_code="PSPI", unit_kind="pole", parent_by_code=parents
        )
        == ""
    )


@pytest.mark.django_db
def test_agenda_direction_migration_preserves_choices_and_audits_backfill() -> None:
    root = OrganizationUnit.objects.create(
        code="M-DG", short_name="Racine", long_name="Racine", kind="direction"
    )
    programs = OrganizationUnit.objects.create(
        code="DP", short_name="Programmes", long_name="Programmes", kind="direction"
    )
    administration = OrganizationUnit.objects.create(
        code="DAF",
        short_name="Administration",
        long_name="Administration",
        kind="direction",
    )
    programs_cell = OrganizationUnit.objects.create(
        code="M-DP-CELL",
        short_name="Cellule DP",
        long_name="Cellule DP",
        kind="cell",
    )
    administration_lab = OrganizationUnit.objects.create(
        code="M-DAF-LAB",
        short_name="Laboratoire DAF",
        long_name="Laboratoire DAF",
        kind="laboratory",
    )
    strategic_pole = OrganizationUnit.objects.create(
        code="M-PSPI",
        short_name="PSPI",
        long_name="PSPI",
        kind="pole",
    )
    strategic_cell = OrganizationUnit.objects.create(
        code="M-PSPI-CELL",
        short_name="Cellule PSPI",
        long_name="Cellule PSPI",
        kind="cell",
    )
    for parent, child in (
        (root, programs),
        (root, administration),
        (programs, programs_cell),
        (administration, administration_lab),
        (root, strategic_pole),
        (strategic_pole, strategic_cell),
    ):
        OrganizationUnitLink.objects.create(
            supervisor_service=parent, collaborator_service=child
        )

    dp_user = User.objects.create_user("migration-dp@example.test")
    daf_user = User.objects.create_user("migration-daf@example.test")
    pspi_cell_user = User.objects.create_user("migration-cell@example.test")
    transversal_user = User.objects.create_user("migration-pole@example.test")
    manual_user = User.objects.create_user(
        "migration-manual@example.test",
        agenda_direction=AgendaDirection.ADMINISTRATION,
    )
    for user, unit in (
        (dp_user, programs_cell),
        (daf_user, administration_lab),
        (pspi_cell_user, strategic_cell),
        (transversal_user, strategic_pole),
        (manual_user, programs_cell),
    ):
        OrganizationMembership.objects.create(
            user=user,
            unit=unit,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    group = Group.objects.create(name="Migration direction")
    permission = Permission.objects.order_by("pk").first()
    assert permission is not None
    dp_user.groups.add(group)
    dp_user.user_permissions.add(permission)

    migration = import_module("accounts.migrations.0006_classify_agenda_directions")

    class SchemaEditor:
        connection = connection

    migration.classify_agenda_directions(apps, SchemaEditor())

    for user in (dp_user, daf_user, pspi_cell_user, transversal_user, manual_user):
        user.refresh_from_db()
    assert dp_user.agenda_direction == AgendaDirection.PROGRAMS
    assert daf_user.agenda_direction == AgendaDirection.ADMINISTRATION
    assert pspi_cell_user.agenda_direction == AgendaDirection.ADMINISTRATION
    assert transversal_user.agenda_direction == ""
    assert manual_user.agenda_direction == AgendaDirection.ADMINISTRATION

    history = dp_user.history.filter(
        history_change_reason=migration.CLASSIFICATION_REASON
    ).latest()
    assert history.agenda_direction == AgendaDirection.PROGRAMS
    assert history.groups.filter(group=group).exists()
    assert history.user_permissions.filter(permission=permission).exists()
    assert not transversal_user.history.filter(
        history_change_reason=migration.CLASSIFICATION_REASON
    ).exists()
    assert not manual_user.history.filter(
        history_change_reason=migration.CLASSIFICATION_REASON
    ).exists()

    migration.classify_agenda_directions(apps, SchemaEditor())
    assert (
        dp_user.history.filter(
            history_change_reason=migration.CLASSIFICATION_REASON
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_dg_exclusion_migration_is_audited_and_idempotent() -> None:
    dg = User.objects.create_user("direction@example.test", login_alias="dg")
    group = Group.objects.create(name="Lecture direction")
    permission = Permission.objects.order_by("pk").first()
    assert permission is not None
    dg.groups.add(group)
    dg.user_permissions.add(permission)
    migration = import_module(
        "accounts.migrations.0007_user_include_in_direction_agendas"
    )

    class SchemaEditor:
        connection = connection

    migration.exclude_dg_from_direction_agendas(apps, SchemaEditor())
    dg.refresh_from_db()

    assert dg.include_in_direction_agendas is False
    history = dg.history.filter(history_change_reason=migration.EXCLUSION_REASON).latest()
    assert history.include_in_direction_agendas is False
    assert history.groups.filter(group=group).exists()
    assert history.user_permissions.filter(permission=permission).exists()

    migration.exclude_dg_from_direction_agendas(apps, SchemaEditor())
    assert (
        dg.history.filter(history_change_reason=migration.EXCLUSION_REASON).count() == 1
    )


@pytest.mark.django_db
def test_unit_link_requires_one_parent_and_rejects_cycles() -> None:
    first = OrganizationUnit.objects.create(code="ONE", short_name="One", long_name="One")
    second = OrganizationUnit.objects.create(
        code="TWO", short_name="Two", long_name="Two"
    )
    child = OrganizationUnit.objects.create(
        code="CHILD", short_name="Child", long_name="Child"
    )
    OrganizationUnitLink.objects.create(
        supervisor_service=first, collaborator_service=child
    )
    with pytest.raises(ValidationError, match="deja une unite superieure"):
        OrganizationUnitLink.objects.create(
            supervisor_service=second, collaborator_service=child
        )
    with pytest.raises(ValidationError, match="boucle"):
        OrganizationUnitLink.objects.create(
            supervisor_service=child, collaborator_service=first
        )


@pytest.mark.django_db
def test_user_admin_form_exposes_current_organization_like_groups() -> None:
    unit = OrganizationUnit.objects.create(
        code="FORM", short_name="Form", long_name="Unite formulaire"
    )
    user = User.objects.create_user("form@example.test", login_alias="form")
    OrganizationMembership.objects.create(
        user=user,
        unit=unit,
        start_date=timezone.localdate(),
        is_primary=True,
    )

    form = InstitutionUserChangeForm(instance=user)

    assert form.initial["organization_units"] == {unit.pk}
    assert form.initial["primary_unit"] == unit.pk
    assert form.initial["organization_state"] == organization_state_token(user)
    assert isinstance(form.fields["organization_units"].widget, FilteredSelectMultiple)
    assert form.fields["organization_units"].label == ""
    assert form.fields["organization_units"].widget.verbose_name == "unités actuelles"


@pytest.mark.django_db
def test_user_admin_organization_selector_has_no_trailing_external_label(client) -> None:
    actor = create_it_admin()
    user = User.objects.create_user("selector@example.test", login_alias="selector")
    client.force_login(actor)

    response = client.get(reverse("admin:accounts_user_change", args=(user.pk,)))
    content = response.content.decode()

    assert response.status_code == 200
    assert '<label for="id_organization_units"></label>' in content
    assert 'data-field-name="unités actuelles"' in content
    assert 'aria-label="Unités actuelles"' in content
    assert "accounts/admin_organization.css" in content


@pytest.mark.django_db
def test_reporting_line_form_derives_primary_employee_unit() -> None:
    unit = OrganizationUnit.objects.create(
        code="DERIVE", short_name="Derive", long_name="Unite deduite"
    )
    supervisor = User.objects.create_user("supervisor@example.test")
    employee = User.objects.create_user("employee-form@example.test")
    today = timezone.localdate()
    for user in (supervisor, employee):
        OrganizationMembership.objects.create(
            user=user, unit=unit, start_date=today, is_primary=True
        )
    form = ReportingLineAdminForm(
        data={
            "employee": employee.pk,
            "supervisor": supervisor.pk,
            "start_date": today.isoformat(),
            "end_date": "",
            "is_primary": "on",
            "secondary_unit": "",
        }
    )

    assert form.is_valid(), form.errors
    assert form.save(commit=False).unit == unit


@pytest.mark.django_db
def test_unit_admin_form_and_service_replace_children_with_stale_guard() -> None:
    actor = create_it_admin()
    root = OrganizationUnit.objects.create(
        code="ROOT", short_name="Root", long_name="Racine"
    )
    first = OrganizationUnit.objects.create(
        code="FIRST", short_name="First", long_name="Premiere"
    )
    second = OrganizationUnit.objects.create(
        code="SECOND", short_name="Second", long_name="Deuxieme"
    )
    token = unit_hierarchy_state_token(root)
    update_unit_hierarchy(
        actor=actor,
        unit=root,
        parent_id=None,
        child_ids={first.pk, second.pk},
        expected_token=token,
    )
    assert set(
        root.collaborator_links.values_list("collaborator_service_id", flat=True)
    ) == {
        first.pk,
        second.pk,
    }
    with pytest.raises(ValidationError, match="a change"):
        update_unit_hierarchy(
            actor=actor,
            unit=root,
            parent_id=None,
            child_ids=set(),
            expected_token=token,
        )
    form = OrganizationUnitAdminForm(instance=root)
    assert set(form.initial["child_units"]) == {first.pk, second.pk}


@pytest.mark.django_db
def test_update_user_organization_dates_relations_and_rejects_stale_state() -> None:
    actor = create_it_admin()
    root = OrganizationUnit.objects.create(
        code="ORG-R", short_name="Root", long_name="Racine"
    )
    child = OrganizationUnit.objects.create(
        code="ORG-C", short_name="Child", long_name="Enfant"
    )
    OrganizationUnitLink.objects.create(
        supervisor_service=root, collaborator_service=child
    )
    supervisor = User.objects.create_user("manager-org@example.test")
    employee = User.objects.create_user("employee-org@example.test")
    old_unit = OrganizationUnit.objects.create(
        code="OLD", short_name="Old", long_name="Ancienne"
    )
    day = timezone.localdate()
    OrganizationMembership.objects.create(
        user=supervisor, unit=root, start_date=day - timedelta(days=30), is_primary=True
    )
    OrganizationMembership.objects.create(
        user=employee, unit=old_unit, start_date=day - timedelta(days=30), is_primary=True
    )
    token = organization_state_token(employee)

    update_user_organization(
        actor=actor,
        user=employee,
        unit_ids={child.pk},
        primary_unit_id=child.pk,
        supervisor_id=supervisor.pk,
        effective_date=day,
        expected_token=token,
    )

    old_membership = OrganizationMembership.objects.get(user=employee, unit=old_unit)
    assert old_membership.end_date == day - timedelta(days=1)
    assert OrganizationMembership.objects.get(
        user=employee, unit=child, end_date__isnull=True
    ).is_primary
    assert (
        ReportingLine.objects.get(employee=employee, end_date__isnull=True).supervisor
        == supervisor
    )
    with pytest.raises(ValidationError, match="a change"):
        update_user_organization(
            actor=actor,
            user=employee,
            unit_ids={child.pk},
            primary_unit_id=child.pk,
            supervisor_id=supervisor.pk,
            effective_date=day,
            expected_token=token,
        )


@pytest.mark.django_db
def test_membership_admin_unit_filter_is_an_autocomplete_datalist(client) -> None:
    actor = create_it_admin()
    unit = OrganizationUnit.objects.create(
        code="AUTO", short_name="Auto", long_name="Unite autocomplete"
    )
    user = User.objects.create_user("auto@example.test", login_alias="auto")
    OrganizationMembership.objects.create(
        user=user, unit=unit, start_date=timezone.localdate(), is_primary=True
    )
    client.force_login(actor)

    response = client.get(
        reverse("admin:work_organizationmembership_changelist"),
        {"unit_code": "AUTO"},
    )

    assert response.status_code == 200
    assert b"unit-filter-options-unit_code" in response.content
    assert b"Unite autocomplete" in response.content


@pytest.mark.django_db
def test_reconcile_command_dry_run_then_changes_primary_line() -> None:
    actor = create_it_admin("operator")
    root = OrganizationUnit.objects.create(
        code="CMD-R", short_name="Root", long_name="Racine commande"
    )
    child = OrganizationUnit.objects.create(
        code="CMD-C", short_name="Child", long_name="Enfant commande"
    )
    OrganizationUnitLink.objects.create(
        supervisor_service=root, collaborator_service=child
    )
    supervisor = User.objects.create_user(
        "command-manager@example.test", login_alias="cmd_manager"
    )
    employee = User.objects.create_user(
        "command-employee@example.test", login_alias="cmd_employee"
    )
    today = timezone.localdate()
    OrganizationMembership.objects.create(
        user=supervisor, unit=root, start_date=today, is_primary=True
    )
    output = StringIO()
    options = {
        "actor": actor.login_alias,
        "effective_date": today.isoformat(),
        "primary_membership": [f"{employee.login_alias}:{child.code}"],
        "line": [f"{employee.login_alias}:{supervisor.login_alias}"],
        "stdout": output,
    }
    call_command("reconcile_organization", dry_run=True, **options)
    assert not OrganizationMembership.objects.filter(user=employee).exists()

    call_command("reconcile_organization", confirm=True, **options)

    assert ReportingLine.objects.filter(
        employee=employee, supervisor=supervisor, unit=child, end_date__isnull=True
    ).exists()


@pytest.mark.django_db
def test_retire_command_only_deletes_unreferenced_inactive_units() -> None:
    actor = create_it_admin("retire_operator")
    removable = OrganizationUnit.objects.create(
        code="REMOVE", short_name="Remove", long_name="A retirer", active=False
    )
    removable.history.update(history_date=timezone.now() - timedelta(days=30))
    protected = OrganizationUnit.objects.create(
        code="KEEP", short_name="Keep", long_name="A conserver", active=False
    )
    user = User.objects.create_user("keep@example.test")
    OrganizationMembership.objects.create(
        user=user,
        unit=protected,
        start_date=timezone.localdate() - timedelta(days=30),
        is_primary=False,
    )
    options = {
        "actor": actor.login_alias,
        "protect_since": timezone.localdate().isoformat(),
    }
    call_command(
        "retire_inactive_units",
        unit=[removable.code],
        dry_run=True,
        **options,
    )
    assert OrganizationUnit.objects.filter(pk=removable.pk).exists()
    call_command(
        "retire_inactive_units",
        unit=[removable.code],
        confirm=True,
        **options,
    )
    assert not OrganizationUnit.objects.filter(pk=removable.pk).exists()
    with pytest.raises(CommandError, match="references metier"):
        call_command(
            "retire_inactive_units",
            unit=[protected.code],
            dry_run=True,
            **options,
        )
