"""Administrative setup for organization and work models."""

from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest
from django.core.exceptions import PermissionDenied
from simple_history.admin import SimpleHistoryAdmin

from accounts.models import User
from work.models import (
    ActionPlan,
    Holiday,
    InstitutionalAction,
    NotificationDelivery,
    OrganizationUnit,
    OrganizationUnitLink,
    OrganizationMembership,
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
from work.services import record_progress, set_primary_supervisor


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
    list_display = (
        "task",
        "employee",
        "manager",
        "organization_unit",
        "status",
        "due_date",
    )
    list_filter = ("status", "organization_unit", "due_date")
    autocomplete_fields = ("employee", "manager", "organization_unit")


@admin.register(TaskProposal)
class TaskProposalAdmin(SimpleHistoryAdmin):
    list_display = ("title", "employee", "organization_unit", "status", "created_at")
    list_filter = ("status", "organization_unit")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(SimpleHistoryAdmin):
    list_display = (
        "user",
        "unit",
        "job_title",
        "is_primary",
        "start_date",
        "end_date",
    )
    list_filter = ("is_primary", "unit")
    search_fields = ("user__email", "user__login_alias", "job_title")
    autocomplete_fields = ("user", "unit")


@admin.register(ProgressEntry)
class ProgressEntryAdmin(SimpleHistoryAdmin):
    list_display = ("assignment", "entry_date", "percentage", "blocked", "author")
    list_filter = ("blocked", "entry_date")

    def save_model(
        self,
        request: HttpRequest,
        obj: ProgressEntry,
        form: ModelForm,
        change: bool,
    ) -> None:
        """Route administrative corrections through the audited domain service."""
        del form, change
        if not isinstance(request.user, User):
            raise PermissionDenied
        saved = record_progress(
            user=request.user,
            assignment=obj.assignment,
            entry_date=obj.entry_date,
            percentage=obj.percentage,
            note=obj.note,
            blocked=obj.blocked,
        )
        obj.pk = saved.pk


@admin.register(OrganizationUnit)
class OrganizationUnitAdmin(admin.ModelAdmin):
    list_display = ("code", "short_name", "long_name", "active")
    list_filter = ("active",)
    search_fields = ("code", "short_name", "long_name")


@admin.register(OrganizationUnitLink)
class OrganizationUnitLinkAdmin(admin.ModelAdmin):
    list_display = ("supervisor_service", "collaborator_service")
    autocomplete_fields = ("supervisor_service", "collaborator_service")


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
