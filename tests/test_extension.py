from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from work.forms import AssignmentCreateForm
from work.models import (
    ActivityKind,
    AssignmentStatus,
    InstitutionalAction,
    NotificationDelivery,
    OrganizationUnit,
    ReportingLine,
    TaskActivity,
    TaskAssignment,
    WorkCalendar,
    WorkCalendarDay,
)
from work.services import (
    create_assignment_for_user,
    daily_progress_rows,
    due_date_for,
    next_task_code,
    record_progress,
    reporting_period,
    team_tree,
    validate_completion,
    visible_activities,
    week_start_for,
)


@pytest.mark.django_db
def test_model_rejects_divergent_schedule_and_rounds_fractional_workload(
    assignment: TaskAssignment,
) -> None:
    expected = due_date_for(assignment.start_date, Decimal("2.5"), assignment.calendar)
    assignment.estimated_work_days = Decimal("2.5")
    assignment.due_date = expected
    assignment.full_clean()
    assignment.due_date += timedelta(days=1)
    with pytest.raises(ValidationError, match="calendrier retenu"):
        assignment.full_clean()


@pytest.mark.django_db
def test_creation_form_accepts_due_or_workload_and_normalizes_both(
    people: dict[str, User], action: InstitutionalAction
) -> None:
    start = week_start_for(timezone.localdate())
    calendar = WorkCalendar.objects.get(is_default=True)
    due = calendar.due_date_for(start, Decimal("3.0"))
    common = {
        "title": "Classer les justificatifs",
        "description": "Ranger les pieces du mois.",
        "employee": people["employee"].pk,
        "action": action.pk,
        "start_date": start.isoformat(),
        "calendar_overrides": "{}",
    }
    from_due = AssignmentCreateForm(
        {**common, "due_date": due.isoformat(), "schedule_source": "due"},
        manager=people["manager"],
        calendar=calendar,
    )
    assert from_due.is_valid(), from_due.errors
    assert from_due.cleaned_data["estimated_work_days"] == Decimal("3.0")
    from_workload = AssignmentCreateForm(
        {**common, "estimated_work_days": "2.5", "schedule_source": "workload"},
        manager=people["manager"],
        calendar=calendar,
    )
    assert from_workload.is_valid(), from_workload.errors
    assert from_workload.cleaned_data["due_date"] == due

    without_action = AssignmentCreateForm(
        {
            **common,
            "action": "",
            "start_date": start.strftime("%d/%m/%Y"),
            "estimated_work_days": "2.5",
            "schedule_source": "workload",
        },
        manager=people["manager"],
        calendar=calendar,
    )
    assert without_action.is_valid(), without_action.errors
    assert without_action.cleaned_data["action"] is None

    unbound = AssignmentCreateForm(manager=people["manager"], calendar=calendar)
    html = unbound.as_p()
    assert 'placeholder="jj/mm/aaaa"' in html
    assert f'value="{start:%d/%m/%Y}"' in html
    assert 'name="estimated_work_days" value="5"' in html


@pytest.mark.django_db
def test_calendar_version_is_retained_by_existing_assignment(
    assignment: TaskAssignment,
) -> None:
    old_calendar = assignment.calendar
    changed_day = old_calendar.due_date_for(assignment.start_date, Decimal("1.0"))
    new_calendar = WorkCalendar.objects.create(
        name="Cote d'Ivoire", version="version suivante"
    )
    WorkCalendarDay.objects.create(
        calendar=new_calendar,
        day=changed_day,
        name="Fermeture exceptionnelle",
        is_working_day=False,
    )
    assert old_calendar.due_date_for(assignment.start_date, Decimal("1.0")) == changed_day
    assert new_calendar.due_date_for(assignment.start_date, Decimal("1.0")) > changed_day
    assignment.refresh_from_db()
    assert assignment.calendar == old_calendar


@pytest.mark.django_db
def test_task_codes_are_normalized_and_sequential(
    action: InstitutionalAction,
) -> None:
    first = next_task_code(action, 2026)
    second = next_task_code(action, 2026)
    assert first == "ACT-TEST-2026-0001"
    assert second == "ACT-TEST-2026-0002"
    assert next_task_code(None, 2026) == "TACHE-2026-0001"
    assert next_task_code(None, 2026) == "TACHE-2026-0002"


@pytest.mark.django_db
def test_same_day_correction_supersedes_feed_but_keeps_database_history(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    today = timezone.localdate()
    record_progress(
        user=people["employee"],
        assignment=assignment,
        entry_date=today,
        percentage=20,
        note="Premier point.",
        blocked=False,
    )
    record_progress(
        user=people["employee"],
        assignment=assignment,
        entry_date=today,
        percentage=30,
        note="Valeur corrigee.",
        blocked=False,
    )
    visible = visible_activities(assignment).filter(kind=ActivityKind.PROGRESS)
    assert visible.count() == 1
    assert visible.get().message == "Valeur corrigee."
    assert TaskActivity.objects.filter(assignment=assignment).count() == 2
    assert assignment.progress_entries.get().history.count() == 2


@pytest.mark.django_db
def test_decreasing_completed_task_reopens_and_notifies_manager(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    yesterday = timezone.localdate() - timedelta(days=1)
    assignment.progress_entries.create(
        entry_date=yesterday,
        percentage=100,
        note="Acheve.",
        author=people["employee"],
    )
    assignment.status = AssignmentStatus.COMPLETED
    assignment.completed_at = timezone.now()
    assignment.save(update_fields=["status", "completed_at"])
    record_progress(
        user=people["employee"],
        assignment=assignment,
        entry_date=timezone.localdate(),
        percentage=80,
        note="Controle incomplet, je reprends le dossier.",
        blocked=False,
    )
    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE
    assert assignment.completed_at is None
    assert visible_activities(assignment).filter(kind=ActivityKind.REOPENED).exists()
    assert NotificationDelivery.objects.filter(
        recipient=people["manager"], event_type="task_reopened"
    ).exists()


@pytest.mark.django_db
def test_same_day_correction_uses_locked_completed_state_and_reopens(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    """A stale caller cannot leave a sub-100 task tagged as completed."""
    today = timezone.localdate()
    record_progress(
        user=people["employee"],
        assignment=assignment,
        entry_date=today,
        percentage=100,
        note="Travail annonce comme termine.",
        blocked=False,
    )
    stale_assignment = TaskAssignment.objects.get(pk=assignment.pk)
    assignment.refresh_from_db()
    validate_completion(people["manager"], assignment)

    record_progress(
        user=people["employee"],
        assignment=stale_assignment,
        entry_date=today,
        percentage=85,
        note="Une verification impose de reprendre le travail.",
        blocked=False,
    )

    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.ACTIVE
    assert assignment.completed_at is None
    assert assignment.progress_entries.get(entry_date=today).percentage == 85
    assert visible_activities(assignment).filter(kind=ActivityKind.REOPENED).exists()
    assert NotificationDelivery.objects.filter(
        recipient=people["manager"], event_type="task_reopened"
    ).exists()


@pytest.mark.django_db
def test_completion_validation_rechecks_that_current_progress_is_100(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    assignment.progress_entries.create(
        entry_date=timezone.localdate(),
        percentage=85,
        author=people["employee"],
    )
    TaskAssignment.objects.filter(pk=assignment.pk).update(
        status=AssignmentStatus.AWAITING_VALIDATION
    )
    assignment.refresh_from_db()

    with pytest.raises(ValidationError, match="100 %"):
        validate_completion(people["manager"], assignment)

    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.AWAITING_VALIDATION
    assert assignment.completed_at is None


@pytest.mark.django_db
def test_daily_rows_are_real_carried_and_stop_at_completion(
    assignment: TaskAssignment, people: dict[str, User]
) -> None:
    monday = assignment.start_date
    first = assignment.calendar.due_date_for(monday, Decimal("1.0"))
    third = assignment.calendar.due_date_for(monday, Decimal("3.0"))
    assignment.progress_entries.create(
        entry_date=first, percentage=25, author=people["employee"]
    )
    assignment.progress_entries.create(
        entry_date=third, percentage=70, author=people["employee"]
    )
    rows = daily_progress_rows(assignment, today=third)
    by_day = {row.day: row for row in rows}
    second = assignment.calendar.due_date_for(monday, Decimal("2.0"))
    assert by_day[monday].percentage == 0
    assert by_day[monday].observed is False
    assert by_day[first].percentage == 25
    assert by_day[first].observed is True
    assert by_day[second].percentage == 25
    assert by_day[second].observed is False
    assert by_day[third].percentage == 70
    assert by_day[third].observed is True
    assignment.completed_at = timezone.make_aware(datetime.combine(third, time(16)))
    assignment.status = AssignmentStatus.COMPLETED
    assignment.save(update_fields=["completed_at", "status"])
    assert (
        daily_progress_rows(assignment, today=third + timedelta(days=10))[-1].day == third
    )


@pytest.mark.django_db
def test_daily_rows_include_non_working_calendar_days(
    assignment: TaskAssignment,
) -> None:
    non_working_day = assignment.start_date + timedelta(days=5)
    rows = daily_progress_rows(assignment, today=non_working_day)
    by_day = {row.day: row for row in rows}

    assert len(rows) == (non_working_day - assignment.start_date).days + 1
    assert by_day[non_working_day].is_working_day is False
    assert (
        by_day[non_working_day].elapsed_work_days
        == by_day[non_working_day - timedelta(days=1)].elapsed_work_days
    )


@pytest.mark.django_db
def test_progress_json_has_chart_schema_and_task_permissions(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    assignment.start_date = date(2026, 4, 30)
    assignment.due_date = assignment.calendar.due_date_for(
        assignment.start_date, assignment.estimated_work_days
    )
    assignment.save(update_fields=["start_date", "due_date"])
    client.force_login(people["manager"])
    response = client.get(reverse("assignment-progress-json", args=[assignment.pk]))
    assert response.status_code == 200
    assert set(response.json()[0]) == {
        "task_id",
        "start_date",
        "day",
        "is_working_day",
        "due_date",
        "planned_work_days",
        "elapsed_work_days",
        "remaining_schedule_days",
        "overdue_days",
        "percentage",
        "observed",
    }
    labour_day = next(row for row in response.json() if row["day"] == "2026-05-01")
    assert labour_day["is_working_day"] is False
    client.force_login(people["outsider"])
    assert (
        client.get(reverse("assignment-progress-json", args=[assignment.pk])).status_code
        == 404
    )


@pytest.mark.django_db
def test_progress_json_observed_points_are_exactly_the_recorded_history(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    """The chart route must not replace task history with a generic profile."""
    assignment.start_date = timezone.localdate() - timedelta(days=14)
    assignment.due_date = assignment.calendar.due_date_for(
        assignment.start_date, assignment.estimated_work_days
    )
    assignment.save(update_fields=["start_date", "due_date"])
    first = assignment.calendar.due_date_for(assignment.start_date, Decimal("1.0"))
    second = assignment.calendar.due_date_for(assignment.start_date, Decimal("3.0"))
    assignment.progress_entries.create(
        entry_date=first,
        percentage=15,
        author=people["employee"],
    )
    assignment.progress_entries.create(
        entry_date=second,
        percentage=55,
        author=people["employee"],
    )
    client.force_login(people["employee"])

    rows = client.get(reverse("assignment-progress-json", args=[assignment.pk])).json()
    observed = [(row["day"], row["percentage"]) for row in rows if row["observed"]]

    assert observed == [(first.isoformat(), 15), (second.isoformat(), 55)]


@pytest.mark.django_db
def test_team_tree_contains_deep_descendants(
    people: dict[str, User], unit: OrganizationUnit
) -> None:
    child = User.objects.create_user("deep@example.test", first_name="Nadia")
    ReportingLine.objects.create(
        employee=child,
        supervisor=people["employee"],
        unit=unit,
        start_date=timezone.localdate(),
        is_primary=True,
    )
    period = reporting_period(today=timezone.localdate())
    tree = team_tree(people["manager"], period)
    assert tree[0].summary.employee == people["employee"]
    assert tree[0].children[0].summary.employee == child


@pytest.mark.django_db
def test_assignment_create_generates_action_code(
    people: dict[str, User], action: InstitutionalAction
) -> None:
    calendar = WorkCalendar.objects.get(is_default=True)
    start = week_start_for(timezone.localdate())
    assignment = create_assignment_for_user(
        manager=people["manager"],
        employee=people["employee"],
        title="Verifier la caisse",
        description="Controler les pieces.",
        action=action,
        start_date=start,
        due_date=calendar.due_date_for(start, Decimal("2.0")),
        estimated_work_days=Decimal("2.0"),
        calendar=calendar,
    )
    assert assignment.task.code == f"{action.code}-{start.year}-0001"

    unclassified = create_assignment_for_user(
        manager=people["manager"],
        employee=people["employee"],
        title="Organiser une activite ponctuelle",
        description="Aucune classification institutionnelle requise.",
        action=None,
        start_date=start,
        due_date=calendar.due_date_for(start, Decimal("1.5")),
        estimated_work_days=Decimal("1.5"),
        calendar=calendar,
    )
    assert unclassified.task.action is None
    assert unclassified.task.code == f"TACHE-{start.year}-0001"


def test_month_period_uses_french_month_name() -> None:
    period = reporting_period(month="2026-07", today=timezone.localdate())
    assert period.label == "juillet 2026"
