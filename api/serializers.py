from __future__ import annotations

from decimal import Decimal
from typing import cast

from rest_framework import serializers

from accounts.models import AgendaDirection


class ScheduleSerializer(serializers.Serializer):
    """Shared, server-validated assignment schedule."""

    start_date = serializers.DateField()
    due_date = serializers.DateField()
    estimated_work_days = serializers.DecimalField(
        max_digits=7, decimal_places=1, min_value=Decimal("0.1")
    )


class TaskCreateSerializer(ScheduleSerializer):
    title = serializers.CharField(max_length=180)
    description = serializers.CharField()
    employee_id = serializers.IntegerField(min_value=1)
    action_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    calendar_id = serializers.IntegerField(min_value=1, required=False)


class TaskUpdateSerializer(ScheduleSerializer):
    revision = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=180)
    description = serializers.CharField()
    action_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class TaskManagementQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=(
            "planned",
            "active",
            "awaiting_validation",
            "completed",
            "closed_early",
        ),
        required=False,
        allow_blank=True,
        default="",
    )
    employee_id = serializers.IntegerField(min_value=1, required=False)
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=100, required=False, default=50
    )


class TaskSelectionSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    revision = serializers.IntegerField(min_value=1)


class TaskBulkDeleteSerializer(serializers.Serializer):
    assignments = TaskSelectionSerializer(many=True, allow_empty=False, max_length=100)
    reason = serializers.CharField(min_length=3, max_length=500, trim_whitespace=True)
    confirmation = serializers.ChoiceField(choices=("SUPPRIMER",))

    def validate_assignments(self, value: list[dict[str, int]]) -> list[dict[str, int]]:
        ids = [item["id"] for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Une tache ne peut apparaitre qu'une fois.")
        return value


class ProgressSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    entry_date = serializers.DateField()
    percentage = serializers.IntegerField(min_value=0, max_value=100)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    blocked = serializers.BooleanField(required=False, default=False)


class ObservationSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    message = serializers.CharField()


class TransitionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    transition = serializers.ChoiceField(choices=("validate", "reject", "close_early"))
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class ProposalCreateSerializer(ScheduleSerializer):
    title = serializers.CharField(max_length=180)
    description = serializers.CharField()
    action_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    calendar_id = serializers.IntegerField(min_value=1, required=False)


class ProposalUpdateSerializer(ProposalCreateSerializer):
    revision = serializers.IntegerField(min_value=1)


class ProposalResubmitSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)


class ProposalDecisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    decision = serializers.ChoiceField(choices=("accept", "reject"))
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class PlanningPreviewSerializer(serializers.Serializer):
    calendar_id = serializers.IntegerField(min_value=1)
    start_date = serializers.DateField()
    source = serializers.ChoiceField(choices=("workload", "due"))
    due_date = serializers.DateField(required=False)
    estimated_work_days = serializers.DecimalField(
        max_digits=7, decimal_places=1, min_value=Decimal("0.1"), required=False
    )

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Require the field that is authoritative for the requested preview."""
        source = attrs["source"]
        required = "estimated_work_days" if source == "workload" else "due_date"
        if required not in attrs:
            raise serializers.ValidationError({required: "Ce champ est obligatoire."})
        return attrs


class JsonEnvelopeSerializer(serializers.Serializer):
    """OpenAPI description for rich, presenter-built JSON resources."""

    data = serializers.JSONField()


class UserManagementQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    state = serializers.ChoiceField(
        choices=("active", "inactive"), required=False, allow_blank=True, default=""
    )
    unit_id = serializers.IntegerField(min_value=1, required=False)
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=100, required=False, default=50
    )


class UserSelectionSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    state_token = serializers.CharField(allow_blank=False)


class UserBulkActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("deactivate", "delete"))
    users = UserSelectionSerializer(many=True, allow_empty=False, max_length=100)
    reason = serializers.CharField(
        min_length=3,
        max_length=75,
        trim_whitespace=True,
        required=False,
        allow_blank=True,
        default="",
    )
    confirmation = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_users(
        self, value: list[dict[str, int | str]]
    ) -> list[dict[str, int | str]]:
        ids = [int(item["id"]) for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Un compte ne peut apparaître qu'une fois.")
        return value

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["action"] == "delete":
            if len(str(attrs.get("reason", "")).strip()) < 3:
                raise serializers.ValidationError(
                    {"reason": "Le motif de suppression est obligatoire."}
                )
            if attrs.get("confirmation") != "SUPPRIMER":
                raise serializers.ValidationError(
                    {"confirmation": "Saisissez exactement SUPPRIMER."}
                )
        return attrs


class UserWriteSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    login_alias = serializers.RegexField(
        r"^[a-z][a-z0-9_-]*$",
        max_length=32,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    position = serializers.CharField(max_length=160, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    agenda_direction = serializers.ChoiceField(
        choices=("", *AgendaDirection.values), required=False, allow_blank=True
    )
    include_in_direction_agendas = serializers.BooleanField(required=False, default=True)
    unit_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    primary_unit_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, default=None
    )
    primary_supervisor_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, default=None
    )
    organization_effective_date = serializers.DateField()
    state_token = serializers.CharField(required=False, allow_blank=False)

    def validate_unit_ids(self, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Une unite ne peut apparaitre qu'une fois.")
        return value

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        unit_ids = set(cast(list[int], attrs.get("unit_ids", [])))
        primary_unit_id = attrs.get("primary_unit_id")
        if primary_unit_id is not None and primary_unit_id not in unit_ids:
            raise serializers.ValidationError(
                {"primary_unit_id": "L'unite principale doit etre selectionnee."}
            )
        if attrs.get("primary_supervisor_id") is not None and primary_unit_id is None:
            raise serializers.ValidationError(
                {"primary_supervisor_id": "Choisissez d'abord une unite principale."}
            )
        return attrs


class UserUpdateSerializer(UserWriteSerializer):
    state_token = serializers.CharField(allow_blank=False)


class MeProfileSerializer(serializers.Serializer):
    terms_of_reference = serializers.CharField(required=False, allow_blank=True)


class StateTokenSerializer(serializers.Serializer):
    state_token = serializers.CharField(allow_blank=False)


class TemporaryPasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)
    new_password_confirmation = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["new_password"] != attrs["new_password_confirmation"]:
            raise serializers.ValidationError(
                {"new_password_confirmation": "Les deux mots de passe sont differents."}
            )
        return attrs


class CollaboratorReplacementSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField(min_value=1)
    supervisor_id = serializers.IntegerField(min_value=1)


class CollaboratorUpdateSerializer(serializers.Serializer):
    collaborator_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True
    )
    replacements = CollaboratorReplacementSerializer(many=True, required=False)
    effective_date = serializers.DateField()
    state_token = serializers.CharField(allow_blank=False)

    def validate_collaborator_ids(self, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise serializers.ValidationError(
                "Un collaborateur ne peut apparaitre qu'une fois."
            )
        return value

    def validate_replacements(self, value: list[dict[str, int]]) -> list[dict[str, int]]:
        employee_ids = [item["employee_id"] for item in value]
        if len(employee_ids) != len(set(employee_ids)):
            raise serializers.ValidationError(
                "Un collaborateur ne peut avoir qu'un nouveau responsable."
            )
        return value
