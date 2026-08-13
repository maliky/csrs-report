"""Account activation forms."""

from django import forms
from django.contrib.admin.widgets import AdminDateWidget, FilteredSelectMultiple
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserChangeForm
from django.db.models import Q
from django.utils import timezone
from typing import Any, cast

from accounts.models import User
from work.models import OrganizationMembership, OrganizationUnit, ReportingLine
from work.services import organization_state_token, validate_supervisor_unit


class OrganizationFieldsMixin:
    """Expose current dated organization relations as simple admin fields."""

    def initialize_organization_fields(self) -> None:
        """Load current relations without exposing archived choices for new writes."""
        instance = cast(User, self.instance)  # type: ignore[attr-defined]
        current_unit_ids: set[int] = set()
        primary_unit_id: int | None = None
        supervisor_id: int | None = None
        if instance.pk:
            memberships = list(
                OrganizationMembership.objects.filter(
                    user=instance, end_date__isnull=True
                ).order_by("-is_primary", "pk")
            )
            current_unit_ids = {membership.unit_id for membership in memberships}
            primary_unit_id = next(
                (
                    membership.unit_id
                    for membership in memberships
                    if membership.is_primary
                ),
                None,
            )
            supervisor_id = (
                ReportingLine.objects.filter(
                    employee=instance,
                    is_primary=True,
                    end_date__isnull=True,
                )
                .values_list("supervisor_id", flat=True)
                .first()
            )
        selectable_units = OrganizationUnit.objects.filter(
            Q(active=True) | Q(pk__in=current_unit_ids)
        ).order_by("display_order", "long_name")
        self.fields["organization_units"].queryset = selectable_units  # type: ignore[attr-defined]
        self.fields["primary_unit"].queryset = selectable_units  # type: ignore[attr-defined]
        supervisors = User.objects.filter(is_active=True).order_by(
            "last_name", "first_name", "email"
        )
        if instance.pk:
            supervisors = supervisors.exclude(pk=instance.pk)
        self.fields["primary_supervisor"].queryset = supervisors  # type: ignore[attr-defined]
        self.initial.update(  # type: ignore[attr-defined]
            {
                "organization_units": current_unit_ids,
                "primary_unit": primary_unit_id,
                "primary_supervisor": supervisor_id,
                "organization_effective_date": timezone.localdate(),
                "organization_state": (
                    organization_state_token(instance) if instance.pk else ""
                ),
            }
        )

    def clean_organization_fields(self) -> None:
        """Validate one coherent current organization selection."""
        cleaned = self.cleaned_data  # type: ignore[attr-defined]
        units = cleaned.get("organization_units")
        primary = cleaned.get("primary_unit")
        supervisor = cleaned.get("primary_supervisor")
        unit_ids = {unit.pk for unit in units} if units is not None else set()
        if primary is not None and primary.pk not in unit_ids:
            self.add_error(  # type: ignore[attr-defined]
                "primary_unit",
                "L'unite principale doit aussi figurer dans les unites actuelles.",
            )
        instance = cast(User, self.instance)  # type: ignore[attr-defined]
        if supervisor is not None and instance.pk and supervisor.pk == instance.pk:
            self.add_error(  # type: ignore[attr-defined]
                "primary_supervisor",
                "Une personne ne peut pas etre son propre responsable.",
            )
        effective_date = cleaned.get("organization_effective_date")
        if supervisor is not None and primary is not None and effective_date is not None:
            try:
                validate_supervisor_unit(
                    supervisor=supervisor,
                    employee_unit_id=primary.pk,
                    on_day=effective_date,
                    require_membership=True,
                )
            except forms.ValidationError as exc:
                self.add_error(  # type: ignore[attr-defined]
                    "primary_supervisor", exc.messages[0]
                )
        submitted_state = cleaned.get("organization_state")
        if (
            instance.pk
            and submitted_state
            and submitted_state != organization_state_token(instance)
        ):
            raise forms.ValidationError(
                "L'organisation a change depuis l'ouverture du formulaire. Rechargez la page."
            )


class InstitutionUserCreationForm(OrganizationFieldsMixin, forms.ModelForm):
    """Admin form for an institution-managed account."""

    organization_units = forms.ModelMultipleChoiceField(
        label="",
        queryset=OrganizationUnit.objects.none(),
        required=False,
        widget=FilteredSelectMultiple(
            "unités actuelles",
            is_stacked=False,
            attrs={"aria-label": "Unités actuelles"},
        ),
        help_text="Selectionnez toutes les unites actuelles de la personne.",
    )
    primary_unit = forms.ModelChoiceField(
        label="Unite principale",
        queryset=OrganizationUnit.objects.none(),
        required=False,
        help_text="Cette unite est utilisee pour l'equipe, les taches et les permissions.",
    )
    primary_supervisor = forms.ModelChoiceField(
        label="Responsable principal",
        queryset=User.objects.none(),
        required=False,
        help_text="Laissez vide uniquement pour une racine de l'organigramme.",
    )
    organization_effective_date = forms.DateField(
        label="Date d'effet",
        input_formats=("%d/%m/%Y", "%Y-%m-%d"),
        widget=AdminDateWidget(format="%d/%m/%Y"),
        help_text="Les anciennes relations seront cloturees la veille.",
    )
    organization_state = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = User
        fields = (
            "email",
            "login_alias",
            "first_name",
            "last_name",
            "position",
            "phone",
            "agenda_direction",
            "organization_units",
            "primary_unit",
            "primary_supervisor",
            "organization_effective_date",
            "organization_state",
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.initialize_organization_fields()

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        self.clean_organization_fields()
        return cleaned

    def save(self, commit: bool = True) -> User:
        user = cast(User, super().save(commit=False))
        user.set_unusable_password()
        if commit:
            user.save()
        return user


class InstitutionUserChangeForm(OrganizationFieldsMixin, UserChangeForm):
    """Edit identity, technical rights and current organization together."""

    organization_units = forms.ModelMultipleChoiceField(
        label="",
        queryset=OrganizationUnit.objects.none(),
        required=False,
        widget=FilteredSelectMultiple(
            "unités actuelles",
            is_stacked=False,
            attrs={"aria-label": "Unités actuelles"},
        ),
        help_text="Selectionnez toutes les unites actuelles de la personne.",
    )
    primary_unit = forms.ModelChoiceField(
        label="Unite principale",
        queryset=OrganizationUnit.objects.none(),
        required=False,
        help_text="Cette unite est utilisee pour l'equipe, les taches et les permissions.",
    )
    primary_supervisor = forms.ModelChoiceField(
        label="Responsable principal",
        queryset=User.objects.none(),
        required=False,
        help_text="Laissez vide uniquement pour une racine de l'organigramme.",
    )
    organization_effective_date = forms.DateField(
        label="Date d'effet",
        input_formats=("%d/%m/%Y", "%Y-%m-%d"),
        widget=AdminDateWidget(format="%d/%m/%Y"),
        help_text="Les anciennes relations seront cloturees la veille.",
    )
    organization_state = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = User
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.initialize_organization_fields()

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        self.clean_organization_fields()
        return cleaned


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
