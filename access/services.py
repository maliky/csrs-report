"""Typed functional authorization services."""

from __future__ import annotations

from collections import deque
from datetime import date, datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.models import User
from access.models import GrantScope, RoleGrant, ScopedRole
from work.models import OrganizationMembership, OrganizationUnit, OrganizationUnitLink

VIEW_PERMISSION = "view_unit_scope"
MANAGE_PERMISSION = "manage_unit_assignments"
PROGRESS_PERMISSION = "correct_unit_progress"
PROPOSAL_PERMISSION = "review_unit_proposals"
EXPORT_PERMISSION = "export_unit_data"
PROCESS_VIEW_PERMISSION = "view_process_scope"
MISSION_ASSISTANCE_PERMISSION = "work_mission_assistance"
MISSION_SIGN_PERMISSION = "sign_mission_order"
MISSION_DISTRIBUTION_PERMISSION = "work_mission_distribution"
MISSION_FLEET_PERMISSION = "work_mission_fleet"
PROCESS_EXPORT_PERMISSION = "export_process"
VISITOR_PERMISSION = "manage_visitor_visits"
AVAILABILITY_PERMISSION = "manage_staff_availability"
AGENDA_PREPARE_PERMISSION = "prepare_weekly_agenda"
AGENDA_VIEW_PERMISSION = "view_weekly_agenda"


def grant_has_permission(grant: RoleGrant, permission: str) -> bool:
    """Return whether one prefetched grant carries an access permission."""
    return any(
        item.codename == permission and item.content_type.app_label == "access"
        for item in grant.role.group.permissions.all()
    )


def active_role_grants(user: User, at: datetime | None = None) -> QuerySet[RoleGrant]:
    """Return the user's grants active at one explicit instant."""
    instant = at or timezone.now()
    return (
        RoleGrant.objects.active_at(instant)
        .filter(user=user)
        .select_related("role", "role__group", "unit")
        .prefetch_related("role__group__permissions__content_type")
    )


def units_in_scope(grant: RoleGrant) -> frozenset[int]:
    """Resolve one grant's active unit tree without trusting acyclicity."""
    if not grant.unit.active:
        return frozenset()
    if grant.scope == GrantScope.UNIT_ONLY:
        return frozenset({grant.unit_id})
    edges: dict[int, set[int]] = {}
    for parent_id, child_id in OrganizationUnitLink.objects.values_list(
        "supervisor_service_id", "collaborator_service_id"
    ):
        edges.setdefault(parent_id, set()).add(child_id)
    active_ids = set(
        OrganizationUnit.objects.filter(active=True).values_list("pk", flat=True)
    )
    queue: deque[int] = deque([grant.unit_id])
    visited: set[int] = set()
    while queue:
        unit_id = queue.popleft()
        if unit_id in visited or unit_id not in active_ids:
            continue
        visited.add(unit_id)
        queue.extend(edges.get(unit_id, ()))
    return frozenset(visited)


def scoped_unit_ids(
    user: User, permission: str, at: datetime | None = None
) -> frozenset[int]:
    """Return the union of units granted for one permission codename."""
    unit_ids: set[int] = set()
    for grant in active_role_grants(user, at):
        if grant_has_permission(grant, permission):
            unit_ids.update(units_in_scope(grant))
    return frozenset(unit_ids)


def has_scoped_permission(
    user: User,
    permission: str,
    unit_id: int | None,
    at: datetime | None = None,
) -> bool:
    """Check one scoped permission without replacing global IT authority."""
    if not user.is_active or unit_id is None:
        return False
    if user.is_superuser or user.is_it_admin:
        return True
    return unit_id in scoped_unit_ids(user, permission, at)


def has_active_permission(
    user: User, permission: str, at: datetime | None = None
) -> bool:
    """Check a role permission whose feature spans its delegated tree."""
    if not user.is_active:
        return False
    if user.is_superuser or user.is_it_admin:
        return True
    return any(
        grant_has_permission(grant, permission) for grant in active_role_grants(user, at)
    )


def active_memberships(on_day: date | None = None) -> QuerySet[OrganizationMembership]:
    """Return organization memberships active on a given local date."""
    target = on_day or timezone.localdate()
    return OrganizationMembership.objects.filter(start_date__lte=target).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=target)
    )


def primary_membership(
    user: User, on_day: date | None = None
) -> OrganizationMembership | None:
    """Return the primary service membership active on a date."""
    return (
        active_memberships(on_day)
        .filter(user=user, is_primary=True)
        .select_related("unit")
        .order_by("-start_date", "-pk")
        .first()
    )


def member_user_ids(
    unit_ids: frozenset[int], on_day: date | None = None
) -> frozenset[int]:
    """Return active users belonging to at least one selected unit."""
    if not unit_ids:
        return frozenset()
    return frozenset(
        active_memberships(on_day)
        .filter(unit_id__in=unit_ids, user__is_active=True)
        .values_list("user_id", flat=True)
    )


def can_administer_grants(user: User) -> bool:
    """Keep grant authority restricted to technical administrators."""
    return bool(user.is_active and (user.is_it_admin or user.is_superuser))


@transaction.atomic
def grant_role(
    *,
    actor: User,
    user: User,
    role: ScopedRole,
    unit: OrganizationUnit,
    scope: str,
    valid_from: datetime,
    valid_until: datetime | None,
    reason: str,
) -> RoleGrant:
    """Create an audited delegation through the only supported write path."""
    if not can_administer_grants(actor):
        raise PermissionDenied("Seul l'administrateur IT peut deleguer un role.")
    if scope not in GrantScope.values:
        raise ValidationError({"scope": "Portee inconnue."})
    grant = RoleGrant(
        user=user,
        role=role,
        unit=unit,
        scope=scope,
        valid_from=valid_from,
        valid_until=valid_until,
        granted_by=actor,
        grant_reason=reason.strip(),
    )
    grant._history_user = actor  # type: ignore[attr-defined]
    grant._change_reason = "Attribution d'une delegation"  # type: ignore[attr-defined]
    grant.save()
    return grant


@transaction.atomic
def revoke_role(*, actor: User, grant: RoleGrant, reason: str) -> RoleGrant:
    """Revoke a delegation immediately while retaining its audit record."""
    if not can_administer_grants(actor):
        raise PermissionDenied("Seul l'administrateur IT peut revoquer un role.")
    if grant.revoked_at is not None:
        return grant
    if not reason.strip():
        raise ValidationError({"revoke_reason": "Le motif est obligatoire."})
    grant.revoked_at = timezone.now()
    grant.revoked_by = actor
    grant.revoke_reason = reason.strip()
    grant._history_user = actor  # type: ignore[attr-defined]
    grant._change_reason = "Revocation d'une delegation"  # type: ignore[attr-defined]
    grant.save(update_fields=["revoked_at", "revoked_by", "revoke_reason"])
    return grant
