from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from accounts.models import User
from accounts.services import user_management_state_token
from work.models import (
    OrganizationMembership,
    OrganizationUnit,
    ReportingLine,
    TaskAssignment,
    TaskProposal,
)
from work.progress_cache import cached_daily_progress_rows
from work.services import (
    ReportingPeriod,
    activity_feed,
    adjacent_period,
    assignment_snapshot,
    can_comment_assignment,
    can_manage_assignment,
    current_progress,
    effective_assignment_status,
    is_self_managed_assignment,
    workload_breakdown,
    assignment_status_label,
    collaborator_state_token,
    eligible_primary_collaborator_ids,
    eligible_primary_supervisor_ids,
)


def decimal_text(value: Decimal) -> str:
    """Render workload precision without trailing zeroes."""
    return format(value.quantize(Decimal("0.0001")).normalize(), "f")


def person_payload(user: User) -> dict[str, object]:
    return {
        "id": user.pk,
        "name": str(user),
        "position": user.position,
        "login_alias": user.login_alias,
        "avatar": user.avatar,
    }


def user_profile_payload(user: User) -> dict[str, object]:
    return {
        **person_payload(user),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "avatar": user.avatar,
        "phone": user.phone,
        "terms_of_reference": user.terms_of_reference,
    }


def organization_unit_payload(unit: OrganizationUnit) -> dict[str, object]:
    """Return the stable labels used in organization selectors."""
    return {
        "id": unit.pk,
        "code": unit.code,
        "short_name": unit.short_name,
        "long_name": unit.long_name,
        "label": str(unit),
    }


def user_management_summary_payload(user: User, viewer: User) -> dict[str, object]:
    """Return one compact user row for routine IT administration."""
    prefetched = getattr(user, "current_organization_memberships", None)
    if prefetched is None:
        prefetched = list(
            OrganizationMembership.objects.filter(user=user, end_date__isnull=True)
            .select_related("unit")
            .order_by("-is_primary", "pk")
        )
    membership = next((item for item in prefetched if item.is_primary), None)
    protected = user.is_superuser and not viewer.is_superuser
    return {
        **person_payload(user),
        "email": user.email,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "password_change_required": user.password_change_required,
        "has_usable_password": user.has_usable_password(),
        "primary_unit": (
            organization_unit_payload(membership.unit) if membership else None
        ),
        "state_token": user_management_state_token(user),
        "batch_capabilities": {
            "deactivate": user.is_active and user.pk != viewer.pk and not protected,
            "delete": (
                not user.is_active
                and user.pk != viewer.pk
                and not protected
                and not user.is_staff
                and not user.is_it_admin
                and not user.is_superuser
            ),
        },
    }


def user_management_detail_payload(user: User, viewer: User) -> dict[str, object]:
    """Return identity and calculated current organization fields."""
    prefetched = getattr(user, "current_organization_memberships", None)
    memberships = (
        list(prefetched)
        if prefetched is not None
        else list(
            OrganizationMembership.objects.filter(user=user, end_date__isnull=True)
            .select_related("unit")
            .order_by("-is_primary", "unit__display_order", "unit__long_name")
        )
    )
    primary_line = (
        ReportingLine.objects.filter(
            employee=user, is_primary=True, end_date__isnull=True
        )
        .select_related("supervisor")
        .first()
    )
    protected = user.is_superuser and not viewer.is_superuser
    return {
        **user_management_summary_payload(user, viewer),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "agenda_direction": user.agenda_direction,
        "include_in_direction_agendas": user.include_in_direction_agendas,
        "unit_ids": [membership.unit_id for membership in memberships],
        "primary_unit_id": next(
            (membership.unit_id for membership in memberships if membership.is_primary),
            None,
        ),
        "primary_supervisor": (
            person_payload(primary_line.supervisor) if primary_line else None
        ),
        "state_token": user_management_state_token(user),
        "capabilities": {
            "deactivate": user.is_active and user.pk != viewer.pk and not protected,
            "reactivate": not user.is_active and not protected,
            "reset_password": (user.is_active and user.pk != viewer.pk and not protected),
            "send_activation": (
                user.is_active and not user.has_usable_password() and not protected
            ),
            "edit": not protected,
        },
    }


def collaborator_management_payload(supervisor: User) -> dict[str, object]:
    """Return direct collaborators, candidates and safe replacement choices."""
    current_users = list(
        User.objects.filter(
            reporting_lines__supervisor=supervisor,
            reporting_lines__is_primary=True,
            reporting_lines__end_date__isnull=True,
            is_active=True,
        )
        .distinct()
        .order_by("last_name", "first_name", "email")
    )
    eligible_ids = eligible_primary_collaborator_ids(supervisor)
    available_users = list(
        User.objects.filter(pk__in=eligible_ids, is_active=True)
        .exclude(pk__in={user.pk for user in current_users})
        .order_by("last_name", "first_name", "email")
    )
    replacement_options: dict[str, list[dict[str, object]]] = {}
    for employee in current_users:
        replacements = User.objects.filter(
            pk__in=eligible_primary_supervisor_ids(employee), is_active=True
        ).order_by("last_name", "first_name", "email")
        replacement_options[str(employee.pk)] = [
            person_payload(candidate) for candidate in replacements
        ]
    return {
        "supervisor": person_payload(supervisor),
        "state_token": collaborator_state_token(supervisor),
        "current": [person_payload(user) for user in current_users],
        "available": [person_payload(user) for user in available_users],
        "replacement_options": replacement_options,
    }


def period_payload(period: ReportingPeriod) -> dict[str, object]:
    previous = adjacent_period(period, -1)
    following = adjacent_period(period, 1)
    return {
        "kind": period.kind,
        "label": period.label,
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "query": period.query,
        "previous_query": previous.query,
        "next_query": following.query,
    }


def recurrence_payload(
    assignment: TaskAssignment, viewer: User | None = None
) -> dict[str, object] | None:
    series = assignment.recurrence
    if series is None:
        return None
    can_cancel = False
    if viewer is not None and series.status == "active":
        from work.services import can_manage_assignment

        can_cancel = (
            series.created_by_id == viewer.pk and series.employee_id == viewer.pk
        ) or can_manage_assignment(viewer, assignment)
    return {
        "id": series.pk,
        "frequency": series.frequency,
        "frequency_label": series.get_frequency_display(),
        "status": series.status,
        "end_date": series.end_date.isoformat(),
        "occurrence_number": assignment.recurrence_occurrence,
        "planned_start_date": (
            assignment.recurrence_anchor_date or assignment.start_date
        ).isoformat(),
        "revision": series.revision,
        "can_cancel": can_cancel,
    }


def assignment_summary_payload(
    assignment: TaskAssignment, period: ReportingPeriod
) -> dict[str, object]:
    snapshot = assignment_snapshot(assignment, period)
    latest = snapshot.latest
    return {
        "id": assignment.pk,
        "revision": assignment.revision,
        "code": assignment.task.code,
        "title": assignment.task.title,
        "status": snapshot.status,
        "status_label": snapshot.status_label,
        "percentage": snapshot.percentage,
        "progress_delta": snapshot.progress_delta,
        "start_date": assignment.start_date.isoformat(),
        "today": timezone.localdate().isoformat(),
        "due_date": assignment.due_date.isoformat(),
        "workload": {
            "total": decimal_text(snapshot.workload.total_days),
            "completed": decimal_text(snapshot.workload.completed_days),
            "remaining": decimal_text(snapshot.workload.remaining_days),
        },
        "deadline_level": snapshot.deadline_level.value,
        "blocked": bool(latest and latest.blocked),
        "latest_note": latest.note if latest else "",
        "employee": person_payload(assignment.employee),
        "manager": person_payload(assignment.manager),
        "action": (
            {"id": assignment.task.action_id, "label": str(assignment.task.action)}
            if assignment.task.action_id
            else None
        ),
        "recurrence": recurrence_payload(assignment),
    }


def task_management_payload(assignment: TaskAssignment) -> dict[str, object]:
    """Return the compact, revision-aware row used by IT task management."""
    progress = current_progress(assignment)
    status = effective_assignment_status(assignment.status, progress)
    return {
        "id": assignment.pk,
        "revision": assignment.revision,
        "task_id": assignment.task_id,
        "code": assignment.task.code,
        "title": assignment.task.title,
        "status": status,
        "status_label": assignment_status_label(status),
        "percentage": progress,
        "start_date": assignment.start_date.isoformat(),
        "due_date": assignment.due_date.isoformat(),
        "employee": person_payload(assignment.employee),
        "manager": person_payload(assignment.manager),
    }


def assignment_detail_payload(
    assignment: TaskAssignment, viewer: User
) -> dict[str, object]:
    today = timezone.localdate()
    progress = current_progress(assignment)
    status = effective_assignment_status(assignment.status, progress)
    workload = workload_breakdown(assignment.estimated_work_days, progress)
    can_manage = can_manage_assignment(viewer, assignment)
    can_comment = can_comment_assignment(viewer, assignment)
    return {
        "id": assignment.pk,
        "revision": assignment.revision,
        "code": assignment.task.code,
        "title": assignment.task.title,
        "description": assignment.task.description,
        "status": status,
        "status_label": assignment_status_label(status),
        "percentage": progress,
        "start_date": assignment.start_date.isoformat(),
        "today": today.isoformat(),
        "due_date": assignment.due_date.isoformat(),
        "estimated_work_days": decimal_text(assignment.estimated_work_days),
        "calendar": {"id": assignment.calendar_id, "label": str(assignment.calendar)},
        "workload": {
            "total": decimal_text(workload.total_days),
            "completed": decimal_text(workload.completed_days),
            "remaining": decimal_text(workload.remaining_days),
        },
        "employee": person_payload(assignment.employee),
        "manager": person_payload(assignment.manager),
        "action": (
            {"id": assignment.task.action_id, "label": str(assignment.task.action)}
            if assignment.task.action_id
            else None
        ),
        "recurrence": recurrence_payload(assignment, viewer),
        "chart": [row.as_json() for row in cached_daily_progress_rows(assignment)],
        "activities": [
            {
                "id": item.activity.pk,
                "kind": item.activity.kind,
                "message": item.activity.message,
                "occurred_at": item.activity.occurred_at.isoformat(),
                "actor": person_payload(item.activity.actor),
                "actor_short_name": item.actor_short_name,
                "percentage_before": item.activity.percentage_before,
                "percentage_after": item.activity.percentage_after,
            }
            for item in activity_feed(assignment)
        ],
        "capabilities": {
            "manage": can_manage,
            "comment": can_comment,
            "update_progress": status != "closed_early"
            and (viewer == assignment.employee or can_manage),
            "self_managed": is_self_managed_assignment(viewer, assignment),
        },
    }


def proposal_payload(proposal: TaskProposal, viewer: User) -> dict[str, object]:
    from work.services import can_review_proposal

    can_review = proposal.status == "submitted" and can_review_proposal(viewer, proposal)
    can_edit = (
        proposal.employee_id == viewer.pk
        and proposal.status in {"submitted", "rejected"}
    ) or can_review
    status_label = {
        "submitted": "Soumise",
        "accepted": "Validée",
        "rejected": "Rejetée",
    }.get(proposal.status, proposal.get_status_display())
    return {
        "id": proposal.pk,
        "revision": proposal.revision,
        "title": proposal.title,
        "description": proposal.description,
        "status": proposal.status,
        "status_label": status_label,
        "start_date": proposal.start_date.isoformat(),
        "due_date": proposal.due_date.isoformat(),
        "estimated_work_days": decimal_text(proposal.estimated_work_days),
        "action": (
            {"id": proposal.action.pk, "label": str(proposal.action)}
            if proposal.action
            else None
        ),
        "calendar": {"id": proposal.calendar.pk, "label": str(proposal.calendar)},
        "employee": person_payload(proposal.employee),
        "accepted_assignment_id": proposal.accepted_assignment_id,
        "decision_note": proposal.decision_note,
        "created_at": proposal.created_at.isoformat(),
        "recurrence": (
            {
                "frequency": proposal.recurrence_frequency,
                "frequency_label": proposal.get_recurrence_frequency_display(),
                "end_date": proposal.recurrence_end_date.isoformat(),
                "accepted_recurrence_id": proposal.accepted_recurrence_id,
            }
            if proposal.recurrence_frequency and proposal.recurrence_end_date
            else None
        ),
        "can_review": can_review,
        "capabilities": {
            "edit": can_edit,
            "resubmit": proposal.employee_id == viewer.pk
            and proposal.status == "rejected",
            "review": can_review,
        },
    }
