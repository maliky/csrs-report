"""Administration for institution accounts."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest
from simple_history.admin import SimpleHistoryAdmin

from accounts.forms import InstitutionUserChangeForm, InstitutionUserCreationForm
from accounts.models import User
from accounts.services import send_activation
from work.services import update_user_organization


@admin.register(User)
class InstitutionUserAdmin(UserAdmin, SimpleHistoryAdmin):
    add_form = InstitutionUserCreationForm
    form = InstitutionUserChangeForm
    model = User
    ordering = ("email",)
    list_display = (
        "login_alias",
        "email",
        "last_name",
        "first_name",
        "position",
        "agenda_direction",
        "include_in_direction_agendas",
        "is_active",
    )
    list_filter = (
        "agenda_direction",
        "include_in_direction_agendas",
        "is_active",
        "is_staff",
    )
    search_fields = ("login_alias", "email", "first_name", "last_name", "position")
    actions = ("send_activation_links",)
    readonly_fields = ("password_change_required",)
    fieldsets = (
        (None, {"fields": ("email", "login_alias", "password")}),
        (
            "Identite",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "position",
                    "phone",
                    "phone_verified_at",
                    "agenda_direction",
                    "include_in_direction_agendas",
                )
            },
        ),
        (
            "Organisation actuelle",
            {
                "fields": (
                    "organization_units",
                    "primary_unit",
                    "primary_supervisor",
                    "organization_effective_date",
                    "organization_state",
                ),
                "description": (
                    "Ces champs modifient les appartenances et le responsable dates; "
                    "les anciennes relations restent dans l'historique."
                ),
            },
        ),
        (
            "Acces",
            {
                "fields": (
                    "is_active",
                    "password_change_required",
                    "is_staff",
                    "is_it_admin",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "login_alias",
                    "first_name",
                    "last_name",
                    "position",
                    "phone",
                    "agenda_direction",
                    "include_in_direction_agendas",
                    "organization_units",
                    "primary_unit",
                    "primary_supervisor",
                    "organization_effective_date",
                    "organization_state",
                ),
            },
        ),
    )

    class Media:
        css = {"all": ("accounts/admin_organization.css",)}

    def _is_it(self, request: HttpRequest) -> bool:
        return bool(
            request.user.is_active
            and (request.user.is_superuser or getattr(request.user, "is_it_admin", False))
        )

    def has_module_permission(self, request: HttpRequest) -> bool:
        return self._is_it(request)

    def has_view_permission(self, request: HttpRequest, obj: User | None = None) -> bool:
        return self._is_it(request)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return self._is_it(request)

    def has_change_permission(
        self, request: HttpRequest, obj: User | None = None
    ) -> bool:
        return self._is_it(request)

    def has_delete_permission(
        self, request: HttpRequest, obj: User | None = None
    ) -> bool:
        return False

    def save_related(
        self,
        request: HttpRequest,
        form: InstitutionUserChangeForm | InstitutionUserCreationForm,
        formsets: list[object],
        change: bool,
    ) -> None:
        super().save_related(request, form, formsets, change)
        organization_fields = {
            "organization_units",
            "primary_unit",
            "primary_supervisor",
            "organization_effective_date",
        }
        if change and not organization_fields.intersection(form.changed_data):
            return
        if not isinstance(request.user, User):
            raise PermissionDenied
        units = form.cleaned_data["organization_units"]
        primary = form.cleaned_data["primary_unit"]
        supervisor = form.cleaned_data["primary_supervisor"]
        update_user_organization(
            actor=request.user,
            user=form.instance,
            unit_ids={unit.pk for unit in units},
            primary_unit_id=primary.pk if primary is not None else None,
            supervisor_id=supervisor.pk if supervisor is not None else None,
            effective_date=form.cleaned_data["organization_effective_date"],
            expected_token=form.cleaned_data.get("organization_state") or None,
        )

    @admin.action(description="Envoyer un lien d'activation")
    def send_activation_links(
        self, request: HttpRequest, queryset: QuerySet[User]
    ) -> None:
        sent = 0
        for user in queryset.filter(is_active=True):
            sent += send_activation(request, user)
        self.message_user(request, f"{sent} lien(s) d'activation envoye(s).")
