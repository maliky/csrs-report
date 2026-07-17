"""IT-only administration of scoped role delegations."""

from django.contrib import admin
from django.http import HttpRequest
from simple_history.admin import SimpleHistoryAdmin

from access.models import RoleGrant, ScopedRole
from access.services import can_administer_grants


class ITOnlyAdminMixin:
    """Apply the grant authority rule to every admin operation."""

    def _allowed(self, request: HttpRequest) -> bool:
        return can_administer_grants(request.user)  # type: ignore[arg-type]

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


@admin.register(ScopedRole)
class ScopedRoleAdmin(ITOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "active", "group")
    list_filter = ("active",)
    search_fields = ("code", "name")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(RoleGrant)
class RoleGrantAdmin(ITOnlyAdminMixin, SimpleHistoryAdmin):
    list_display = (
        "user",
        "role",
        "unit",
        "scope",
        "valid_from",
        "valid_until",
        "state",
        "revoked_at",
    )
    list_filter = ("role", "scope", "unit")
    search_fields = ("user__email", "user__login_alias", "grant_reason")
    autocomplete_fields = ("user", "role", "unit")
    readonly_fields = ("granted_by", "revoked_by", "created_at")

    @admin.display(description="etat")
    def state(self, obj: RoleGrant) -> str:
        from django.utils import timezone

        now = timezone.now()
        if obj.revoked_at is not None and obj.revoked_at <= now:
            return "revoquee"
        if obj.valid_from > now:
            return "future"
        if obj.valid_until is not None and obj.valid_until <= now:
            return "expiree"
        return "active"

    def save_model(
        self, request: HttpRequest, obj: RoleGrant, form: object, change: bool
    ) -> None:
        del form
        if not change:
            obj.granted_by = request.user  # type: ignore[assignment]
        if obj.revoked_at is not None and obj.revoked_by_id is None:
            obj.revoked_by = request.user  # type: ignore[assignment]
        obj.save()
