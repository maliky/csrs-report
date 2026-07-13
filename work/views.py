"""Server-rendered, permission-scoped CSRS views."""

from __future__ import annotations

import json
from math import ceil
from typing import TypeVar

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import User
from work.forms import (
    AssignmentCreateForm,
    AssignmentEditForm,
    CommentForm,
    ProgressForm,
    ProposalForm,
    ReasonForm,
)
from work.models import (
    ProposalStatus,
    TaskAssignment,
    TaskProposal,
)
from work.notifications import queue_assignment_notification
from work.observable import (
    create_export_token,
    export_token_user_id,
    observable_dataset,
)
from work.services import (
    add_observation,
    accept_proposal,
    can_comment_assignment,
    can_manage_assignment,
    can_view_assignment,
    can_view_employee,
    close_early,
    create_assignment_for_user,
    daily_progress_rows,
    adjacent_period,
    assignment_snapshot,
    can_self_assign,
    current_progress,
    is_self_managed_assignment,
    period_assignments,
    primary_manager,
    record_progress,
    ReportingPeriod,
    reporting_period,
    reject_completion,
    reject_proposal,
    remaining_projection,
    team_tree,
    update_assignment_schedule,
    visible_activities,
    workload_breakdown,
    validate_completion,
    week_start_for,
)

ResponseT = TypeVar("ResponseT", bound=HttpResponse)


def request_user(request: HttpRequest) -> User:
    """Return the authenticated custom user."""
    if not isinstance(request.user, User):
        raise PermissionDenied
    return request.user


def selected_period(request: HttpRequest) -> ReportingPeriod:
    """Return the normalized week or month selected by the request."""
    return reporting_period(
        week=request.GET.get("week", ""),
        month=request.GET.get("month", ""),
        today=timezone.localdate(),
    )


def period_context(request: HttpRequest) -> dict[str, ReportingPeriod]:
    """Build shared navigation context for period-aware pages."""
    period = selected_period(request)
    return {
        "period": period,
        "previous_period": adjacent_period(period, -1),
        "next_period": adjacent_period(period, 1),
    }


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    user = request_user(request)
    navigation = period_context(request)
    period = navigation["period"]
    assignments = list(period_assignments(user, period))
    cards = [assignment_snapshot(assignment, period) for assignment in assignments]
    has_team = user.supervised_lines.filter(end_date__isnull=True).exists()
    return render(
        request,
        "work/dashboard.html",
        {
            "cards": cards,
            "has_team": has_team,
            "can_self_assign": can_self_assign(user),
            **navigation,
        },
    )


@login_required
def assignment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    assignment = get_object_or_404(
        TaskAssignment.objects.select_related(
            "task", "employee", "manager", "task__action", "calendar"
        ).prefetch_related("calendar__days"),
        pk=pk,
    )
    user = request_user(request)
    if not can_view_assignment(user, assignment):
        raise Http404
    latest = assignment.progress_entries.order_by("-entry_date").first()
    initial_progress = latest.percentage if latest else 0
    progress_rows = daily_progress_rows(assignment)
    self_managed = is_self_managed_assignment(user, assignment)
    can_manage = can_manage_assignment(user, assignment)
    progress_form = ProgressForm(
        initial={"percentage": initial_progress}, self_managed=self_managed
    )
    return render(
        request,
        "work/assignment_detail.html",
        {
            "assignment": assignment,
            "projection": remaining_projection(assignment),
            "workload": workload_breakdown(
                assignment.estimated_work_days, initial_progress
            ),
            "progress_form": progress_form,
            "comment_form": CommentForm(),
            "reason_form": ReasonForm(),
            "can_comment": can_comment_assignment(user, assignment),
            "can_manage": can_manage,
            "can_update_progress": assignment.status != "closed_early"
            and (user == assignment.employee or can_manage),
            "initial_progress": initial_progress,
            "self_managed": self_managed,
            "activities": visible_activities(assignment).order_by("-occurred_at", "-pk"),
            "progress_rows": progress_rows,
            "progress_observation_count": sum(row.observed for row in progress_rows),
            "today": timezone.localdate(),
        },
    )


@login_required
def assignment_progress_json(request: HttpRequest, pk: int) -> JsonResponse:
    """Expose chart-only daily history under the task detail permission."""
    assignment = get_object_or_404(
        TaskAssignment.objects.select_related(
            "calendar", "employee", "manager"
        ).prefetch_related("calendar__days"),
        pk=pk,
    )
    if not can_view_assignment(request_user(request), assignment):
        raise Http404
    return JsonResponse(
        [row.as_json() for row in daily_progress_rows(assignment)], safe=False
    )


def _with_observable_headers(response: ResponseT) -> ResponseT:
    """Apply non-credentialed CORS and prevent bearer responses from caching."""
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Authorization, Accept"
    response["Access-Control-Max-Age"] = "600"
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    response["Cross-Origin-Resource-Policy"] = "cross-origin"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _observable_auth_error() -> JsonResponse:
    """Return one indistinguishable error for absent, expired, or invalid tokens."""
    response = JsonResponse(
        {"detail": "Jeton Observable absent, invalide ou expire."}, status=401
    )
    response["WWW-Authenticate"] = 'Bearer realm="CSRS Observable"'
    return _with_observable_headers(response)


@login_required
def observable_export_page(request: HttpRequest) -> HttpResponse:
    """Issue a temporary token and show copy-ready Observable instructions."""
    user = request_user(request)
    token = create_export_token(user)
    endpoint = request.build_absolute_uri(reverse("observable-progress-export"))
    snippet = "\n".join(
        (
            "csrs = {",
            f"  const response = await fetch({json.dumps(endpoint)}, {{",
            "    headers: {",
            '      Accept: "application/json",',
            f'      Authorization: "Bearer {token}"',
            "    }",
            "  });",
            "  if (!response.ok) throw new Error(`CSRS ${response.status}`);",
            "  return response.json();",
            "}",
        )
    )
    ttl_seconds = settings.OBSERVABLE_EXPORT_TOKEN_MAX_AGE_SECONDS
    response = render(
        request,
        "work/observable_export.html",
        {
            "endpoint": endpoint,
            "token": token,
            "snippet": snippet,
            "ttl_minutes": max(1, ceil(ttl_seconds / 60)),
        },
    )
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


@require_http_methods(["GET", "OPTIONS"])
def observable_progress_export(request: HttpRequest) -> HttpResponse:
    """Expose every currently visible task through a temporary bearer token."""
    if request.method == "OPTIONS":
        return _with_observable_headers(HttpResponse(status=204))
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        return _observable_auth_error()
    try:
        user_id = export_token_user_id(token.strip())
    except signing.BadSignature:
        return _observable_auth_error()
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return _observable_auth_error()
    response = JsonResponse(observable_dataset(user).as_json())
    return _with_observable_headers(response)


@login_required
@require_POST
def update_progress(request: HttpRequest, pk: int) -> HttpResponse:
    assignment = get_object_or_404(TaskAssignment, pk=pk)
    user = request_user(request)
    form = ProgressForm(
        request.POST, self_managed=is_self_managed_assignment(user, assignment)
    )
    if form.is_valid():
        previous = current_progress(assignment)
        percentage = int(form.cleaned_data["percentage"])
        try:
            record_progress(
                user=user,
                assignment=assignment,
                entry_date=timezone.localdate(),
                percentage=percentage,
                note=str(form.cleaned_data["note"]),
                blocked=bool(form.cleaned_data["blocked"]),
            )
        except ValidationError as error:
            messages.error(request, str(error))
            return redirect("assignment-detail", pk=pk)
        if percentage < previous:
            messages.warning(
                request,
                f"Progression enregistree : diminution de {previous - percentage} points.",
            )
        else:
            messages.success(request, "Progression enregistree.")
    else:
        messages.error(request, "La progression n'a pas pu etre enregistree.")
    return redirect("assignment-detail", pk=pk)


@login_required
@require_POST
def add_comment(request: HttpRequest, pk: int) -> HttpResponse:
    assignment = get_object_or_404(TaskAssignment, pk=pk)
    user = request_user(request)
    if not can_comment_assignment(user, assignment):
        raise PermissionDenied
    form = CommentForm(request.POST)
    if form.is_valid():
        add_observation(
            user=user, assignment=assignment, message=str(form.cleaned_data["body"])
        )
        messages.success(request, "Commentaire ajoute.")
    return redirect("assignment-detail", pk=pk)


@login_required
def create_proposal(request: HttpRequest) -> HttpResponse:
    user = request_user(request)
    if primary_manager(user) is None:
        messages.info(
            request,
            "Vous pouvez creer directement une tache personnelle.",
        )
        return redirect("assignment-create")
    monday = week_start_for(timezone.localdate())
    form = ProposalForm(request.POST or None, initial={"start_date": monday})
    if request.method == "POST" and form.is_valid():
        proposal = form.save(commit=False)
        proposal.employee = user
        proposal.save()
        messages.success(request, "Proposition envoyee au responsable principal.")
        return redirect("proposal-list")
    return render(
        request, "work/form_page.html", {"form": form, "title": "Proposer une tache"}
    )


@login_required
def create_assignment(request: HttpRequest) -> HttpResponse:
    manager = request_user(request)
    form = AssignmentCreateForm(request.POST or None, manager=manager)
    if request.method == "POST" and form.is_valid():
        employee = form.cleaned_data["employee"]
        if not isinstance(employee, User):
            raise PermissionDenied
        action = form.cleaned_data["action"]
        if action is None:
            raise PermissionDenied
        assignment = create_assignment_for_user(
            manager=manager,
            employee=employee,
            title=str(form.cleaned_data["title"]),
            description=str(form.cleaned_data["description"]),
            action=action,
            start_date=form.cleaned_data["start_date"],
            due_date=form.cleaned_data["due_date"],
            estimated_work_days=form.cleaned_data["estimated_work_days"],
            calendar=form.calendar,
        )
        queue_assignment_notification(assignment)
        messages.success(request, "Tache affectee.")
        return redirect("assignment-detail", pk=assignment.pk)
    return render(
        request, "work/form_page.html", {"form": form, "title": "Affecter une tache"}
    )


@login_required
def edit_assignment(request: HttpRequest, pk: int) -> HttpResponse:
    assignment = get_object_or_404(
        TaskAssignment.objects.select_related("task", "employee", "manager"), pk=pk
    )
    user = request_user(request)
    if not can_manage_assignment(user, assignment):
        raise PermissionDenied
    initial = {
        "title": assignment.task.title,
        "description": assignment.task.description,
        "action": assignment.task.action,
        "start_date": assignment.start_date,
        "due_date": assignment.due_date,
        "estimated_work_days": assignment.estimated_work_days,
    }
    form = AssignmentEditForm(
        request.POST or None, initial=initial, calendar=assignment.calendar
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            assignment.task.title = form.cleaned_data["title"]
            assignment.task.description = form.cleaned_data["description"]
            assignment.task.action = form.cleaned_data["action"]
            assignment.task.save(
                update_fields=["title", "description", "action", "updated_at"]
            )
            update_assignment_schedule(
                user=user,
                assignment=assignment,
                start_date=form.cleaned_data["start_date"],
                due_date=form.cleaned_data["due_date"],
                estimated_work_days=form.cleaned_data["estimated_work_days"],
            )
        messages.success(request, "Tache modifiee et changement audite.")
        return redirect("assignment-detail", pk=assignment.pk)
    return render(
        request, "work/form_page.html", {"form": form, "title": "Modifier la tache"}
    )


@login_required
def team_summary(request: HttpRequest) -> HttpResponse:
    manager = request_user(request)
    navigation = period_context(request)
    period = navigation["period"]
    nodes = team_tree(manager, period)
    return render(
        request,
        "work/team_summary.html",
        {
            "nodes": nodes,
            **navigation,
        },
    )


@login_required
def employee_detail(request: HttpRequest, employee_id: int) -> HttpResponse:
    user = request_user(request)
    employee = get_object_or_404(User, pk=employee_id)
    navigation = period_context(request)
    period = navigation["period"]
    if not can_view_employee(user, employee):
        raise Http404
    assignments = list(period_assignments(employee, period))
    cards = [assignment_snapshot(item, period) for item in assignments]
    return render(
        request,
        "work/employee_detail.html",
        {"employee": employee, "cards": cards, **navigation},
    )


@login_required
def proposal_list(request: HttpRequest) -> HttpResponse:
    """Show proposal history to its author and direct primary manager."""
    user = request_user(request)
    status = request.GET.get("status", "all")
    valid_statuses = {choice for choice, _label in ProposalStatus.choices}
    own = TaskProposal.objects.filter(employee=user)
    employee_ids = user.supervised_lines.filter(
        is_primary=True, end_date__isnull=True
    ).values_list("employee_id", flat=True)
    team = TaskProposal.objects.filter(employee_id__in=employee_ids)
    if status in valid_statuses:
        own = own.filter(status=status)
        team = team.filter(status=status)
    common = ("employee", "action", "reviewed_by", "accepted_assignment")
    return render(
        request,
        "work/proposal_list.html",
        {
            "own_proposals": own.select_related(*common),
            "team_proposals": team.select_related(*common),
            "selected_status": status,
            "has_team": employee_ids.exists(),
        },
    )


@login_required
def proposal_queue(request: HttpRequest) -> HttpResponse:
    """Preserve the former pending-queue URL."""
    return redirect("/propositions/?status=submitted")


@login_required
@require_POST
def decide_proposal(request: HttpRequest, pk: int) -> HttpResponse:
    proposal = get_object_or_404(TaskProposal, pk=pk, status=ProposalStatus.SUBMITTED)
    user = request_user(request)
    action = request.POST.get("action")
    if action == "accept":
        accept_proposal(user, proposal)
        messages.success(request, "Proposition acceptee et planifiee.")
    elif action == "reject":
        try:
            reject_proposal(user, proposal, request.POST.get("reason", ""))
        except ValidationError as error:
            messages.error(request, str(error))
            return redirect("proposal-list")
        messages.success(request, "Proposition rejetee.")
    else:
        raise ValidationError("Decision inconnue.")
    return redirect("proposal-list")


@login_required
@require_POST
def assignment_action(request: HttpRequest, pk: int) -> HttpResponse:
    assignment = get_object_or_404(TaskAssignment, pk=pk)
    user = request_user(request)
    action = request.POST.get("action")
    reason = request.POST.get("reason", "")
    if action == "validate":
        validate_completion(user, assignment)
        messages.success(request, "Achevement valide.")
    elif action == "reject":
        reject_completion(user, assignment, reason)
        messages.success(request, "La tache est remise en cours.")
    elif action == "close":
        close_early(user, assignment, reason)
        messages.success(request, "Tache cloturee avant achevement.")
    else:
        raise ValidationError("Action inconnue.")
    return redirect("assignment-detail", pk=pk)
