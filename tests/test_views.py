from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from work.models import (
    ActivityKind,
    InstitutionalAction,
    ProposalStatus,
    TaskActivity,
    TaskAssignment,
    TaskProposal,
    WorkCalendar,
    default_work_calendar_id,
)
from work.services import week_start_for


@pytest.mark.django_db
def test_dashboard_requires_login(client) -> None:
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_outsider_cannot_discover_assignment(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    client.force_login(people["outsider"])
    response = client.get(reverse("assignment-detail", args=[assignment.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_secondary_supervisor_sees_comment_but_no_manager_action(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    client.force_login(people["observer"])
    response = client.get(reverse("assignment-detail", args=[assignment.pk]))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Ajouter l’observation" in content
    assert "Décision du responsable" not in content


@pytest.mark.django_db
def test_employee_progress_post_sets_awaiting_validation(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    client.force_login(people["employee"])
    response = client.post(
        reverse("progress-update", args=[assignment.pk]),
        {"percentage": 100, "note": "Fini", "blocked": ""},
    )
    assert response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.status == "awaiting_validation"


@pytest.mark.django_db
def test_only_primary_manager_can_edit_assignment(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    url = reverse("assignment-edit", args=[assignment.pk])
    client.force_login(people["observer"])
    assert client.get(url).status_code == 403
    client.force_login(people["manager"])
    response = client.post(
        url,
        {
            "title": "Titre corrige",
            "description": "Description corrigee",
            "action": assignment.task.action_id,
            "start_date": assignment.start_date.isoformat(),
            "due_date": assignment.due_date.isoformat(),
            "estimated_work_days": "4.00",
        },
    )
    assert response.status_code == 302
    assignment.task.refresh_from_db()
    assert assignment.task.title == "Titre corrige"
    assert assignment.task.history.count() >= 2


@pytest.mark.django_db
def test_team_summary_is_one_table_with_required_metrics(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    client.force_login(people["manager"])
    response = client.get(reverse("team-summary"))
    content = response.content.decode()
    assert response.status_code == 200
    assert 'class="team-tree"' in content
    for label in ("Moyenne", "Médiane", "Reste cumulé", "Reste moyen"):
        assert label in content
    assert str(people["employee"]) in content


@pytest.mark.django_db
def test_rejected_proposal_is_visible_to_author_and_manager_but_audited(
    client, people: dict[str, User], action: InstitutionalAction
) -> None:
    monday = week_start_for(timezone.localdate())
    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    proposal = TaskProposal.objects.create(
        employee=people["employee"],
        title="Proposition rejetee",
        description="Amelioration proposee",
        action=action,
        start_date=monday,
        due_date=calendar.due_date_for(monday, Decimal("2.00")),
        estimated_work_days=Decimal("2.00"),
        calendar=calendar,
    )
    client.force_login(people["manager"])
    response = client.post(
        reverse("proposal-decide", args=[proposal.pk]),
        {"action": "reject", "reason": "Hors priorite"},
    )
    assert response.status_code == 302
    proposal.refresh_from_db()
    assert proposal.status == ProposalStatus.REJECTED
    listing = client.get(reverse("proposal-list")).content.decode()
    assert "Proposition rejetee" in listing
    client.force_login(people["employee"])
    own_listing = client.get(reverse("proposal-list")).content.decode()
    assert "Proposition rejetee" in own_listing
    assert proposal.history.count() >= 2


@pytest.mark.django_db
def test_forms_have_mobile_viewport_and_french_labels(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    client.force_login(people["employee"])
    content = client.get(
        reverse("assignment-detail", args=[assignment.pk])
    ).content.decode()
    assert 'name="viewport"' in content
    assert "Avancement" in content
    assert "Observation" in content


@pytest.mark.django_db
def test_assignment_detail_shows_start_today_and_due_in_chart_and_facts(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    assignment.progress_entries.create(
        entry_date=timezone.localdate(),
        percentage=15,
        author=people["employee"],
    )
    client.force_login(people["employee"])
    content = client.get(
        reverse("assignment-detail", args=[assignment.pk])
    ).content.decode()

    assert "Date de début" in content
    assert "Date du jour" in content
    assert "Fin prévue" in content
    assert f'data-start="{assignment.start_date:%Y-%m-%d}"' in content
    assert f'data-today="{timezone.localdate():%Y-%m-%d}"' in content
    assert f'data-due="{assignment.due_date:%Y-%m-%d}"' in content
    assert "saisie historique" in content


@pytest.mark.django_db
def test_outsider_cannot_open_empty_employee_detail(
    client, people: dict[str, User]
) -> None:
    empty_employee = User.objects.create_user("empty@example.test")
    client.force_login(people["outsider"])
    response = client.get(reverse("employee-detail", args=[empty_employee.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_employee_detail_shows_progress_and_workload(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    monday = week_start_for(timezone.localdate())
    assignment.progress_entries.create(
        entry_date=monday,
        percentage=40,
        author=people["employee"],
    )
    client.force_login(people["manager"])
    content = client.get(
        reverse("employee-detail", args=[people["employee"].pk]),
        {"week": monday.isoformat()},
    ).content.decode()
    assert "40 %" in content
    assert "5,00 j" in content
    assert "restants" in content


@pytest.mark.django_db
def test_month_view_and_proposal_visibility_are_scoped(
    client, people: dict[str, User], action: InstitutionalAction
) -> None:
    monday = week_start_for(timezone.localdate())
    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    proposal = TaskProposal.objects.create(
        employee=people["employee"],
        title="Ameliorer le classement",
        description="Regrouper les dossiers",
        action=action,
        start_date=monday,
        due_date=calendar.due_date_for(monday, Decimal("2.00")),
        estimated_work_days=Decimal("2.00"),
        calendar=calendar,
    )
    client.force_login(people["manager"])
    assert proposal.title in client.get(reverse("proposal-list")).content.decode()
    month = client.get(reverse("team-summary"), {"month": f"{monday:%Y-%m}"})
    assert month.status_code == 200
    assert "Mois" in month.content.decode()
    client.force_login(people["outsider"])
    assert proposal.title not in client.get(reverse("proposal-list")).content.decode()


@pytest.mark.django_db
def test_old_proposal_queue_redirects_to_pending_filter(client, people) -> None:
    client.force_login(people["manager"])
    response = client.get(reverse("proposal-queue"))
    assert response.status_code == 302
    assert response.url == "/propositions/?status=submitted"


@pytest.mark.django_db
def test_dashboard_has_compact_workload_and_all_period_observations(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    for index in range(3):
        TaskActivity.objects.create(
            assignment=assignment,
            actor=people["employee"],
            kind=ActivityKind.COMMENT,
            message=f"Observation generale {index}",
        )
    client.force_login(people["employee"])
    content = client.get(reverse("dashboard")).content.decode()
    assert 'class="workload-chart"' in content
    assert "j réalisés" in content
    assert "Observations (3)" in content
    for index in range(3):
        assert f"Observation generale {index}" in content
    assert " points)" not in content


@pytest.mark.django_db
def test_team_summary_uses_task_profiles_without_exception_columns(
    client, assignment: TaskAssignment, people: dict[str, User]
) -> None:
    client.force_login(people["manager"])
    content = client.get(reverse("team-summary")).content.decode()
    assert "Profil des tâches" in content
    assert 'class="task-profile-chart"' in content
    assert "Exceptions</th>" not in content
    assert "Évolution</th>" not in content


@pytest.mark.django_db
def test_self_managed_task_uses_first_person_labels_and_five_percent_step(
    client, action: InstitutionalAction
) -> None:
    root = User.objects.create_user("dg-ui@example.test")
    calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
    task = root.created_tasks.create(
        code="DG-UI",
        title="Arbitrer les priorites",
        description="Suivi",
        action=action,
    )
    assignment = TaskAssignment.objects.create(
        task=task,
        employee=root,
        manager=root,
        start_date=timezone.localdate(),
        due_date=calendar.due_date_for(timezone.localdate(), Decimal("3.00")),
        estimated_work_days=Decimal("3.00"),
        calendar=calendar,
        status="awaiting_validation",
    )
    client.force_login(root)
    content = client.get(
        reverse("assignment-detail", args=[assignment.pk])
    ).content.decode()
    assert "Signaler un point d&#x27;attention" in content
    assert "Clôture de ma tâche" in content
    assert "Confirmer mon achèvement" in content
    assert 'step="5"' in content


@pytest.mark.django_db
def test_root_assignment_form_includes_self(client) -> None:
    root = User.objects.create_user("direction@example.test")
    client.force_login(root)
    content = client.get(reverse("assignment-create")).content.decode()
    assert str(root) in content
