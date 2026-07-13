"""Administrative setup for organization and work models."""

from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest
from simple_history.admin import SimpleHistoryAdmin

from work.models import (
    ActionPlan,
    Holiday,
    InstitutionalAction,
    NotificationDelivery,
    OrganizationUnit,
    ProgressEntry,
    ReportingLine,
    StrategicPlan,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskProposal,
    WorkCalendar,
    WorkCalendarDay,
)
from work.services import set_primary_supervisor


@admin.register(ReportingLine)
class ReportingLineAdmin(SimpleHistoryAdmin):
    list_display = (
        "employee",
        "supervisor",
        "unit",
        "is_primary",
        "start_date",
        "end_date",
    )
    list_filter = ("is_primary", "unit")
    autocomplete_fields = ("employee", "supervisor")

    def save_model(
        self,
        request: HttpRequest,
        obj: ReportingLine,
        form: ModelForm,
        change: bool,
    ) -> None:
        if obj.is_primary and obj.end_date is None and not change:
            saved = set_primary_supervisor(
                employee=obj.employee,
                supervisor=obj.supervisor,
                unit_id=obj.unit_id,
                start_date=obj.start_date,
            )
            obj.pk = saved.pk
            return
        super().save_model(request, obj, form, change)


@admin.register(Task)
class TaskAdmin(SimpleHistoryAdmin):
    list_display = ("code", "title", "created_by", "updated_at")
    search_fields = ("code", "title", "description")


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(SimpleHistoryAdmin):
    list_display = ("task", "employee", "manager", "status", "due_date")
    list_filter = ("status", "due_date")
    autocomplete_fields = ("employee", "manager")


@admin.register(TaskProposal)
class TaskProposalAdmin(SimpleHistoryAdmin):
    list_display = ("title", "employee", "status", "created_at")
    list_filter = ("status",)


@admin.register(ProgressEntry)
class ProgressEntryAdmin(SimpleHistoryAdmin):
    list_display = ("assignment", "entry_date", "percentage", "blocked", "author")
    list_filter = ("blocked", "entry_date")


admin.site.register(OrganizationUnit)
admin.site.register(StrategicPlan)
admin.site.register(ActionPlan)
admin.site.register(InstitutionalAction)
admin.site.register(Holiday)


@admin.register(WorkCalendar)
class WorkCalendarAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "is_default", "active", "created_at")
    list_filter = ("is_default", "active")

    def get_readonly_fields(
        self, request: HttpRequest, obj: WorkCalendar | None = None
    ) -> tuple[str, ...]:
        if obj is not None and obj.assignments.exists():
            return ("name", "version", "is_default", "active")
        return ()

    def save_model(
        self,
        request: HttpRequest,
        obj: WorkCalendar,
        form: ModelForm,
        change: bool,
    ) -> None:
        if obj.is_default:
            WorkCalendar.objects.exclude(pk=obj.pk).update(is_default=False)
        super().save_model(request, obj, form, change)


@admin.register(WorkCalendarDay)
class WorkCalendarDayAdmin(admin.ModelAdmin):
    list_display = ("day", "name", "is_working_day", "calendar")
    list_filter = ("calendar", "is_working_day")


@admin.register(TaskActivity)
class TaskActivityAdmin(admin.ModelAdmin):
    list_display = ("assignment", "kind", "actor", "occurred_at")
    list_filter = ("kind", "occurred_at")
    readonly_fields = (
        "assignment",
        "kind",
        "actor",
        "occurred_at",
        "message",
        "percentage_before",
        "percentage_after",
        "progress_entry",
        "details",
        "supersedes",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: TaskActivity | None = None
    ) -> bool:
        return False


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("event_type", "status", "attempts", "created_at", "sent_at")
    list_filter = ("status", "event_type")
    readonly_fields = (
        "recipient",
        "event_type",
        "subject",
        "body",
        "status",
        "attempts",
        "next_attempt_at",
        "sent_at",
        "last_error_type",
        "created_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: NotificationDelivery | None = None
    ) -> bool:
        return False
