"""Small permission-aware values shared by the responsive navigation."""

from __future__ import annotations

from django.http import HttpRequest

from access.services import MANAGE_PERMISSION, VIEW_PERMISSION, scoped_unit_ids
from accounts.models import User
from work.services import active_lines


def authorization_navigation(request: HttpRequest) -> dict[str, bool]:
    """Expose navigation only when its server-side capability currently exists."""
    user = request.user
    if not isinstance(user, User) or not user.is_authenticated:
        return {"can_access_team": False, "can_assign_tasks": False}
    if user.is_it_admin or user.is_superuser:
        return {"can_access_team": True, "can_assign_tasks": True}
    has_direct_team = active_lines().filter(supervisor=user).exists()
    can_view_scope = bool(scoped_unit_ids(user, VIEW_PERMISSION))
    can_manage_scope = bool(scoped_unit_ids(user, MANAGE_PERMISSION))
    return {
        "can_access_team": has_direct_team or can_view_scope,
        "can_assign_tasks": has_direct_team or can_manage_scope,
    }
