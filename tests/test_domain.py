from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from accounts.models import User
from work.models import (
    AssignmentStatus,
    ActivityKind,
    InstitutionalAction,
    OrganizationUnit,
    OrganizationUnitLink,
    ProgressEntry,
    ReportingLine,
    TaskAssignment,
    TaskActivity,
    WorkCalendar,
    default_work_calendar_id,
)
from work.services import (
    adjacent_period,
    can_self_assign,
    business_days_between,
    can_comment_assignment,
    can_manage_assignment,
    can_view_employee,
    close_early,
    deadline_level,
    DeadlineLevel,
    record_progress,
    reject_completion,
    remaining_projection,
    reporting_period,
    set_primary_membership,
    set_primary_supervisor,
    task_progress_series,
    validate_completion,
    week_start_for,
    workload_breakdown,
)


@pytest.mark.django_db
def test_projection_uses_baseline_then_observed_velocity(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    monday = week_start_for(timezone.localdate())
    ProgressEntry.objects.create(
        assignment=assignment,
        entry_date=monday,
        percentage=20,
        author=people["employee"],
    )
    initial = remaining_projection(assignment)
    assert initial.baseline_days == Decimal("4.0")
    assert initial.observed_days is None
    ProgressEntry.objects.create(
        assignment=assignment,
        entry_date=monday + timedelta(days=2),
        percentage=40,
        author=people["employee"],
    )
    projected = remaining_projection(assignment)
    assert projected.baseline_days == Decimal("3.0")
    assert projected.observed_days == Decimal("6.0")


@pytest.mark.django_db
def test_non_positive_velocity_has_no_observed_projection(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    monday = week_start_for(timezone.localdate())
    for day, percentage in ((monday, 40), (monday + timedelta(days=1), 40)):
        ProgressEntry.objects.create(
            assignment=assignment,
            entry_date=day,
            percentage=percentage,
            author=people["employee"],
        )
    assert remaining_projection(assignment).observed_days is None


@pytest.mark.django_db
def test_weekends_and_configured_holidays_are_excluded() -> None:
    from work.models import Holiday

    monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    Holiday.objects.create(day=monday + timedelta(days=1), name="Ferie test")
    assert business_days_between(monday, monday + timedelta(days=7)) == 4


@pytest.mark.django_db
def test_secondary_supervisor_can_comment_but_not_manage(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    observer = people["observer"]
    assert can_comment_assignment(observer, assignment)
    assert not can_manage_assignment(observer, assignment)
    with pytest.raises(PermissionDenied):
        close_early(observer, assignment, "Non autorise")


@pytest.mark.django_db
def test_hierarchical_visibility_has_no_artificial_depth_limit(
    unit: OrganizationUnit,
) -> None:
    users = [User.objects.create_user(f"u{i}@example.test") for i in range(5)]
    today = timezone.localdate()
    for manager, employee in zip(users[:-1], users[1:], strict=True):
        ReportingLine.objects.create(
            supervisor=manager,
            employee=employee,
            unit=unit,
            start_date=today,
            is_primary=True,
        )
    assert can_view_employee(users[0], users[3])
    assert can_view_employee(users[0], users[4])


@pytest.mark.django_db
def test_reporting_line_rejects_hierarchy_cycle(unit: OrganizationUnit) -> None:
    first = User.objects.create_user("first@example.test")
    second = User.objects.create_user("second@example.test")
    today = timezone.localdate()
    ReportingLine.objects.create(
        supervisor=first,
        employee=second,
        unit=unit,
        start_date=today,
        is_primary=True,
    )
    reverse = ReportingLine(
        supervisor=second,
        employee=first,
        unit=unit,
        start_date=today,
        is_primary=True,
    )
    with pytest.raises(ValidationError, match="boucle"):
        reverse.full_clean()


@pytest.mark.django_db
def test_service_links_are_separate_and_reject_hierarchy_cycles(
    unit: OrganizationUnit,
) -> None:
    finance = OrganizationUnit.objects.create(
        code="FIN-TEST",
        short_name="Finances",
        long_name="Service des finances",
    )
    accounting = OrganizationUnit.objects.create(
        code="CPT-TEST",
        short_name="Comptabilite",
        long_name="Service de la comptabilite",
    )
    OrganizationUnitLink.objects.create(
        supervisor_service=unit,
        collaborator_service=finance,
    )
    OrganizationUnitLink.objects.create(
        supervisor_service=finance,
        collaborator_service=accounting,
    )

    cycle = OrganizationUnitLink(
        supervisor_service=accounting,
        collaborator_service=unit,
    )
    with pytest.raises(ValidationError, match="boucle"):
        cycle.full_clean()


@pytest.mark.django_db
def test_primary_change_transfers_active_assignments(
    assignment: TaskAssignment, people: dict[str, User], unit: OrganizationUnit
) -> None:
    new_manager = User.objects.create_user("new@example.test")
    set_primary_supervisor(
        employee=people["employee"],
        supervisor=new_manager,
        unit_id=unit.pk,
        start_date=timezone.localdate(),
    )
    assignment.refresh_from_db()
    assert assignment.manager == new_manager
    assert can_manage_assignment(new_manager, assignment)
    assert not can_manage_assignment(people["manager"], assignment)


@pytest.mark.django_db
def test_hundred_percent_waits_for_manager_validation(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    record_progress(
        user=people["employee"],
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=100,
        note="Termine",
        blocked=False,
    )
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.AWAITING_VALIDATION
    validate_completion(people["manager"], assignment)
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.COMPLETED
    assert assignment.completed_at is not None


@pytest.mark.django_db
def test_manager_can_reject_completion_with_comment(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    assignment.status = AssignmentStatus.AWAITING_VALIDATION
    assignment.save(update_fields=["status"])
    reject_completion(people["manager"], assignment, "Ajouter la preuve.")
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE
    assert (
        assignment.activities.get(kind=ActivityKind.REJECTED).message
        == "Ajouter la preuve."
    )


@pytest.mark.django_db
def test_employee_cannot_backdate_progress(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    with pytest.raises(PermissionDenied):
        record_progress(
            user=people["employee"],
            assignment=assignment,
            entry_date=timezone.localdate() - timedelta(days=1),
            percentage=20,
            note="Tardif",
            blocked=False,
        )


@pytest.mark.django_db
def test_activity_is_immutable(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    comment = TaskActivity.objects.create(
        assignment=assignment,
        actor=people["employee"],
        kind=ActivityKind.COMMENT,
        message="Observation",
    )
    comment.message = "Ecrase"
    with pytest.raises(ValidationError):
        comment.save()


@pytest.mark.django_db
def test_root_user_can_manage_and_validate_personal_assignment(
    action: InstitutionalAction,
    unit: OrganizationUnit,
) -> None:
    root = User.objects.create_user("root@example.test")
    set_primary_membership(
        user=root, unit_id=unit.pk, start_date=timezone.localdate()
    )
    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    task = root.created_tasks.create(
        code="ROOT-01",
        title="Priorite de direction",
        description="Suivi",
        action=action,
    )
    assignment = TaskAssignment.objects.create(
        task=task,
        employee=root,
        manager=root,
        organization_unit=unit,
        start_date=timezone.localdate(),
        due_date=calendar.due_date_for(timezone.localdate(), Decimal("2.0")),
        estimated_work_days=Decimal("2.0"),
        calendar=calendar,
    )
    assert can_self_assign(root)
    assert can_manage_assignment(root, assignment)
    record_progress(
        user=root,
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=100,
        note="Travail termine",
        blocked=False,
    )
    validate_completion(root, assignment)
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.COMPLETED


def test_reporting_period_prefers_calendar_month_and_navigates() -> None:
    period = reporting_period(
        week="2026-07-06", month="2026-06", today=timezone.localdate()
    )
    assert period.start.isoformat() == "2026-06-01"
    assert period.end.isoformat() == "2026-06-30"
    assert adjacent_period(period, -1).query == "month=2026-05"


def test_workload_breakdown_uses_one_proportional_calculation() -> None:
    workload = workload_breakdown(Decimal("8.0"), 35)
    assert workload.completed_days == Decimal("2.8")
    assert workload.remaining_days == Decimal("5.2")
    assert workload.completed_days + workload.remaining_days == workload.total_days


@pytest.mark.django_db
def test_deadline_levels_and_profile_overrun(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    assignment.start_date = timezone.localdate() - timedelta(days=14)
    assignment.due_date = assignment.calendar.due_date_for(
        assignment.start_date, Decimal("5.0")
    )
    assignment.estimated_work_days = Decimal("5.0")
    assignment.save(update_fields=["start_date", "due_date", "estimated_work_days"])
    assignment.progress_entries.create(
        entry_date=timezone.localdate() - timedelta(days=12),
        percentage=20,
        author=people["employee"],
    )
    assignment.progress_entries.create(
        entry_date=timezone.localdate(),
        percentage=60,
        author=people["employee"],
    )
    period = reporting_period(today=timezone.localdate())
    series = task_progress_series(assignment, period)
    assert series.displayed_days > series.planned_days
    assert series.overrun_days > 0
    assert series.points[-1].percentage == 60
    assert (
        deadline_level(assignment, on_day=timezone.localdate(), percentage=60)
        == DeadlineLevel.OVERDUE
    )


@pytest.mark.django_db
def test_progress_uses_five_percent_steps_and_requires_explanation_for_variance(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    with pytest.raises(ValidationError, match="pas de 5"):
        record_progress(
            user=people["employee"],
            assignment=assignment,
            entry_date=timezone.localdate(),
            percentage=33,
            note="",
            blocked=False,
        )
    record_progress(
        user=people["employee"],
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=50,
        note="",
        blocked=False,
    )
    with pytest.raises(ValidationError, match="note est obligatoire"):
        record_progress(
            user=people["employee"],
            assignment=assignment,
            entry_date=timezone.localdate(),
            percentage=40,
            note="",
            blocked=False,
        )
    with pytest.raises(ValidationError, match="note est obligatoire"):
        record_progress(
            user=people["employee"],
            assignment=assignment,
            entry_date=timezone.localdate(),
            percentage=55,
            note="",
            blocked=True,
        )
    record_progress(
        user=people["employee"],
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=40,
        note="Verification complementaire necessaire.",
        blocked=False,
    )


@pytest.mark.django_db
def test_it_admin_can_record_precise_percentage(
    assignment: TaskAssignment,
) -> None:
    admin = User.objects.create_superuser("admin-progress@example.test", "Secret9!x")
    entry = record_progress(
        user=admin,
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=33,
        note="Ajustement administratif",
        blocked=False,
    )
    assert entry.percentage == 33
