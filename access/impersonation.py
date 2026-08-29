"""Session-scoped, audited superuser impersonation."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from access.models import RoleGrant, RoleSimulation
from access.services import active_memberships, active_role_grants


ROLE_SIMULATION_SESSION_KEY = "access_role_simulation_id"


def _ensure_superuser(administrator: User) -> None:
    if not administrator.is_active or not administrator.is_superuser:
        raise PermissionDenied("Seul un superutilisateur peut changer de role.")


def access_snapshot(
    user: User,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Freeze the target's active delegated roles and organization units."""
    roles = [
        {
            "code": grant.role.code,
            "name": grant.role.name,
            "unit_id": grant.unit_id,
            "unit": grant.unit.long_name,
            "scope": grant.scope,
        }
        for grant in active_role_grants(user).order_by("role__name", "unit__long_name")
    ]
    memberships = [
        {
            "id": membership.unit_id,
            "code": membership.unit.code,
            "name": membership.unit.long_name,
            "is_primary": membership.is_primary,
        }
        for membership in active_memberships()
        .filter(user=user, unit__active=True)
        .select_related("unit")
        .order_by("-is_primary", "unit__long_name")
    ]
    if not roles:
        roles = [
            {
                "code": "EMPLOYEE",
                "name": "Employe",
                "unit_id": memberships[0]["id"] if memberships else None,
                "unit": memberships[0]["name"] if memberships else "",
                "scope": "unit",
            }
        ]
    return roles, memberships


def role_simulation_options(administrator: User) -> list[dict[str, object]]:
    """Return active, non-privileged users available to a superuser."""
    _ensure_superuser(administrator)
    users = list(
        User.objects.filter(
            is_active=True,
            is_superuser=False,
            is_it_admin=False,
        ).order_by("last_name", "first_name", "email")
    )
    user_ids = [user.pk for user in users]
    roles_by_user: dict[int, list[dict[str, object]]] = {}
    for grant in (
        RoleGrant.objects.active_at(timezone.now())
        .filter(user_id__in=user_ids)
        .select_related("role", "unit")
        .order_by("user_id", "role__name", "unit__long_name")
    ):
        roles_by_user.setdefault(grant.user_id, []).append(
            {
                "code": grant.role.code,
                "name": grant.role.name,
                "unit_id": grant.unit_id,
                "unit": grant.unit.long_name,
                "scope": grant.scope,
            }
        )
    units_by_user: dict[int, list[dict[str, object]]] = {}
    for membership in (
        active_memberships()
        .filter(user_id__in=user_ids, unit__active=True)
        .select_related("unit")
        .order_by("user_id", "-is_primary", "unit__long_name")
    ):
        units_by_user.setdefault(membership.user_id, []).append(
            {
                "id": membership.unit_id,
                "code": membership.unit.code,
                "name": membership.unit.long_name,
                "is_primary": membership.is_primary,
            }
        )

    options: list[dict[str, object]] = []
    for user in users:
        units = units_by_user.get(user.pk, [])
        roles = roles_by_user.get(user.pk)
        if not roles:
            roles = [
                {
                    "code": "EMPLOYEE",
                    "name": "Employe",
                    "unit_id": units[0]["id"] if units else None,
                    "unit": units[0]["name"] if units else "",
                    "scope": "unit",
                }
            ]
        options.append(
            {
                "id": user.pk,
                "name": str(user),
                "position": user.position,
                "login_alias": user.login_alias,
                "avatar": user.avatar or None,
                "roles": roles,
                "units": units,
            }
        )
    return options


@transaction.atomic
def start_role_simulation(*, administrator: User, target: User) -> RoleSimulation:
    """Create the immutable start record for one simulated identity."""
    _ensure_superuser(administrator)
    if (
        not target.is_active
        or target.is_superuser
        or target.is_it_admin
        or target.pk == administrator.pk
    ):
        raise ValidationError("Cet utilisateur ne peut pas etre simule.")
    roles, units = access_snapshot(target)
    return RoleSimulation.objects.create(
        administrator=administrator,
        target=target,
        administrator_label=str(administrator),
        target_label=str(target),
        role_snapshot=roles,
        unit_snapshot=units,
    )


@transaction.atomic
def end_role_simulation(simulation: RoleSimulation, *, reason: str) -> RoleSimulation:
    """Close a simulation once while preserving its full audit trail."""
    locked = RoleSimulation.objects.select_for_update().get(pk=simulation.pk)
    if locked.ended_at is None:
        from django.utils import timezone

        locked.ended_at = timezone.now()
        locked.end_reason = reason[:80]
        locked.save(update_fields=["ended_at", "end_reason"])
    return locked
