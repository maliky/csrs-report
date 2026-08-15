from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast

from django.contrib.auth import logout
from django.http import Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from agenda.services import (
    can_manage_availability,
    can_manage_visits,
    can_prepare_agenda,
    can_view_agenda,
)
from api.presenters import (
    assignment_detail_payload,
    assignment_summary_payload,
    decimal_text,
    period_payload,
    person_payload,
    proposal_payload,
)
from api.serializers import (
    ObservationSerializer,
    PlanningPreviewSerializer,
    ProgressSerializer,
    ProposalCreateSerializer,
    ProposalDecisionSerializer,
    ProposalResubmitSerializer,
    ProposalUpdateSerializer,
    TaskCreateSerializer,
    TaskUpdateSerializer,
    TransitionSerializer,
)
from work.models import (
    InstitutionalAction,
    TaskAssignment,
    TaskProposal,
    WorkCalendar,
    default_work_calendar_id,
)
from work.services import (
    ReportingPeriod,
    accept_proposal,
    add_observation,
    assignable_employee_ids,
    can_self_assign,
    can_review_proposal,
    can_view_assignment,
    can_view_employee,
    close_early,
    create_assignment_for_user,
    due_date_for,
    period_assignments,
    record_progress,
    reject_completion,
    reject_proposal,
    resubmit_proposal,
    reporting_period,
    reviewable_proposals,
    team_tree_overview,
    update_assignment_details,
    update_proposal,
    validate_completion,
    visible_team_proposals,
    visible_employee_ids,
    workload_for,
)

PERIOD_PARAMETERS = [
    OpenApiParameter("week", OpenApiTypes.DATE, required=False),
    OpenApiParameter("month", OpenApiTypes.STR, required=False),
]


def request_user(request: Request) -> User:
    """Return the authenticated custom user after DRF permission checks."""
    return cast(User, request.user)


def selected_period(request: Request) -> ReportingPeriod:
    """Parse the shared week/month query contract."""
    return reporting_period(
        week=request.query_params.get("week", ""),
        month=request.query_params.get("month", ""),
        today=timezone.localdate(),
    )


def assignment_for_viewer(user: User, pk: int) -> TaskAssignment:
    """Load one assignment and hide its existence from unauthorized users."""
    assignment = get_object_or_404(
        TaskAssignment.objects.select_related(
            "task", "task__action", "employee", "manager", "calendar"
        ).prefetch_related("calendar__days", "progress_entries", "activities__actor"),
        pk=pk,
    )
    if not can_view_assignment(user, assignment):
        raise Http404
    return assignment


def proposal_for_viewer(user: User, pk: int) -> TaskProposal:
    """Load one proposal while hiding it from unauthorized users."""
    proposal = get_object_or_404(
        TaskProposal.objects.select_related(
            "employee",
            "reviewed_by",
            "action",
            "calendar",
            "accepted_assignment",
        ),
        pk=pk,
    )
    if (
        proposal.employee_id != user.pk
        and not can_review_proposal(user, proposal)
        and not visible_team_proposals(user).filter(pk=proposal.pk).exists()
    ):
        raise Http404
    return proposal


class SessionView(APIView):
    """Expose the current session and seed the CSRF cookie for unsafe calls."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = request_user(request)
        return Response(
            {
                "user": person_payload(user),
                "csrf_token": get_token(request._request),
                "capabilities": {
                    "create_task": bool(assignable_employee_ids(user)),
                    "create_proposal": user.is_active,
                    "view_team": bool(visible_employee_ids(user) - {user.pk}),
                    "self_assign": can_self_assign(user),
                    "admin": user.is_staff,
                    "manage_visits": can_manage_visits(user),
                    "manage_availability": can_manage_availability(user),
                    "prepare_weekly_agenda": can_prepare_agenda(user),
                    "view_weekly_agenda": can_view_agenda(user),
                },
            }
        )


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DashboardView(APIView):
    @extend_schema(parameters=PERIOD_PARAMETERS, responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = request_user(request)
        period = selected_period(request)
        assignments = period_assignments(user, period)
        return Response(
            {
                "period": period_payload(period),
                "today": timezone.localdate().isoformat(),
                "tasks": [
                    assignment_summary_payload(assignment, period)
                    for assignment in assignments
                ],
            }
        )


class PlanningOptionsView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = request_user(request)
        today = timezone.localdate()
        calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
        start = today
        while not calendar.is_working_day(start):
            start = date.fromordinal(start.toordinal() + 1)
        workload = Decimal("5.0")
        employees = User.objects.filter(
            pk__in=assignable_employee_ids(user), is_active=True
        )
        return Response(
            {
                "employees": [person_payload(employee) for employee in employees],
                "actions": [
                    {"id": action.pk, "label": str(action)}
                    for action in InstitutionalAction.objects.filter(active=True)
                ],
                "calendars": [
                    {"id": item.pk, "label": str(item)}
                    for item in WorkCalendar.objects.filter(active=True)
                ],
                "defaults": {
                    "calendar_id": calendar.pk,
                    "start_date": start.isoformat(),
                    "due_date": due_date_for(start, workload, calendar).isoformat(),
                    "estimated_work_days": decimal_text(workload),
                },
            }
        )


class PlanningPreviewView(APIView):
    @extend_schema(request=PlanningPreviewSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        serializer = PlanningPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        calendar = get_object_or_404(WorkCalendar, pk=data["calendar_id"], active=True)
        start = cast(date, data["start_date"])
        if not calendar.is_working_day(start):
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"start_date": "Le début doit être un jour ouvré."})
        if data["source"] == "workload":
            workload = cast(Decimal, data["estimated_work_days"])
            due = due_date_for(start, workload, calendar)
        else:
            due = cast(date, data["due_date"])
            workload = workload_for(start, due, calendar)
            if workload <= 0:
                from rest_framework.exceptions import ValidationError

                raise ValidationError(
                    {"due_date": "L'échéance doit inclure un jour ouvré."}
                )
        return Response(
            {
                "start_date": start.isoformat(),
                "due_date": due.isoformat(),
                "estimated_work_days": decimal_text(workload),
            }
        )


class TaskCreateView(APIView):
    @extend_schema(request=TaskCreateSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        user = request_user(request)
        employee = get_object_or_404(User, pk=data["employee_id"], is_active=True)
        action = (
            get_object_or_404(InstitutionalAction, pk=data["action_id"], active=True)
            if data.get("action_id")
            else None
        )
        calendar = get_object_or_404(
            WorkCalendar,
            pk=data.get("calendar_id", default_work_calendar_id()),
            active=True,
        )
        assignment = create_assignment_for_user(
            manager=user,
            employee=employee,
            title=data["title"],
            description=data["description"],
            action=action,
            start_date=data["start_date"],
            due_date=data["due_date"],
            estimated_work_days=data["estimated_work_days"],
            calendar=calendar,
        )
        assignment = assignment_for_viewer(user, assignment.pk)
        return Response(
            assignment_detail_payload(assignment, user),
            status=status.HTTP_201_CREATED,
        )


class TaskDetailView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, pk: int) -> Response:
        user = request_user(request)
        return Response(assignment_detail_payload(assignment_for_viewer(user, pk), user))

    @extend_schema(request=TaskUpdateSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request: Request, pk: int) -> Response:
        serializer = TaskUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        user = request_user(request)
        assignment = assignment_for_viewer(user, pk)
        action = (
            get_object_or_404(InstitutionalAction, pk=data["action_id"], active=True)
            if data.get("action_id")
            else None
        )
        update_assignment_details(
            user=user,
            assignment=assignment,
            title=data["title"],
            description=data["description"],
            action=action,
            start_date=data["start_date"],
            due_date=data["due_date"],
            estimated_work_days=data["estimated_work_days"],
            expected_revision=data["revision"],
        )
        return Response(assignment_detail_payload(assignment_for_viewer(user, pk), user))


class TaskProgressView(APIView):
    @extend_schema(request=ProgressSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: int) -> Response:
        serializer = ProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        user = request_user(request)
        assignment = assignment_for_viewer(user, pk)
        record_progress(
            user=user,
            assignment=assignment,
            entry_date=data["entry_date"],
            percentage=data["percentage"],
            note=data["note"],
            blocked=data["blocked"],
            expected_revision=data["revision"],
        )
        return Response(assignment_detail_payload(assignment_for_viewer(user, pk), user))


class TaskObservationView(APIView):
    @extend_schema(request=ObservationSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: int) -> Response:
        serializer = ObservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        user = request_user(request)
        assignment = assignment_for_viewer(user, pk)
        add_observation(
            user=user,
            assignment=assignment,
            message=data["message"],
            expected_revision=data["revision"],
        )
        return Response(assignment_detail_payload(assignment_for_viewer(user, pk), user))


class TaskTransitionView(APIView):
    @extend_schema(request=TransitionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: int) -> Response:
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        user = request_user(request)
        assignment = assignment_for_viewer(user, pk)
        if data["transition"] == "validate":
            validate_completion(user, assignment, data["revision"])
        elif data["transition"] == "reject":
            reject_completion(user, assignment, data["reason"], data["revision"])
        else:
            close_early(user, assignment, data["reason"], data["revision"])
        return Response(assignment_detail_payload(assignment_for_viewer(user, pk), user))


class ProposalListCreateView(APIView):
    @extend_schema(operation_id="proposal_list", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = request_user(request)
        common = (
            "employee",
            "reviewed_by",
            "action",
            "calendar",
            "accepted_assignment",
        )
        own = TaskProposal.objects.filter(employee=user).select_related(*common)
        reviewable = reviewable_proposals(user).select_related(*common)
        reviewable_ids = set(reviewable.values_list("pk", flat=True))
        read_only = (
            visible_team_proposals(user)
            .exclude(pk__in=reviewable_ids)
            .select_related(*common)
        )
        return Response(
            {
                "own": [proposal_payload(item, user) for item in own],
                "reviewable": [proposal_payload(item, user) for item in reviewable],
                "read_only": [proposal_payload(item, user) for item in read_only],
            }
        )

    @extend_schema(
        operation_id="proposal_create",
        request=ProposalCreateSerializer,
        responses={201: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        serializer = ProposalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        user = request_user(request)
        from work.services import organization_unit_for_employee

        unit_id = organization_unit_for_employee(user, data["start_date"])
        if unit_id is None:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "Votre compte doit être rattaché à un service pour proposer une tâche."
            )
        action = (
            get_object_or_404(InstitutionalAction, pk=data["action_id"], active=True)
            if data.get("action_id")
            else None
        )
        calendar = get_object_or_404(
            WorkCalendar,
            pk=data.get("calendar_id", default_work_calendar_id()),
            active=True,
        )
        proposal = TaskProposal(
            employee=user,
            organization_unit_id=unit_id,
            title=data["title"],
            description=data["description"],
            action=action,
            calendar=calendar,
            start_date=data["start_date"],
            due_date=data["due_date"],
            estimated_work_days=data["estimated_work_days"],
        )
        proposal.save()
        return Response(proposal_payload(proposal, user), status=status.HTTP_201_CREATED)


class ProposalDetailView(APIView):
    @extend_schema(operation_id="proposal_detail", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, pk: int) -> Response:
        user = request_user(request)
        return Response(proposal_payload(proposal_for_viewer(user, pk), user))

    @extend_schema(
        operation_id="proposal_update",
        request=ProposalUpdateSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = ProposalUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        user = request_user(request)
        proposal = proposal_for_viewer(user, pk)
        action = (
            get_object_or_404(InstitutionalAction, pk=data["action_id"], active=True)
            if data.get("action_id")
            else None
        )
        calendar = get_object_or_404(
            WorkCalendar,
            pk=data.get("calendar_id", proposal.calendar_id),
            active=True,
        )
        update_proposal(
            user=user,
            proposal=proposal,
            title=data["title"],
            description=data["description"],
            action=action,
            calendar=calendar,
            start_date=data["start_date"],
            due_date=data["due_date"],
            estimated_work_days=data["estimated_work_days"],
            expected_revision=data["revision"],
        )
        return Response(proposal_payload(proposal_for_viewer(user, pk), user))


class ProposalResubmitView(APIView):
    @extend_schema(
        operation_id="proposal_resubmit",
        request=ProposalResubmitSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = ProposalResubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request_user(request)
        proposal = proposal_for_viewer(user, pk)
        resubmit_proposal(
            user=user,
            proposal=proposal,
            expected_revision=serializer.validated_data["revision"],
        )
        return Response(proposal_payload(proposal_for_viewer(user, pk), user))


class ProposalDecisionView(APIView):
    @extend_schema(
        operation_id="proposal_decision",
        request=ProposalDecisionSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = ProposalDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data
        user = request_user(request)
        proposal = proposal_for_viewer(user, pk)
        if data["decision"] == "accept":
            accept_proposal(user, proposal, expected_revision=data["revision"])
        else:
            reject_proposal(
                user, proposal, data["reason"], expected_revision=data["revision"]
            )
        return Response(proposal_payload(proposal_for_viewer(user, pk), user))


def team_node_payload(node: Any) -> dict[str, object]:
    return {
        "employee": person_payload(node.employee),
        "task_count": node.task_count,
        "children": [team_node_payload(child) for child in node.children],
    }


class TeamView(APIView):
    @extend_schema(
        operation_id="team_overview",
        parameters=PERIOD_PARAMETERS,
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        user = request_user(request)
        period = selected_period(request)
        return Response(
            {
                "period": period_payload(period),
                "nodes": [
                    team_node_payload(node) for node in team_tree_overview(user, period)
                ],
            }
        )


class TeamEmployeeView(APIView):
    @extend_schema(
        operation_id="team_employee_detail",
        parameters=PERIOD_PARAMETERS,
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request, pk: int) -> Response:
        user = request_user(request)
        employee = get_object_or_404(User, pk=pk, is_active=True)
        if not can_view_employee(user, employee):
            raise Http404
        period = selected_period(request)
        assignments = period_assignments(employee, period, viewer=user)
        return Response(
            {
                "period": period_payload(period),
                "employee": person_payload(employee),
                "tasks": [
                    assignment_summary_payload(assignment, period)
                    for assignment in assignments
                ],
            }
        )
