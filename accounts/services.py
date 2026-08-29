"""Audited account-management and activation services."""

from collections.abc import Sequence
from datetime import date
from hashlib import sha256
import secrets
from typing import cast

from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.http import HttpRequest
from django.db import DEFAULT_DB_ALIAS, transaction
from django.db.models import Model
from django.db.models.deletion import Collector, ProtectedError, RestrictedError
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import User


class StaleUserStateError(Exception):
    """Raised when an account form was based on an obsolete state."""


USER_BULK_ACTIONS = frozenset({"deactivate", "delete"})


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


def update_terms_of_reference(user: User, actor: User, terms_of_reference: str) -> User:
    """Store a user's own terms of reference and track it in history."""
    user.terms_of_reference = terms_of_reference.strip()
    _attribute_history(
        user,
        actor=actor,
        reason="Mise à jour du cahier des charges par l'utilisateur",
    )
    user.save(update_fields=["terms_of_reference"])
    return user


def update_own_profile(
    user: User,
    actor: User,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    avatar: str | None = None,
    terms_of_reference: str | None = None,
) -> User:
    """Store editable identity details and the user's own TOR."""
    changed_fields: list[str] = []
    if first_name is not None:
        user.first_name = first_name.strip()
        changed_fields.append("first_name")
    if last_name is not None:
        user.last_name = last_name.strip()
        changed_fields.append("last_name")
    if phone is not None:
        user.phone = phone.strip()
        changed_fields.append("phone")
    if avatar is not None:
        user.avatar = avatar.strip()
        changed_fields.append("avatar")
    if terms_of_reference is not None:
        user.terms_of_reference = terms_of_reference.strip()
        changed_fields.append("terms_of_reference")
    if not changed_fields:
        return user
    _attribute_history(
        user,
        actor=actor,
        reason="Mise à jour du profil personnel",
    )
    user.save(update_fields=changed_fields)
    return user


def _attribute_history(user: User, actor: User, reason: str) -> None:
    """Attribute the next simple-history row without exposing credentials."""
    user._history_user = actor  # type: ignore[attr-defined]
    user._change_reason = reason[:100]  # type: ignore[attr-defined]


def managed_user_deletion_blockers(user: User) -> tuple[str, ...]:
    """Describe why an inactive account is not an orphan safe to delete."""
    blockers: list[str] = []
    if user.is_active:
        blockers.append("le compte est encore actif")
    if user.is_staff or user.is_superuser or user.is_it_admin:
        blockers.append("le compte possède encore des droits techniques")
    if user.groups.exists() or user.user_permissions.exists():
        blockers.append("le compte possède encore des groupes ou permissions")

    database = user._state.db or DEFAULT_DB_ALIAS
    relation_labels: set[str] = set()
    for relation in user._meta.related_objects:
        related_model = cast(type[Model], relation.related_model)
        if (
            related_model._base_manager.using(database)
            .filter(**{relation.field.name: user.pk})
            .exists()
        ):
            relation_labels.add(str(related_model._meta.verbose_name_plural))
    if relation_labels:
        blockers.append("le compte est lié à " + ", ".join(sorted(relation_labels)))

    if not relation_labels:
        collector = Collector(using=database, origin=user)
        try:
            collector.collect([user])
        except (ProtectedError, RestrictedError):
            blockers.append("le compte est lié à des données protégées")
        else:
            collected_relations = any(
                model is not User and bool(objects)
                for model, objects in collector.data.items()
            )
            fast_relations = any(queryset.exists() for queryset in collector.fast_deletes)
            updated_relations = any(
                batch.exists() if hasattr(batch, "exists") else bool(batch)
                for batches in collector.field_updates.values()
                for batch in batches
            )
            if collected_relations or fast_relations or updated_relations:
                blockers.append("le compte est lié à d'autres données persistantes")
    return tuple(blockers)


def _deactivate_locked_users(*, actor: User, users: Sequence[User]) -> int:
    """Deactivate one already locked and state-checked selection."""
    invalid = [
        user.login_alias or user.email
        for user in users
        if not user.is_active or user.pk == actor.pk
    ]
    if invalid:
        raise ValidationError(
            {
                "users": (
                    "Ces comptes ne peuvent pas être désactivés : "
                    + ", ".join(invalid)
                    + "."
                )
            }
        )
    for user in users:
        user.is_active = False
        _attribute_history(user, actor, "Désactivation groupée du compte")
        user.save(update_fields=["is_active"])
    return len(users)


def _delete_locked_orphans(*, actor: User, users: Sequence[User], reason: str) -> int:
    """Delete one already locked selection after checking every relation."""
    blocked: list[str] = []
    for user in users:
        blockers = list(managed_user_deletion_blockers(user))
        if user.pk == actor.pk:
            blockers.insert(0, "vous ne pouvez pas supprimer votre propre compte")
        if blockers:
            blocked.append(f"{user.login_alias or user.email} : " + "; ".join(blockers))
    if blocked:
        raise ValidationError({"users": blocked})

    history_reason = f"Suppression groupée : {reason.strip()}"
    for user in users:
        _attribute_history(user, actor, history_reason)
        user.delete()
    return len(users)


@transaction.atomic
def bulk_manage_users(
    *,
    actor: User,
    action: str,
    selections: Sequence[tuple[int, str]],
    reason: str = "",
) -> int:
    """Deactivate accounts or delete inactive orphans as one audited batch."""
    ensure_can_manage_users(actor)
    if action not in USER_BULK_ACTIONS:
        raise ValidationError({"action": "Cette action groupée est inconnue."})

    requested_ids = [user_id for user_id, _state_token in selections]
    locked_by_id = {
        user.pk: user
        for user in User.objects.select_for_update().filter(pk__in=requested_ids)
    }
    missing_ids = sorted(set(requested_ids) - set(locked_by_id))
    if missing_ids:
        raise ValidationError(
            {"users": f"Comptes introuvables : {', '.join(map(str, missing_ids))}."}
        )

    users = [locked_by_id[user_id] for user_id in requested_ids]
    stale_labels: list[str] = []
    for user, (_user_id, expected_token) in zip(users, selections, strict=True):
        ensure_can_manage_users(actor, user)
        if user_management_state_token(user) != expected_token:
            stale_labels.append(user.login_alias or user.email)
    if stale_labels:
        raise StaleUserStateError(
            "Ces comptes ont changé depuis leur sélection : "
            + ", ".join(stale_labels)
            + ". Rechargez la liste."
        )

    if action == "deactivate":
        return _deactivate_locked_users(actor=actor, users=users)
    return _delete_locked_orphans(actor=actor, users=users, reason=reason)


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
def change_password(*, user: User, current_password: str, new_password: str) -> User:
    """Replace the current password and clear any mandatory-change marker."""
    locked = User.objects.select_for_update().get(pk=user.pk)
    if not locked.check_password(current_password):
        raise ValidationError(
            {"current_password": "Le mot de passe actuel est incorrect."}
        )
    password_validation.validate_password(new_password, locked)
    was_required = locked.password_change_required
    locked.set_password(new_password)
    locked.password_change_required = False
    reason = (
        "Remplacement du mot de passe temporaire"
        if was_required
        else "Modification du mot de passe"
    )
    _attribute_history(locked, locked, reason)
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
