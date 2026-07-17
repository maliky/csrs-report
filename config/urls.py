"""Root URL configuration."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.forms import AliasAuthenticationForm

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.urls")),
    path(
        "connexion/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=AliasAuthenticationForm,
        ),
        name="login",
    ),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("comptes/", include("accounts.urls")),
    path("", include("work.urls")),
]
