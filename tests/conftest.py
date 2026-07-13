from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import User
from work.models import (
    ActionPlan,
    InstitutionalAction,
    OrganizationUnit,
    StrategicPlan,
    Task,
    TaskAssignment,
    WorkCalendar,
    default_work_calendar_id,
)
from work.services import set_primary_supervisor, week_start_for


@pytest.fixture
def unit(db) -> OrganizationUnit:
    return OrganizationUnit.objects.create(code="IT", name="Service IT")


@pytest.fixture
def people(db, unit: OrganizationUnit) -> dict[str, User]:
    users = {
        "manager": User.objects.create_user("manager@example.test", first_name="Awa"),
        "observer": User.objects.create_user("observer@example.test", first_name="Yao"),
        "employee": User.objects.create_user(
            "employee@example.test", first_name="Mariam"
        ),
        "outsider": User.objects.create_user("outside@example.test", first_name="Jean"),
    }
    monday = week_start_for(timezone.localdate())
    set_primary_supervisor(
        employee=users["employee"],
        supervisor=users["manager"],
        unit_id=unit.pk,
        start_date=monday,
    )
    from work.models import ReportingLine

    ReportingLine.objects.create(
        employee=users["employee"],
        supervisor=users["observer"],
        unit=unit,
        start_date=monday,
        is_primary=False,
    )
    return users


@pytest.fixture
def action(db) -> InstitutionalAction:
    plan = StrategicPlan.objects.create(
        name="Plan test",
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=365),
    )
    action_plan = ActionPlan.objects.create(
        strategic_plan=plan, name="Plan d'action test", code="PA-TEST"
    )
    return InstitutionalAction.objects.create(
        action_plan=action_plan, name="Action test", code="ACT-TEST"
    )


@pytest.fixture
def assignment(
    db, people: dict[str, User], action: InstitutionalAction
) -> TaskAssignment:
    monday = week_start_for(timezone.localdate())
    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    task = Task.objects.create(
        code="TSK-TEST",
        title="Tester le prototype",
        description="Tache fictive.",
        action=action,
        created_by=people["manager"],
    )
    return TaskAssignment.objects.create(
        task=task,
        employee=people["employee"],
        manager=people["manager"],
        start_date=monday,
        due_date=calendar.due_date_for(monday, Decimal("5.00")),
        estimated_work_days=Decimal("5.00"),
        calendar=calendar,
        status="active",
    )
