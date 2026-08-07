"""Session-authenticated API for weekly agenda preparation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import cast

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
    AvailabilityKind,
    StaffAvailability,
    VisitorVisit,
    WeeklyAgendaDraft,
    WeeklyAgendaVersion,
)
from agenda.services import (
    agenda_pdf_bytes,
    build_week_snapshot,
    can_manage_availability,
    can_manage_visits,
    can_prepare_agenda,
    can_view_agenda,
    cancel_availability,
    create_availability,
    create_visit,
    generate_agenda,
    mark_visit_departed,
    normalize_week,
    save_draft,
    update_availability,
)
from work.models import OrganizationMembership


WEEK_PARAMETER = OpenApiParameter("week", OpenApiTypes.DATE, required=False)


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


class DraftSerializer(serializers.Serializer):
    week_start = serializers.DateField()
    major_events = serializers.CharField(required=False, allow_blank=True, default="")
    revision = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class GenerateSerializer(serializers.Serializer):
    week_start = serializers.DateField()


def _user(request: Request) -> User:
    return cast(User, request.user)


def _week(request: Request) -> date:
    raw = request.query_params.get("week", "")
    try:
        selected = date.fromisoformat(raw) if raw else timezone.localdate()
    except ValueError as exc:
        raise serializers.ValidationError({"week": "Date de semaine invalide."}) from exc
    return normalize_week(selected)


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


def version_payload(version: WeeklyAgendaVersion) -> dict[str, object]:
    return {
        "id": version.pk,
        "week_start": version.week_start.isoformat(),
        "version": version.version,
        "snapshot_sha256": version.snapshot_sha256,
        "pdf_sha256": version.pdf_sha256,
        "pdf_size": version.pdf_size,
        "generated_by": _person(version.generated_by),
        "generated_at": version.generated_at.isoformat(),
        "pdf_url": f"/api/v1/agenda/versions/{version.pk}/pdf/",
    }


class VisitListCreateView(APIView):
    @extend_schema(parameters=[WEEK_PARAMETER], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = _user(request)
        if not can_manage_visits(user):
            raise Http404
        monday = _week(request)
        sunday = monday + timedelta(days=6)
        visits = VisitorVisit.objects.filter(
            arrived_at__date__lte=sunday, cancelled_at__isnull=True
        ).filter(Q(departed_at__isnull=True) | Q(departed_at__date__gte=monday))
        return Response(
            {
                "week_start": monday.isoformat(),
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
    @extend_schema(parameters=[WEEK_PARAMETER], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = _user(request)
        if not can_prepare_agenda(user):
            raise Http404
        monday = _week(request)
        draft = WeeklyAgendaDraft.objects.filter(week_start=monday).first()
        major_events = draft.major_events if draft else ""
        return Response(
            {
                "draft": {
                    "week_start": monday.isoformat(),
                    "major_events": major_events,
                    "revision": draft.revision if draft else 0,
                },
                "snapshot": build_week_snapshot(
                    week_start=monday, major_events=major_events
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
                "week_start": draft.week_start.isoformat(),
                "major_events": draft.major_events,
                "revision": draft.revision,
            }
        )


class AgendaVersionListCreateView(APIView):
    @extend_schema(parameters=[WEEK_PARAMETER], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = _user(request)
        if not can_view_agenda(user):
            raise Http404
        versions = WeeklyAgendaVersion.objects.select_related("generated_by")
        raw = request.query_params.get("week")
        if raw:
            versions = versions.filter(week_start=_week(request))
        return Response({"versions": [version_payload(item) for item in versions]})

    @extend_schema(request=GenerateSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        serializer = GenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = generate_agenda(
            actor=_user(request), week_start=serializer.validated_data["week_start"]
        )
        return Response(version_payload(version), status=status.HTTP_201_CREATED)


class AgendaVersionPdfView(APIView):
    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request: Request, pk: int) -> HttpResponse:
        user = _user(request)
        if not can_view_agenda(user):
            raise Http404
        version = get_object_or_404(WeeklyAgendaVersion, pk=pk)
        response = HttpResponse(agenda_pdf_bytes(version), content_type="application/pdf")
        response["Content-Disposition"] = cast(
            str,
            content_disposition_header(
                False,
                f"agenda-{version.week_start.isoformat()}-v{version.version}.pdf",
            ),
        )
        response["Cache-Control"] = "private, no-store"
        return response
