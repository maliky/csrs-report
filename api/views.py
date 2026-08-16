from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast

from django.contrib.auth import logout, update_session_auth_hash
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q, QuerySet
from django.http import Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AgendaDirection, User
from accounts.services import (
    StaleUserStateError,
    bulk_manage_users,
    can_manage_users,
    complete_temporary_password_change,
    create_managed_user,
    ensure_can_manage_users,
    reset_managed_user_password,
    send_activation,
    set_managed_user_active,
    update_own_profile,
    update_managed_user,
    user_management_state_token,
)
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
    collaborator_management_payload,
    organization_unit_payload,
    period_payload,
    person_payload,
    user_profile_payload,
    proposal_payload,
    task_management_payload,
    user_management_detail_payload,
    user_management_summary_payload,
)
from api.serializers import (
    ObservationSerializer,
    CollaboratorUpdateSerializer,
    PlanningPreviewSerializer,
    ProgressSerializer,
    ProposalCreateSerializer,
    ProposalDecisionSerializer,
    ProposalResubmitSerializer,
    ProposalUpdateSerializer,
    TaskCreateSerializer,
    TaskBulkDeleteSerializer,
    TaskManagementQuerySerializer,
    TaskUpdateSerializer,
    StateTokenSerializer,
    TemporaryPasswordChangeSerializer,
    TransitionSerializer,
    UserManagementQuerySerializer,
    UserBulkActionSerializer,
    UserUpdateSerializer,
    UserWriteSerializer,
    MeProfileSerializer,
)
from work.models import (
    InstitutionalAction,
    OrganizationMembership,
    OrganizationUnit,
    ReportingLine,
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
    can_delete_reporting_data,
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
    delete_task_assignments,
    update_primary_collaborators,
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


def managed_user_queryset() -> QuerySet[User]:
    """Load routine user administration rows with their current memberships."""
    memberships = OrganizationMembership.objects.filter(
        end_date__isnull=True
    ).select_related("unit")
    reporting_lines = ReportingLine.objects.filter(end_date__isnull=True)
    return User.objects.prefetch_related(
        Prefetch(
            "organization_memberships",
            queryset=memberships,
            to_attr="current_organization_memberships",
        ),
        Prefetch(
            "reporting_lines",
            queryset=reporting_lines,
            to_attr="current_reporting_lines",
        ),
    )


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
                    "delete_tasks": can_delete_reporting_data(user),
                    "manage_users": can_manage_users(user),
                    "password_change_required": user.password_change_required,
                },
            }
        )


class MeProfileView(APIView):
    """Read and edit the current user's own profile details."""

    @extend_schema(operation_id="my_profile", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        return Response(user_profile_payload(request_user(request)))

    @extend_schema(
        operation_id="my_profile_update",
        request=MeProfileSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def patch(self, request: Request) -> Response:
        serializer = MeProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request_user(request)
        user = update_own_profile(
            user=user,
            actor=user,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            phone=data.get("phone"),
            avatar=data.get("avatar"),
            terms_of_reference=data.get("terms_of_reference"),
        )
        return Response(user_profile_payload(user))


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionPasswordView(APIView):
    """Complete the mandatory replacement of a temporary password."""

    @extend_schema(request=TemporaryPasswordChangeSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        serializer = TemporaryPasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = complete_temporary_password_change(
            user=request_user(request),
            current_password=str(data["current_password"]),
            new_password=str(data["new_password"]),
        )
        update_session_auth_hash(request._request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserListCreateView(APIView):
    """List and create institution-managed accounts."""

    @extend_schema(
        operation_id="user_list",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, required=False),
            OpenApiParameter("state", OpenApiTypes.STR, required=False),
            OpenApiParameter("unit_id", OpenApiTypes.INT, required=False),
            OpenApiParameter("page", OpenApiTypes.INT, required=False),
            OpenApiParameter("page_size", OpenApiTypes.INT, required=False),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        actor = request_user(request)
        ensure_can_manage_users(actor)
        serializer = UserManagementQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = managed_user_queryset()
        query = str(data["q"]).strip()
        if query:
            queryset = queryset.filter(
                Q(email__icontains=query)
                | Q(login_alias__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(position__icontains=query)
            )
        if data["state"] == "active":
            queryset = queryset.filter(is_active=True)
        elif data["state"] == "inactive":
            queryset = queryset.filter(is_active=False)
        if data.get("unit_id"):
            queryset = queryset.filter(
                organization_memberships__unit_id=data["unit_id"],
                organization_memberships__end_date__isnull=True,
            )
        queryset = queryset.distinct().order_by("last_name", "first_name", "email")
        paginator = Paginator(queryset, int(data["page_size"]))
        page = paginator.get_page(int(data["page"]))
        return Response(
            {
                "items": [
                    user_management_summary_payload(user, actor)
                    for user in page.object_list
                ],
                "total": paginator.count,
                "page": page.number,
                "pages": paginator.num_pages,
                "page_size": int(data["page_size"]),
            }
        )

    @extend_schema(
        operation_id="user_create",
        request=UserWriteSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request: Request) -> Response:
        serializer = UserWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = request_user(request)
        user = create_managed_user(
            actor=actor,
            email=str(data["email"]),
            login_alias=str(data.get("login_alias") or "") or None,
            first_name=str(data.get("first_name", "")),
            last_name=str(data.get("last_name", "")),
            position=str(data.get("position", "")),
            phone=str(data.get("phone", "")),
            agenda_direction=str(data.get("agenda_direction", "")),
            include_in_direction_agendas=bool(
                data.get("include_in_direction_agendas", True)
            ),
            unit_ids=set(data.get("unit_ids", [])),
            primary_unit_id=cast(int | None, data.get("primary_unit_id")),
            primary_supervisor_id=cast(int | None, data.get("primary_supervisor_id")),
            organization_effective_date=cast(date, data["organization_effective_date"]),
        )
        user = managed_user_queryset().get(pk=user.pk)
        return Response(
            user_management_detail_payload(user, actor),
            status=status.HTTP_201_CREATED,
        )


class UserBulkActionView(APIView):
    """Apply one audited account action to at most one visible page."""

    @extend_schema(
        operation_id="users_bulk_action",
        request=UserBulkActionSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request: Request) -> Response:
        serializer = UserBulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        selections = [
            (cast(int, item["id"]), str(item["state_token"]))
            for item in cast(list[dict[str, object]], data["users"])
        ]
        action = str(data["action"])
        affected = bulk_manage_users(
            actor=request_user(request),
            action=action,
            selections=selections,
            reason=str(data.get("reason", "")),
        )
        return Response({"action": action, "affected": affected})


class UserOptionsView(APIView):
    """Expose active organization choices for the user editor."""

    @extend_schema(operation_id="user_options", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        ensure_can_manage_users(request_user(request))
        return Response(
            {
                "today": timezone.localdate().isoformat(),
                "units": [
                    organization_unit_payload(unit)
                    for unit in OrganizationUnit.objects.filter(active=True)
                ],
                "users": [
                    person_payload(user)
                    for user in User.objects.filter(is_active=True).order_by(
                        "last_name", "first_name", "email"
                    )
                ],
                "agenda_directions": [
                    {"value": value, "label": label}
                    for value, label in AgendaDirection.choices
                ],
            }
        )


class UserDetailView(APIView):
    """Read and update one account and its calculated organization fields."""

    @extend_schema(operation_id="user_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, pk: int) -> Response:
        actor = request_user(request)
        ensure_can_manage_users(actor)
        user = get_object_or_404(managed_user_queryset(), pk=pk)
        return Response(user_management_detail_payload(user, actor))

    @extend_schema(
        operation_id="user_update",
        request=UserUpdateSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = UserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = request_user(request)
        target = get_object_or_404(User, pk=pk)
        user = update_managed_user(
            actor=actor,
            user=target,
            expected_token=str(data["state_token"]),
            email=str(data["email"]),
            login_alias=str(data.get("login_alias") or "") or None,
            first_name=str(data.get("first_name", "")),
            last_name=str(data.get("last_name", "")),
            position=str(data.get("position", "")),
            phone=str(data.get("phone", "")),
            agenda_direction=str(data.get("agenda_direction", "")),
            include_in_direction_agendas=bool(
                data.get("include_in_direction_agendas", True)
            ),
            unit_ids=set(data.get("unit_ids", [])),
            primary_unit_id=cast(int | None, data.get("primary_unit_id")),
            primary_supervisor_id=cast(int | None, data.get("primary_supervisor_id")),
            organization_effective_date=cast(date, data["organization_effective_date"]),
        )
        user = managed_user_queryset().get(pk=user.pk)
        return Response(user_management_detail_payload(user, actor))


class UserActivationView(APIView):
    """Send the existing one-time activation link for a new account."""

    @extend_schema(request=StateTokenSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: int) -> Response:
        serializer = StateTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = request_user(request)
        user = get_object_or_404(User, pk=pk)
        ensure_can_manage_users(actor, user)
        if user_management_state_token(user) != serializer.validated_data["state_token"]:
            raise StaleUserStateError(
                "Ce compte a change depuis l'ouverture de la fiche. Rechargez la page."
            )
        if not user.is_active:
            raise ValidationError("Reactivez ce compte avant d'envoyer son activation.")
        if user.has_usable_password():
            raise ValidationError(
                "Ce compte possede deja un mot de passe. Utilisez la reinitialisation."
            )
        sent = send_activation(request._request, user)
        return Response({"sent": sent})


class UserActiveView(APIView):
    """Deactivate or reactivate a retained account."""

    active: bool

    @extend_schema(request=StateTokenSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: int) -> Response:
        serializer = StateTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = request_user(request)
        user = set_managed_user_active(
            actor=actor,
            user=get_object_or_404(User, pk=pk),
            active=self.active,
            expected_token=str(serializer.validated_data["state_token"]),
        )
        user = managed_user_queryset().get(pk=user.pk)
        return Response(user_management_detail_payload(user, actor))


class UserDeactivateView(UserActiveView):
    active = False


class UserReactivateView(UserActiveView):
    active = True


class UserTemporaryPasswordView(APIView):
    """Generate and disclose one temporary password once."""

    @extend_schema(request=StateTokenSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: int) -> Response:
        serializer = StateTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = request_user(request)
        user, temporary_password = reset_managed_user_password(
            actor=actor,
            user=get_object_or_404(User, pk=pk),
            expected_token=str(serializer.validated_data["state_token"]),
        )
        response = Response(
            {
                "temporary_password": temporary_password,
                "state_token": user_management_state_token(user),
            }
        )
        response["Cache-Control"] = "no-store"
        return response


class UserCollaboratorsView(APIView):
    """Read or replace one user's direct primary collaborators."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, pk: int) -> Response:
        actor = request_user(request)
        supervisor = get_object_or_404(User, pk=pk)
        ensure_can_manage_users(actor)
        return Response(collaborator_management_payload(supervisor))

    @extend_schema(request=CollaboratorUpdateSerializer, responses=OpenApiTypes.OBJECT)
    def put(self, request: Request, pk: int) -> Response:
        serializer = CollaboratorUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = request_user(request)
        supervisor = get_object_or_404(User, pk=pk)
        ensure_can_manage_users(actor, supervisor)
        update_primary_collaborators(
            actor=actor,
            supervisor=supervisor,
            collaborator_ids=set(data["collaborator_ids"]),
            replacements={
                item["employee_id"]: item["supervisor_id"]
                for item in data.get("replacements", [])
            },
            effective_date=cast(date, data["effective_date"]),
            expected_token=str(data["state_token"]),
        )
        return Response(collaborator_management_payload(supervisor))


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


class TaskManagementView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, required=False),
            OpenApiParameter("status", OpenApiTypes.STR, required=False),
            OpenApiParameter("employee_id", OpenApiTypes.INT, required=False),
            OpenApiParameter("page", OpenApiTypes.INT, required=False),
            OpenApiParameter("page_size", OpenApiTypes.INT, required=False),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        user = request_user(request)
        if not can_delete_reporting_data(user):
            raise PermissionDenied("Seul un administrateur IT peut gerer les taches.")
        serializer = TaskManagementQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = TaskAssignment.objects.select_related(
            "task", "employee", "manager"
        ).prefetch_related("progress_entries")
        query = str(data["q"]).strip()
        if query:
            queryset = queryset.filter(
                Q(task__code__icontains=query)
                | Q(task__title__icontains=query)
                | Q(employee__login_alias__icontains=query)
                | Q(employee__first_name__icontains=query)
                | Q(employee__last_name__icontains=query)
            )
        if data["status"]:
            queryset = queryset.filter(status=data["status"])
        if data.get("employee_id"):
            queryset = queryset.filter(employee_id=data["employee_id"])
        queryset = queryset.order_by("employee__last_name", "task__code", "pk")
        paginator = Paginator(queryset, int(data["page_size"]))
        page = paginator.get_page(int(data["page"]))
        employees = User.objects.filter(task_assignments__isnull=False).distinct()
        return Response(
            {
                "items": [task_management_payload(item) for item in page.object_list],
                "total": paginator.count,
                "page": page.number,
                "pages": paginator.num_pages,
                "page_size": int(data["page_size"]),
                "employees": [
                    person_payload(item)
                    for item in employees.order_by("last_name", "first_name")
                ],
            }
        )


class TaskBulkDeleteView(APIView):
    @extend_schema(request=TaskBulkDeleteSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        serializer = TaskBulkDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = delete_task_assignments(
            actor=request_user(request),
            selections=((item["id"], item["revision"]) for item in data["assignments"]),
            reason=data["reason"],
        )
        return Response(
            {
                "audit_id": result.audit_id,
                "deleted_assignments": result.deleted_assignments,
                "deleted_tasks": result.deleted_tasks,
            }
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
                "employee": user_profile_payload(employee),
                "tasks": [
                    assignment_summary_payload(assignment, period)
                    for assignment in assignments
                ],
            }
        )
