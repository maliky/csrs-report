from django.contrib import admin

from agenda.models import (
    StaffAvailability,
    VisitorVisit,
    WeeklyAgendaDraft,
    WeeklyAgendaVersion,
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


@admin.register(WeeklyAgendaDraft)
class WeeklyAgendaDraftAdmin(admin.ModelAdmin):
    list_display = ("week_start", "revision", "updated_by", "updated_at")
    readonly_fields = ("revision", "created_at", "updated_at")


@admin.register(WeeklyAgendaVersion)
class WeeklyAgendaVersionAdmin(admin.ModelAdmin):
    list_display = ("week_start", "version", "generated_by", "generated_at")
    readonly_fields = (
        "draft",
        "week_start",
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
