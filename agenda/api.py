"""Session-authenticated API for weekly agenda preparation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import content_disposition_header
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from agenda.models import (
    AgendaDirection,
    AgendaDraft,
    AgendaVersion,
    AvailabilityKind,
    StaffAvailability,
    VisitorVisit,
)
from agenda.services import (
    agenda_pdf_bytes,
    build_agenda_snapshot,
    can_manage_availability,
    can_manage_visits,
    can_prepare_agenda,
    can_view_agenda,
    cancel_availability,
    create_availability,
    create_visit,
    generate_agenda,
    mark_visit_departed,
    next_week_period,
    normalize_week,
    save_draft,
    update_availability,
    validate_agenda_period,
)
from work.models import OrganizationMembership


WEEK_PARAMETER = OpenApiParameter("week", OpenApiTypes.DATE, required=False)
PERIOD_PARAMETERS = [
    OpenApiParameter("period_start", OpenApiTypes.DATE, required=False),
    OpenApiParameter("period_end", OpenApiTypes.DATE, required=False),
]


class VisitCreateSerializer(serializers.Serializer):
    party_size = serializers.IntegerField(min_value=1, max_value=999)
    visitor_names = serializers.ListField(
        child=serializers.CharField(max_length=160), required=False, default=list
    )


class RevisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)


class AvailabilitySerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=AvailabilityKind.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if cast(date, attrs["end_date"]) < cast(date, attrs["start_date"]):
            raise serializers.ValidationError(
                {"end_date": "La fin doit suivre le début."}
            )
        return attrs


class AvailabilityUpdateSerializer(AvailabilitySerializer):
    revision = serializers.IntegerField(min_value=1)


class CancelSerializer(RevisionSerializer):
    reason = serializers.CharField()


class PeriodSerializer(serializers.Serializer):
    period_start = serializers.DateField()
    period_end = serializers.DateField()

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        try:
            validate_agenda_period(
                cast(date, attrs["period_start"]), cast(date, attrs["period_end"])
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs


class DraftSerializer(PeriodSerializer):
    major_events = serializers.CharField(required=False, allow_blank=True, default="")
    revision = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class GenerateSerializer(PeriodSerializer):
    agenda_direction = serializers.ChoiceField(
        choices=(
            AgendaDirection.PROGRAMS,
            AgendaDirection.ADMINISTRATION,
        )
    )


def _user(request: Request) -> User:
    return cast(User, request.user)


def _week(request: Request) -> date:
    raw = request.query_params.get("week", "")
    try:
        selected = date.fromisoformat(raw) if raw else timezone.localdate()
    except ValueError as exc:
        raise serializers.ValidationError({"week": "Date de semaine invalide."}) from exc
    return normalize_week(selected)


def _period(request: Request) -> tuple[date, date]:
    default_start, default_end = next_week_period(timezone.localdate())
    raw_start = request.query_params.get("period_start", "")
    raw_end = request.query_params.get("period_end", "")
    try:
        period_start = date.fromisoformat(raw_start) if raw_start else default_start
        period_end = date.fromisoformat(raw_end) if raw_end else default_end
    except ValueError as exc:
        raise serializers.ValidationError({"period_start": "Période invalide."}) from exc
    try:
        validate_agenda_period(period_start, period_end)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.message_dict) from exc
    return period_start, period_end


def _agenda_direction(request: Request) -> str:
    value = request.query_params.get("agenda_direction", AgendaDirection.PROGRAMS)
    if value not in (AgendaDirection.PROGRAMS, AgendaDirection.ADMINISTRATION):
        raise serializers.ValidationError(
            {"agenda_direction": "Direction d’agenda inconnue."}
        )
    return cast(str, value)


def _person(user: User) -> dict[str, object]:
    return {"id": user.pk, "name": str(user), "position": user.position}


def visit_payload(visit: VisitorVisit) -> dict[str, object]:
    return {
        "id": visit.pk,
        "revision": visit.revision,
        "party_size": visit.party_size,
        "visitor_names": visit.visitor_names,
        "arrived_at": visit.arrived_at.isoformat(),
        "departed_at": visit.departed_at.isoformat() if visit.departed_at else None,
        "cancelled_at": visit.cancelled_at.isoformat() if visit.cancelled_at else None,
    }


def availability_payload(item: StaffAvailability) -> dict[str, object]:
    return {
        "id": item.pk,
        "revision": item.revision,
        "employee": _person(item.employee),
        "kind": item.kind,
        "kind_label": item.get_kind_display(),
        "start_date": item.start_date.isoformat(),
        "end_date": item.end_date.isoformat(),
        "note": item.note,
        "cancelled_at": item.cancelled_at.isoformat() if item.cancelled_at else None,
    }


def version_payload(version: AgendaVersion) -> dict[str, object]:
    return {
        "id": version.pk,
        "period_start": version.period_start.isoformat(),
        "period_end": version.period_end.isoformat(),
        "agenda_direction": version.agenda_direction,
        "agenda_direction_label": version.get_agenda_direction_display(),
        "version": version.version,
        "snapshot_sha256": version.snapshot_sha256,
        "pdf_sha256": version.pdf_sha256,
        "pdf_size": version.pdf_size,
        "generated_by": _person(version.generated_by),
        "generated_at": version.generated_at.isoformat(),
        "pdf_url": f"/api/v1/agenda/versions/{version.pk}/pdf/",
    }


class VisitListCreateView(APIView):
    @extend_schema(parameters=PERIOD_PARAMETERS, responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = _user(request)
        if not can_manage_visits(user):
            raise Http404
        period_start, period_end = _period(request)
        visits = VisitorVisit.objects.filter(
            arrived_at__date__lte=period_end, cancelled_at__isnull=True
        ).filter(Q(departed_at__isnull=True) | Q(departed_at__date__gte=period_start))
        return Response(
            {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "visits": [visit_payload(item) for item in visits],
            }
        )

    @extend_schema(request=VisitCreateSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        serializer = VisitCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        visit = create_visit(actor=_user(request), **serializer.validated_data)
        return Response(visit_payload(visit), status=status.HTTP_201_CREATED)


class VisitDepartureView(APIView):
    @extend_schema(request=RevisionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: int) -> Response:
        serializer = RevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        visit = mark_visit_departed(
            actor=_user(request),
            visit=get_object_or_404(VisitorVisit, pk=pk),
            expected_revision=serializer.validated_data["revision"],
        )
        return Response(visit_payload(visit))


class AvailabilityListCreateView(APIView):
    @extend_schema(parameters=[WEEK_PARAMETER], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = _user(request)
        if not can_manage_availability(user):
            raise Http404
        monday = _week(request)
        sunday = monday + timedelta(days=6)
        items = StaffAvailability.objects.filter(
            cancelled_at__isnull=True,
            start_date__lte=sunday,
            end_date__gte=monday,
        ).select_related("employee")
        employee_ids = OrganizationMembership.objects.filter(
            is_primary=True,
            end_date__isnull=True,
            user__is_active=True,
        ).values_list("user_id", flat=True)
        employees = User.objects.filter(pk__in=employee_ids).order_by(
            "last_name", "first_name", "email"
        )
        return Response(
            {
                "week_start": monday.isoformat(),
                "items": [availability_payload(item) for item in items],
                "employees": [_person(employee) for employee in employees],
                "kinds": [
                    {"value": value, "label": label}
                    for value, label in AvailabilityKind.choices
                ],
            }
        )

    @extend_schema(request=AvailabilitySerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        serializer = AvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = get_object_or_404(
            User, pk=serializer.validated_data.pop("employee_id"), is_active=True
        )
        item = create_availability(
            actor=_user(request), employee=employee, **serializer.validated_data
        )
        return Response(availability_payload(item), status=status.HTTP_201_CREATED)


class AvailabilityDetailView(APIView):
    @extend_schema(request=AvailabilityUpdateSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request: Request, pk: int) -> Response:
        serializer = AvailabilityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        employee_id = values.pop("employee_id")
        item = get_object_or_404(StaffAvailability, pk=pk)
        if employee_id != item.employee_id:
            raise serializers.ValidationError(
                {"employee_id": "L’agent d’une indisponibilité ne peut pas être changé."}
            )
        expected_revision = values.pop("revision")
        item = update_availability(
            actor=_user(request),
            item=item,
            expected_revision=expected_revision,
            **values,
        )
        return Response(availability_payload(item))


class AvailabilityCancelView(APIView):
    @extend_schema(request=CancelSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request, pk: int) -> Response:
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = cancel_availability(
            actor=_user(request),
            item=get_object_or_404(StaffAvailability, pk=pk),
            expected_revision=serializer.validated_data["revision"],
            reason=serializer.validated_data["reason"],
        )
        return Response(availability_payload(item))


class AgendaPreviewView(APIView):
    @extend_schema(
        parameters=PERIOD_PARAMETERS
        + [OpenApiParameter("agenda_direction", OpenApiTypes.STR, required=False)],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        user = _user(request)
        if not can_prepare_agenda(user):
            raise Http404
        period_start, period_end = _period(request)
        agenda_direction = _agenda_direction(request)
        draft = AgendaDraft.objects.filter(
            period_start=period_start, period_end=period_end
        ).first()
        major_events = draft.major_events if draft else ""
        return Response(
            {
                "draft": {
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "major_events": major_events,
                    "revision": draft.revision if draft else 0,
                },
                "snapshot": build_agenda_snapshot(
                    period_start=period_start,
                    period_end=period_end,
                    agenda_direction=agenda_direction,
                    major_events=major_events,
                ),
            }
        )


class AgendaDraftView(APIView):
    @extend_schema(request=DraftSerializer, responses=OpenApiTypes.OBJECT)
    def put(self, request: Request) -> Response:
        serializer = DraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected_revision = values.pop("revision", None)
        draft = save_draft(
            actor=_user(request),
            expected_revision=expected_revision,
            **values,
        )
        return Response(
            {
                "period_start": draft.period_start.isoformat(),
                "period_end": draft.period_end.isoformat(),
                "major_events": draft.major_events,
                "revision": draft.revision,
            }
        )


class AgendaVersionListCreateView(APIView):
    @extend_schema(
        parameters=PERIOD_PARAMETERS
        + [OpenApiParameter("agenda_direction", OpenApiTypes.STR, required=False)],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        user = _user(request)
        if not can_view_agenda(user):
            raise Http404
        versions = AgendaVersion.objects.select_related("generated_by")
        if request.query_params.get("period_start") or request.query_params.get(
            "period_end"
        ):
            period_start, period_end = _period(request)
            versions = versions.filter(period_start=period_start, period_end=period_end)
        direction = request.query_params.get("agenda_direction")
        if direction:
            if direction not in AgendaDirection.values:
                raise serializers.ValidationError(
                    {"agenda_direction": "Direction d’agenda inconnue."}
                )
            versions = versions.filter(agenda_direction=direction)
        return Response({"versions": [version_payload(item) for item in versions]})

    @extend_schema(request=GenerateSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        serializer = GenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = generate_agenda(actor=_user(request), **serializer.validated_data)
        return Response(version_payload(version), status=status.HTTP_201_CREATED)


class AgendaVersionPdfView(APIView):
    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request: Request, pk: int) -> HttpResponse:
        user = _user(request)
        if not can_view_agenda(user):
            raise Http404
        version = get_object_or_404(AgendaVersion, pk=pk)
        response = HttpResponse(agenda_pdf_bytes(version), content_type="application/pdf")
        response["Content-Disposition"] = cast(
            str,
            content_disposition_header(
                False,
                f"agenda-{version.agenda_direction}-{version.period_start.isoformat()}-"
                f"{version.period_end.isoformat()}-v{version.version}.pdf",
            ),
        )
        response["Cache-Control"] = "private, no-store"
        return response
