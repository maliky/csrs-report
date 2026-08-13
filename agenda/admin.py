from django.contrib import admin

from agenda.models import (
    AgendaDraft,
    AgendaVersion,
    StaffAvailability,
    VisitorVisit,
)


@admin.register(VisitorVisit)
class VisitorVisitAdmin(admin.ModelAdmin):
    list_display = ("arrived_at", "departed_at", "party_size", "recorded_by")
    readonly_fields = ("revision", "created_at", "updated_at")


@admin.register(StaffAvailability)
class StaffAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("employee", "kind", "start_date", "end_date", "recorded_by")
    list_filter = ("kind",)
    readonly_fields = ("revision", "created_at", "updated_at")


@admin.register(AgendaDraft)
class AgendaDraftAdmin(admin.ModelAdmin):
    list_display = (
        "period_start",
        "period_end",
        "revision",
        "updated_by",
        "updated_at",
    )
    readonly_fields = ("revision", "created_at", "updated_at")


@admin.register(AgendaVersion)
class AgendaVersionAdmin(admin.ModelAdmin):
    list_display = (
        "period_start",
        "period_end",
        "agenda_direction",
        "version",
        "generated_by",
        "generated_at",
    )
    list_filter = ("agenda_direction",)
    readonly_fields = (
        "draft",
        "period_start",
        "period_end",
        "agenda_direction",
        "version",
        "snapshot",
        "snapshot_sha256",
        "storage_provider",
        "storage_key",
        "pdf_sha256",
        "pdf_size",
        "generated_by",
        "generated_at",
    )

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object | None = None) -> bool:
        return False
