"""Administrative setup for organization and work models."""

from django.contrib import admin
from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.models import Model, Q, QuerySet
from django.forms import ModelForm
from django.http import HttpRequest
from django.core.exceptions import PermissionDenied
from simple_history.admin import SimpleHistoryAdmin
from typing import Any, cast

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
from access.services import active_memberships, primary_membership
from work.services import (
    record_progress,
    set_primary_supervisor,
    unit_hierarchy_state_token,
    update_unit_hierarchy,
)


class ITOrganizationAdminMixin:
    """Restrict organization writes and reads to technical administrators."""

    def _allowed(self, request: HttpRequest) -> bool:
        return bool(
            request.user.is_active
            and (request.user.is_superuser or getattr(request.user, "is_it_admin", False))
        )

    def has_module_permission(self, request: HttpRequest) -> bool:
        return self._allowed(request)

    def has_view_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return self._allowed(request)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return self._allowed(request)

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return self._allowed(request)

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


class UnitAutocompleteFilter(admin.SimpleListFilter):
    """Small native autocomplete filter reusable by organization changelists."""

    title = "unite"
    parameter_name = "unit_code"
    template = "admin/unit_autocomplete_filter.html"

    def __init__(
        self,
        request: HttpRequest,
        params: dict[str, str],
        model: type[Model],
        model_admin: admin.ModelAdmin,
    ) -> None:
        super().__init__(request, params, model, model_admin)
        self.unit_options = tuple(OrganizationUnit.objects.order_by("code"))
        self.preserved_parameters = tuple(
            (key, value)
            for key in request.GET
            for value in request.GET.getlist(key)
            if key != self.parameter_name
        )

    def lookups(
        self, request: HttpRequest, model_admin: admin.ModelAdmin
    ) -> tuple[tuple[str, str], ...]:
        del request, model_admin
        return (("autocomplete", "autocomplete"),)

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        del request
        if not self.value():
            return queryset
        return queryset.filter(unit__code__iexact=self.value())


class ActiveUnitFilter(admin.SimpleListFilter):
    """Show active units by default while retaining explicit archive access."""

    title = "etat administratif"
    parameter_name = "unit_state"

    def lookups(
        self, request: HttpRequest, model_admin: admin.ModelAdmin
    ) -> tuple[tuple[str, str], ...]:
        del request, model_admin
        return (
            ("active", "Actives"),
            ("archived", "Archivees"),
            ("all", "Toutes"),
        )

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        del request
        if self.value() == "archived":
            return queryset.filter(active=False)
        if self.value() == "all":
            return queryset
        return queryset.filter(active=True)


class ReportingLineAdminForm(forms.ModelForm):
    """Derive the employee unit for primary hierarchy lines."""

    secondary_unit = forms.ModelChoiceField(
        label="Unite de la ligne secondaire",
        queryset=OrganizationUnit.objects.none(),
        required=False,
        help_text=(
            "L'unite principale est deduite automatiquement. Choisissez ce champ "
            "seulement pour une responsabilite secondaire ambigue."
        ),
    )

    class Meta:
        model = ReportingLine
        exclude = ("unit",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        current_unit_id = self.instance.unit_id if self.instance.pk else None
        cast(
            forms.ModelChoiceField, self.fields["secondary_unit"]
        ).queryset = OrganizationUnit.objects.filter(
            Q(active=True) | Q(pk=current_unit_id)
        ).order_by("display_order", "long_name")
        if self.instance.pk and not self.instance.is_primary:
            self.initial["secondary_unit"] = current_unit_id

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        employee = cleaned.get("employee")
        start_date = cleaned.get("start_date")
        is_primary = bool(cleaned.get("is_primary"))
        selected_unit = cleaned.get("secondary_unit")
        if not isinstance(employee, User) or start_date is None:
            return cleaned
        memberships = (
            active_memberships(start_date).filter(user=employee).select_related("unit")
        )
        if is_primary:
            membership = primary_membership(employee, start_date)
            if membership is None:
                self.add_error(
                    "employee",
                    "Le collaborateur doit d'abord avoir une unite principale a cette date.",
                )
                return cleaned
            self.instance.unit = membership.unit
            return cleaned
        if selected_unit is None:
            units = list(memberships)
            if len(units) != 1:
                self.add_error(
                    "secondary_unit",
                    "Choisissez l'unite de cette responsabilite secondaire.",
                )
                return cleaned
            selected_unit = units[0].unit
        if not memberships.filter(unit=selected_unit).exists():
            self.add_error(
                "secondary_unit",
                "Le collaborateur doit appartenir a l'unite selectionnee.",
            )
            return cleaned
        self.instance.unit = selected_unit
        return cleaned


class OrganizationUnitAdminForm(forms.ModelForm):
    """Edit a unit and both sides of its strict tree relation."""

    parent_unit = forms.ModelChoiceField(
        label="Unite superieure",
        queryset=OrganizationUnit.objects.none(),
        required=False,
    )
    child_units = forms.ModelMultipleChoiceField(
        label="Unites directement rattachees",
        queryset=OrganizationUnit.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("unites", is_stacked=False),
    )
    hierarchy_state = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = OrganizationUnit
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        unit = self.instance
        current_parent_id: int | None = None
        current_child_ids: set[int] = set()
        related_ids: set[int] = set()
        if unit.pk:
            current_parent_id = (
                OrganizationUnitLink.objects.filter(collaborator_service=unit)
                .values_list("supervisor_service_id", flat=True)
                .first()
            )
            current_child_ids = set(
                OrganizationUnitLink.objects.filter(supervisor_service=unit).values_list(
                    "collaborator_service_id", flat=True
                )
            )
            related_ids = current_child_ids | (
                {current_parent_id} if current_parent_id else set()
            )
        selectable = OrganizationUnit.objects.filter(
            Q(active=True) | Q(pk__in=related_ids)
        )
        if unit.pk:
            selectable = selectable.exclude(pk=unit.pk)
        selectable = selectable.order_by("display_order", "long_name")
        cast(forms.ModelChoiceField, self.fields["parent_unit"]).queryset = selectable
        cast(
            forms.ModelMultipleChoiceField, self.fields["child_units"]
        ).queryset = selectable
        self.initial.update(
            {
                "parent_unit": current_parent_id,
                "child_units": current_child_ids,
                "hierarchy_state": (unit_hierarchy_state_token(unit) if unit.pk else ""),
            }
        )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        parent = cleaned.get("parent_unit")
        children = cleaned.get("child_units")
        if parent is not None and children is not None and parent in children:
            self.add_error(
                "child_units",
                "L'unite superieure ne peut pas etre aussi une unite rattachee.",
            )
        if self.instance.pk:
            submitted_state = cleaned.get("hierarchy_state")
            if submitted_state and submitted_state != unit_hierarchy_state_token(
                self.instance
            ):
                raise forms.ValidationError(
                    "La hierarchie a change depuis l'ouverture du formulaire. Rechargez la page."
                )
        return cleaned


@admin.register(ReportingLine)
class ReportingLineAdmin(ITOrganizationAdminMixin, SimpleHistoryAdmin):
    form = ReportingLineAdminForm
    list_display = (
        "employee",
        "supervisor",
        "unit",
        "is_primary",
        "start_date",
        "end_date",
    )
    list_filter = ("is_primary", UnitAutocompleteFilter)
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
                actor=request.user if isinstance(request.user, User) else None,
                require_supervisor_membership=True,
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
class OrganizationMembershipAdmin(ITOrganizationAdminMixin, SimpleHistoryAdmin):
    list_display = (
        "user",
        "unit",
        "job_title",
        "is_primary",
        "start_date",
        "end_date",
    )
    list_filter = ("is_primary", UnitAutocompleteFilter)
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
class OrganizationUnitAdmin(ITOrganizationAdminMixin, SimpleHistoryAdmin):
    form = OrganizationUnitAdminForm
    list_display = (
        "code",
        "short_name",
        "long_name",
        "parent_code",
        "direct_child_count",
        "active",
    )
    list_filter = (ActiveUnitFilter,)
    search_fields = ("code", "short_name", "long_name")

    @admin.display(description="unite superieure")
    def parent_code(self, obj: OrganizationUnit) -> str:
        link = obj.supervisor_links.select_related("supervisor_service").first()
        return link.supervisor_service.code if link is not None else "—"

    @admin.display(description="unites rattachees")
    def direct_child_count(self, obj: OrganizationUnit) -> int:
        return obj.collaborator_links.count()

    def save_model(
        self,
        request: HttpRequest,
        obj: OrganizationUnit,
        form: OrganizationUnitAdminForm,
        change: bool,
    ) -> None:
        super().save_model(request, obj, form, change)
        hierarchy_fields = {"parent_unit", "child_units"}
        if change and not hierarchy_fields.intersection(form.changed_data):
            return
        if not isinstance(request.user, User):
            raise PermissionDenied
        parent = form.cleaned_data["parent_unit"]
        children = form.cleaned_data["child_units"]
        update_unit_hierarchy(
            actor=request.user,
            unit=obj,
            parent_id=parent.pk if parent is not None else None,
            child_ids={child.pk for child in children},
            expected_token=form.cleaned_data.get("hierarchy_state") or None,
        )


@admin.register(OrganizationUnitLink)
class OrganizationUnitLinkAdmin(ITOrganizationAdminMixin, SimpleHistoryAdmin):
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
