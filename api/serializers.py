from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


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
