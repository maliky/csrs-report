"""Administrative configuration for workflow definitions and service queues."""

from django.contrib import admin
from django.http import HttpRequest

from processes.models import (
    MissionOrder,
    MissionParticipant,
    ProcessCase,
    ProcessDefinition,
    ProcessDocument,
    ProcessEvent,
    ProcessQueue,
    ProcessSignature,
    ProcessWorkItem,
)


@admin.register(ProcessDefinition)
class ProcessDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "version", "name", "active")
    list_filter = ("active",)


@admin.register(ProcessQueue)
class ProcessQueueAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "definition",
        "kind",
        "role",
        "handler_unit",
        "coverage_unit",
        "coverage_scope",
        "active",
    )
    list_filter = ("definition", "kind", "role", "active")
    autocomplete_fields = ("role", "handler_unit", "coverage_unit")


class ReadOnlyWorkflowAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(ProcessCase)
class ProcessCaseAdmin(ReadOnlyWorkflowAdmin):
    list_display = ("reference", "definition", "initiator", "status", "revision")
    list_filter = ("definition", "status", "legal_hold")
    search_fields = ("reference", "initiator__email", "origin_unit_name")


for model in (
    MissionOrder,
    MissionParticipant,
    ProcessDocument,
    ProcessEvent,
    ProcessSignature,
    ProcessWorkItem,
):
    admin.site.register(model, ReadOnlyWorkflowAdmin)
