"""Account activation forms."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from typing import cast

from accounts.models import User


class InstitutionUserCreationForm(forms.ModelForm):
    """Admin form for an institution-managed account."""

    class Meta:
        model = User
        fields = (
            "email",
            "login_alias",
            "first_name",
            "last_name",
            "position",
            "phone",
        )

    def save(self, commit: bool = True) -> User:
        user = cast(User, super().save(commit=False))
        user.set_unusable_password()
        if commit:
            user.save()
        return user


class ActivationForm(SetPasswordForm):
    """Let a pre-created user choose an initial password."""


class AliasAuthenticationForm(AuthenticationForm):
    """Label the credential field according to both accepted identifiers."""

    username = forms.CharField(label="Email ou identifiant", max_length=254)
    password = forms.CharField(
        label="mot de passe",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
