from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from accounts.models import User
from work.models import TaskAssignment, TaskProposal
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
)


def decimal_text(value: Decimal) -> str:
    """Render the app-wide tenth-of-a-day precision without trailing zeroes."""
    return format(value.quantize(Decimal("0.1")).normalize(), "f")


def person_payload(user: User) -> dict[str, object]:
    return {
        "id": user.pk,
        "name": str(user),
        "position": user.position,
        "login_alias": user.login_alias,
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

    can_edit = proposal.employee_id == viewer.pk and proposal.status in {
        "submitted",
        "rejected",
    }
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
        "can_review": proposal.status == "submitted"
        and can_review_proposal(viewer, proposal),
        "capabilities": {
            "edit": can_edit,
            "resubmit": proposal.employee_id == viewer.pk
            and proposal.status == "rejected",
            "review": proposal.status == "submitted"
            and can_review_proposal(viewer, proposal),
        },
    }
