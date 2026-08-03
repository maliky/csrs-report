"""REST endpoints and presentation helpers for process cases."""

from __future__ import annotations

from typing import Any, cast

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import content_disposition_header
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from processes.exports import export_case_zip
from processes.models import (
    CaseStatus,
    DocumentKind,
    MissionType,
    ProcessCase,
    ProcessDocument,
    QueueKind,
    WorkItemStatus,
)
from processes.services import (
    act_on_case,
    add_document,
    can_download_documents,
    can_edit_mission,
    can_export_case,
    can_upload_document,
    can_view_case,
    can_work_queue,
    create_mission_draft,
    document_bytes,
    may_create_mission,
    update_mission_draft,
    visible_cases,
)


class MissionSerializer(serializers.Serializer):
    mission_type = serializers.ChoiceField(choices=MissionType.choices)
    destination = serializers.CharField(max_length=220)
    purpose = serializers.CharField()
    itinerary = serializers.CharField(required=False, allow_blank=True)
    transport_mode = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    transport_company = serializers.CharField(
        max_length=160, required=False, allow_blank=True
    )
    departure_date = serializers.DateField()
    return_date = serializers.DateField()
    funding_source = serializers.CharField(
        max_length=220, required=False, allow_blank=True
    )
    costs_covered = serializers.CharField(required=False, allow_blank=True)
    vehicle_required = serializers.BooleanField(required=False, default=False)
    vehicle_details = serializers.CharField(required=False, allow_blank=True)
    participant_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    official_number = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["return_date"] < attrs["departure_date"]:
            raise serializers.ValidationError(
                {"return_date": "La date de retour doit suivre le départ."}
            )
        return attrs


class MissionUpdateSerializer(MissionSerializer):
    revision = serializers.IntegerField(min_value=1)


class ProcessActionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(
        choices=(
            "submit",
            "abandon",
            "claim",
            "takeover",
            "send_to_signature",
            "request_correction",
            "reject",
            "sign",
            "complete_distribution",
            "complete_fleet",
            "place_legal_hold",
            "release_legal_hold",
        )
    )
    note = serializers.CharField(required=False, allow_blank=True)
    confirmation = serializers.CharField(required=False, allow_blank=True)
    checklist = serializers.DictField(
        child=serializers.BooleanField(), required=False, default=dict
    )


class DocumentUploadSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=DocumentKind.choices)
    file = serializers.FileField()


def _request_user(request: Request) -> User:
    return cast(User, request.user)


def _case_for_user(user: User, pk: int) -> ProcessCase:
    case = get_object_or_404(
        ProcessCase.objects.select_related(
            "definition", "initiator", "origin_unit", "calendar", "mission_order"
        ).prefetch_related(
            "mission_participants__user",
            "documents__uploaded_by",
            "events__actor",
            "work_items__queue__role",
            "work_items__claimed_by",
        ),
        pk=pk,
    )
    if not can_view_case(user, case):
        raise Http404
    return case


def _person(user: User) -> dict[str, object]:
    return {
        "id": user.pk,
        "name": str(user),
        "position": user.position,
        "login_alias": user.login_alias,
    }


def _available_actions(user: User, case: ProcessCase) -> list[str]:
    if case.status in {CaseStatus.COMPLETED, CaseStatus.REJECTED, CaseStatus.ABANDONED}:
        if user.is_superuser or user.is_it_admin:
            return ["release_legal_hold" if case.legal_hold else "place_legal_hold"]
        return []
    if case.status == CaseStatus.DRAFT:
        return ["submit", "abandon"] if case.initiator_id == user.pk else []
    item = next(
        (
            candidate
            for candidate in reversed(list(case.work_items.all()))
            if candidate.status in (WorkItemStatus.OPEN, WorkItemStatus.CLAIMED)
        ),
        None,
    )
    if item is None or not can_work_queue(user, item.queue):
        return []
    if item.claimed_by_id is None:
        return ["claim"]
    if item.claimed_by_id != user.pk:
        return ["takeover"]
    actions_by_step: dict[str, list[str]] = {
        QueueKind.ASSISTANCE: ["send_to_signature"],
        QueueKind.SIGNATURE: ["sign", "request_correction", "reject"],
        QueueKind.DISTRIBUTION: ["complete_distribution"],
        QueueKind.FLEET: ["complete_fleet"],
    }
    return actions_by_step.get(item.step, [])


def case_payload(user: User, case: ProcessCase, *, detail: bool) -> dict[str, object]:
    mission = case.mission_order
    open_item = next(
        (
            item
            for item in reversed(list(case.work_items.all()))
            if item.status in (WorkItemStatus.OPEN, WorkItemStatus.CLAIMED)
        ),
        None,
    )
    payload: dict[str, object] = {
        "id": case.pk,
        "reference": case.reference,
        "revision": case.revision,
        "status": case.status,
        "status_label": case.get_status_display(),
        "current_step": case.current_step,
        "initiator": _person(case.initiator),
        "origin_unit": {
            "id": case.origin_unit_id,
            "name": case.origin_unit_name,
            "short_name": case.origin_unit.short_name,
        },
        "mission_type": mission.mission_type,
        "mission_type_label": mission.get_mission_type_display(),
        "destination": mission.destination,
        "purpose": mission.purpose,
        "departure_date": mission.departure_date.isoformat(),
        "return_date": mission.return_date.isoformat(),
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
        "due_date": open_item.due_date.isoformat() if open_item else None,
        "claimed_by": _person(open_item.claimed_by)
        if open_item and open_item.claimed_by
        else None,
        "available_actions": _available_actions(user, case),
    }
    if not detail:
        return payload
    may_download = can_download_documents(user, case)
    payload.update(
        {
            "mission": {
                "itinerary": mission.itinerary,
                "transport_mode": mission.transport_mode,
                "transport_company": mission.transport_company,
                "funding_source": mission.funding_source,
                "costs_covered": mission.costs_covered,
                "vehicle_required": mission.vehicle_required,
                "vehicle_details": mission.vehicle_details,
                "official_number": mission.official_number,
            },
            "participants": [
                {
                    "id": participant.user_id,
                    "name": participant.name_snapshot,
                    "position": participant.position_snapshot,
                    "login_alias": participant.user.login_alias,
                }
                for participant in case.mission_participants.all()
            ],
            "documents": [
                {
                    "id": document.pk,
                    "kind": document.kind,
                    "kind_label": document.get_kind_display(),
                    "name": document.original_name,
                    "content_type": document.content_type,
                    "size": document.size,
                    "sha256": document.sha256,
                    "scan_status": document.scan_status,
                    "active": document.replaced_by_id is None,
                    "replaced_by_id": document.replaced_by_id,
                    "created_at": document.created_at.isoformat(),
                    "download_url": (
                        f"/api/v1/processes/{case.pk}/documents/{document.pk}/content/"
                        if may_download
                        else None
                    ),
                }
                for document in case.documents.all()
            ],
            "events": [
                {
                    "id": event.pk,
                    "kind": event.kind,
                    "from_status": event.from_status,
                    "to_status": event.to_status,
                    "message": event.message,
                    "actor": _person(event.actor),
                    "occurred_at": event.occurred_at.isoformat(),
                }
                for event in case.events.all()
            ],
            "capabilities": {
                "edit": can_edit_mission(user, case),
                "upload": can_upload_document(user, case),
                "download_documents": may_download,
                "export": can_export_case(user, case),
            },
            "signature": (
                {
                    "signer": _person(case.signature.signer),
                    "signed_at": case.signature.signed_at.isoformat(),
                    "snapshot_sha256": case.signature.snapshot_sha256,
                }
                if hasattr(case, "signature")
                else None
            ),
        }
    )
    return payload


class ProcessListView(APIView):
    @extend_schema(
        operation_id="process_case_list",
        parameters=[OpenApiParameter("box", OpenApiTypes.STR, required=False)],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request) -> Response:
        user = _request_user(request)
        box = request.query_params.get("box", "actionable")
        cases = (
            visible_cases(user)
            .select_related("initiator", "origin_unit", "mission_order")
            .prefetch_related("work_items__queue__role", "work_items__claimed_by")
        )
        items = list(cases)
        if box == "mine":
            items = [case for case in items if case.initiator_id == user.pk]
        elif box == "actionable":
            items = [case for case in items if _available_actions(user, case)]
        else:
            raise serializers.ValidationError({"box": "Boîte inconnue."})
        corrections = sum(
            case.events.filter(kind="request_correction").count()
            for case in visible_cases(user).filter(initiator=user)
        )
        return Response(
            {
                "items": [case_payload(user, case, detail=False) for case in items],
                "counters": {"pending": len(items), "correction_returns": corrections},
            }
        )


class MissionOptionsView(APIView):
    @extend_schema(operation_id="mission_options", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = _request_user(request)
        if not may_create_mission(user):
            raise Http404
        people = User.objects.filter(
            is_active=True, organization_memberships__is_primary=True
        ).distinct()
        return Response(
            {
                "participants": [_person(person) for person in people],
                "today": timezone.localdate().isoformat(),
            }
        )


class MissionCreateView(APIView):
    @extend_schema(
        operation_id="mission_create",
        request=MissionSerializer,
        responses={201: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        serializer = MissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        data.pop("official_number", None)
        case = create_mission_draft(actor=_request_user(request), **data)
        case = _case_for_user(_request_user(request), case.pk)
        return Response(
            case_payload(_request_user(request), case, detail=True),
            status=status.HTTP_201_CREATED,
        )


class ProcessDetailView(APIView):
    @extend_schema(operation_id="process_case_detail", responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, pk: int) -> Response:
        user = _request_user(request)
        return Response(case_payload(user, _case_for_user(user, pk), detail=True))

    @extend_schema(
        operation_id="mission_update",
        request=MissionUpdateSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def patch(self, request: Request, pk: int) -> Response:
        user = _request_user(request)
        case = _case_for_user(user, pk)
        serializer = MissionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        revision = int(data.pop("revision"))
        participant_ids = cast(list[int], data.pop("participant_ids"))
        updated = update_mission_draft(
            actor=user,
            case=case,
            expected_revision=revision,
            fields=data,
            participant_ids=participant_ids,
        )
        return Response(case_payload(user, _case_for_user(user, updated.pk), detail=True))


class ProcessActionView(APIView):
    @extend_schema(
        operation_id="process_case_action",
        request=ProcessActionSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request: Request, pk: int) -> Response:
        user = _request_user(request)
        case = _case_for_user(user, pk)
        serializer = ProcessActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        updated = act_on_case(
            actor=user,
            case=case,
            expected_revision=data["revision"],
            action=data["action"],
            note=data.get("note", ""),
            confirmation=data.get("confirmation", ""),
            checklist=data.get("checklist", {}),
        )
        return Response(case_payload(user, _case_for_user(user, updated.pk), detail=True))


class ProcessDocumentUploadView(APIView):
    @extend_schema(
        operation_id="process_document_upload",
        request=DocumentUploadSerializer,
        responses={201: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request, pk: int) -> Response:
        user = _request_user(request)
        case = _case_for_user(user, pk)
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        document = add_document(
            actor=user,
            case=case,
            kind=serializer.validated_data["kind"],
            name=uploaded.name,
            content_type=uploaded.content_type or "application/octet-stream",
            content=uploaded.read(),
            expected_revision=serializer.validated_data["revision"],
        )
        return Response({"id": document.pk}, status=status.HTTP_201_CREATED)


class ProcessDocumentContentView(APIView):
    @extend_schema(
        operation_id="process_document_download", responses=OpenApiTypes.BINARY
    )
    def get(self, request: Request, pk: int, document_pk: int) -> HttpResponse:
        user = _request_user(request)
        case = _case_for_user(user, pk)
        if not can_download_documents(user, case):
            raise Http404
        document = get_object_or_404(ProcessDocument, pk=document_pk, case=case)
        response = HttpResponse(
            document_bytes(document), content_type=document.content_type
        )
        response["Content-Disposition"] = (
            content_disposition_header(True, document.original_name) or "attachment"
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ProcessExportView(APIView):
    @extend_schema(operation_id="process_case_export", responses=OpenApiTypes.BINARY)
    def get(self, request: Request, pk: int) -> HttpResponse:
        user = _request_user(request)
        case = _case_for_user(user, pk)
        if not can_export_case(user, case):
            raise Http404
        response = HttpResponse(export_case_zip(case), content_type="application/zip")
        response["Content-Disposition"] = (
            f'attachment; filename="{case.reference}-audit.zip"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response
