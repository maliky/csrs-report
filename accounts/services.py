"""Audited account-management and activation services."""

from datetime import date
from hashlib import sha256
import secrets

from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.http import HttpRequest
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import User


class StaleUserStateError(Exception):
    """Raised when an account form was based on an obsolete state."""


def can_manage_users(user: User) -> bool:
    """Restrict routine account management to active IT administrators."""
    return bool(user.is_active and (user.is_it_admin or user.is_superuser))


def ensure_can_manage_users(actor: User, target: User | None = None) -> None:
    """Enforce account-management and superuser boundaries server-side."""
    if not can_manage_users(actor):
        raise PermissionDenied("Seul un administrateur IT peut gerer les comptes.")
    if target is not None and target.is_superuser and not actor.is_superuser:
        raise PermissionDenied(
            "Seul un superutilisateur peut modifier un autre superutilisateur."
        )


def user_management_state_token(user: User) -> str:
    """Hash editable identity and organization state for optimistic writes."""
    from work.services import organization_state_token

    payload = (
        str(user.pk),
        user.email,
        user.login_alias or "",
        user.first_name,
        user.last_name,
        user.position,
        user.phone,
        user.agenda_direction,
        str(int(user.include_in_direction_agendas)),
        str(int(user.is_active)),
        str(int(user.password_change_required)),
        organization_state_token(user),
    )
    return sha256("|".join(payload).encode()).hexdigest()


def _attribute_history(user: User, actor: User, reason: str) -> None:
    """Attribute the next simple-history row without exposing credentials."""
    user._history_user = actor  # type: ignore[attr-defined]
    user._change_reason = reason[:100]  # type: ignore[attr-defined]


def _assign_identity(
    user: User,
    *,
    email: str,
    login_alias: str | None,
    first_name: str,
    last_name: str,
    position: str,
    phone: str,
    agenda_direction: str,
    include_in_direction_agendas: bool,
) -> None:
    """Apply the routine profile fields exposed by the React administration."""
    user.email = User.objects.normalize_email(email)
    user.login_alias = login_alias or None
    user.first_name = first_name.strip()
    user.last_name = last_name.strip()
    user.position = position.strip()
    user.phone = phone.strip()
    user.agenda_direction = agenda_direction
    user.include_in_direction_agendas = include_in_direction_agendas


@transaction.atomic
def create_managed_user(
    *,
    actor: User,
    email: str,
    login_alias: str | None,
    first_name: str,
    last_name: str,
    position: str,
    phone: str,
    agenda_direction: str,
    include_in_direction_agendas: bool,
    unit_ids: set[int],
    primary_unit_id: int | None,
    primary_supervisor_id: int | None,
    organization_effective_date: date,
) -> User:
    """Create an unusable-password account and its current organization."""
    from work.services import update_user_organization

    ensure_can_manage_users(actor)
    user = User()
    _assign_identity(
        user,
        email=email,
        login_alias=login_alias,
        first_name=first_name,
        last_name=last_name,
        position=position,
        phone=phone,
        agenda_direction=agenda_direction,
        include_in_direction_agendas=include_in_direction_agendas,
    )
    user.set_unusable_password()
    _attribute_history(user, actor, "Creation du compte depuis l'administration React")
    user.full_clean()
    user.save()
    update_user_organization(
        actor=actor,
        user=user,
        unit_ids=unit_ids,
        primary_unit_id=primary_unit_id,
        supervisor_id=primary_supervisor_id,
        effective_date=organization_effective_date,
        expected_token=None,
    )
    return user


@transaction.atomic
def update_managed_user(
    *,
    actor: User,
    user: User,
    expected_token: str,
    email: str,
    login_alias: str | None,
    first_name: str,
    last_name: str,
    position: str,
    phone: str,
    agenda_direction: str,
    include_in_direction_agendas: bool,
    unit_ids: set[int],
    primary_unit_id: int | None,
    primary_supervisor_id: int | None,
    organization_effective_date: date,
) -> User:
    """Update identity and dated organization as one optimistic transaction."""
    from work.services import organization_state_token, update_user_organization

    ensure_can_manage_users(actor, user)
    locked = User.objects.select_for_update().get(pk=user.pk)
    ensure_can_manage_users(actor, locked)
    if user_management_state_token(locked) != expected_token:
        raise StaleUserStateError(
            "Ce compte a change depuis l'ouverture de la fiche. Rechargez la page."
        )
    organization_token = organization_state_token(locked)
    _assign_identity(
        locked,
        email=email,
        login_alias=login_alias,
        first_name=first_name,
        last_name=last_name,
        position=position,
        phone=phone,
        agenda_direction=agenda_direction,
        include_in_direction_agendas=include_in_direction_agendas,
    )
    _attribute_history(
        locked, actor, "Modification du compte depuis l'administration React"
    )
    locked.full_clean()
    locked.save(
        update_fields=[
            "email",
            "login_alias",
            "first_name",
            "last_name",
            "position",
            "phone",
            "agenda_direction",
            "include_in_direction_agendas",
        ]
    )
    update_user_organization(
        actor=actor,
        user=locked,
        unit_ids=unit_ids,
        primary_unit_id=primary_unit_id,
        supervisor_id=primary_supervisor_id,
        effective_date=organization_effective_date,
        expected_token=organization_token,
    )
    return locked


@transaction.atomic
def set_managed_user_active(
    *, actor: User, user: User, active: bool, expected_token: str
) -> User:
    """Deactivate or reactivate a user without deleting audited relations."""
    ensure_can_manage_users(actor, user)
    locked = User.objects.select_for_update().get(pk=user.pk)
    ensure_can_manage_users(actor, locked)
    if locked.pk == actor.pk and not active:
        raise ValidationError("Vous ne pouvez pas desactiver votre propre compte.")
    if user_management_state_token(locked) != expected_token:
        raise StaleUserStateError(
            "Ce compte a change depuis l'ouverture de la fiche. Rechargez la page."
        )
    if locked.is_active == active:
        return locked
    locked.is_active = active
    _attribute_history(
        locked,
        actor,
        "Reactivation du compte" if active else "Desactivation du compte",
    )
    locked.save(update_fields=["is_active"])
    return locked


def _temporary_password(user: User) -> str:
    """Generate a validator-compliant password with unambiguous characters."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(18))
        if not (
            any(character.isupper() for character in candidate)
            and any(character.islower() for character in candidate)
            and any(character.isdigit() for character in candidate)
        ):
            continue
        try:
            password_validation.validate_password(candidate, user)
        except ValidationError:
            continue
        return candidate


@transaction.atomic
def reset_managed_user_password(
    *, actor: User, user: User, expected_token: str
) -> tuple[User, str]:
    """Replace a password and return its temporary plaintext exactly once."""
    ensure_can_manage_users(actor, user)
    locked = User.objects.select_for_update().get(pk=user.pk)
    ensure_can_manage_users(actor, locked)
    if locked.pk == actor.pk:
        raise ValidationError(
            "Utilisez votre propre ecran de changement de mot de passe."
        )
    if not locked.is_active:
        raise ValidationError("Reactivez ce compte avant de reinitialiser son acces.")
    if user_management_state_token(locked) != expected_token:
        raise StaleUserStateError(
            "Ce compte a change depuis l'ouverture de la fiche. Rechargez la page."
        )
    temporary_password = _temporary_password(locked)
    locked.set_password(temporary_password)
    locked.password_change_required = True
    _attribute_history(locked, actor, "Generation d'un mot de passe temporaire")
    locked.save(update_fields=["password", "password_change_required"])
    return locked, temporary_password


@transaction.atomic
def complete_temporary_password_change(
    *, user: User, current_password: str, new_password: str
) -> User:
    """Replace a temporary password and clear the mandatory-change marker."""
    locked = User.objects.select_for_update().get(pk=user.pk)
    if not locked.password_change_required:
        raise ValidationError("Aucun changement de mot de passe n'est requis.")
    if not locked.check_password(current_password):
        raise ValidationError(
            {"current_password": "Le mot de passe actuel est incorrect."}
        )
    password_validation.validate_password(new_password, locked)
    locked.set_password(new_password)
    locked.password_change_required = False
    _attribute_history(locked, locked, "Remplacement du mot de passe temporaire")
    locked.save(update_fields=["password", "password_change_required"])
    return locked


def activation_url(request: HttpRequest, user: User) -> str:
    """Build a one-time account activation URL."""
    path = reverse(
        "activate",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    return request.build_absolute_uri(path)


def send_activation(request: HttpRequest, user: User) -> int:
    """Send an activation link without logging its token."""
    url = activation_url(request, user)
    return send_mail(
        "Activation de votre compte CSRS Report",
        (
            f"Bonjour {user.get_full_name() or user.email},\n\n"
            "Le service IT a cree votre compte CSRS Report. "
            f"Choisissez votre mot de passe avec ce lien :\n{url}\n\n"
            "Si vous n'attendiez pas ce message, contactez le service IT."
        ),
        None,
        [user.email],
        fail_silently=False,
    )
