"""Administration for institution accounts."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import QuerySet
from django.http import HttpRequest

from accounts.forms import InstitutionUserCreationForm
from accounts.models import User
from accounts.services import send_activation


@admin.register(User)
class InstitutionUserAdmin(UserAdmin):
    add_form = InstitutionUserCreationForm
    model = User
    ordering = ("email",)
    list_display = (
        "login_alias",
        "email",
        "last_name",
        "first_name",
        "position",
        "is_active",
    )
    search_fields = ("login_alias", "email", "first_name", "last_name", "position")
    actions = ("send_activation_links",)
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
                )
            },
        ),
        (
            "Acces",
            {
                "fields": (
                    "is_active",
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
                ),
            },
        ),
    )

    @admin.action(description="Envoyer un lien d'activation")
    def send_activation_links(
        self, request: HttpRequest, queryset: QuerySet[User]
    ) -> None:
        sent = 0
        for user in queryset.filter(is_active=True):
            sent += send_activation(request, user)
        self.message_user(request, f"{sent} lien(s) d'activation envoye(s).")
