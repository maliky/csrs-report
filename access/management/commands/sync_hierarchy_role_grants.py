"""Create auditable manager grants from the active reporting hierarchy."""

from __future__ import annotations

from typing import cast

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from access.models import GrantScope, RoleGrant, ScopedRole
from access.services import active_memberships, grant_role
from accounts.models import User
from work.services import active_lines


class Command(BaseCommand):
    help = "Attribue UNIT_MANAGER aux responsables actifs sur leur service principal."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--actor",
            default="dev",
            help="Identifiant court de l'administrateur IT qui autorise l'attribution.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        actor_alias = str(options["actor"]).strip().lower()
        try:
            actor = User.objects.get(login_alias=actor_alias, is_active=True)
        except User.DoesNotExist as error:
            raise CommandError(
                f"Administrateur IT actif introuvable: {actor_alias}."
            ) from error
        role = ScopedRole.objects.get(code="UNIT_MANAGER", active=True)
        manager_ids = set(
            active_lines()
            .filter(is_primary=True, supervisor__is_active=True)
            .values_list("supervisor_id", flat=True)
        )
        memberships = {
            membership.user_id: membership
            for membership in active_memberships()
            .filter(user_id__in=manager_ids, is_primary=True)
            .select_related("user", "unit")
            .order_by("user__login_alias", "user__email")
        }
        missing_ids = manager_ids - memberships.keys()
        if missing_ids:
            missing = ", ".join(
                user.login_alias or user.email
                for user in User.objects.filter(pk__in=missing_ids).order_by(
                    "login_alias", "email"
                )
            )
            raise CommandError(
                "Responsables sans appartenance principale active: " + missing
            )

        created = 0
        skipped = 0
        now = timezone.now()
        with transaction.atomic():
            for membership in memberships.values():
                existing = RoleGrant.objects.filter(
                    user_id=membership.user_id,
                    role=role,
                    unit_id=membership.unit_id,
                    scope=GrantScope.UNIT_TREE,
                    revoked_at__isnull=True,
                    valid_until__isnull=True,
                ).first()
                if existing is not None:
                    skipped += 1
                    self.stdout.write(
                        f"conserve {membership.user.login_alias}: "
                        f"{role.code} / {membership.unit.code} / tree"
                    )
                    continue
                grant_role(
                    actor=actor,
                    user=membership.user,
                    role=role,
                    unit=membership.unit,
                    scope=GrantScope.UNIT_TREE,
                    valid_from=now,
                    valid_until=None,
                    reason=(
                        "Responsabilite principale active issue de "
                        "l'organigramme institutionnel."
                    ),
                )
                created += 1
                self.stdout.write(
                    f"attribue {membership.user.login_alias}: "
                    f"{role.code} / {membership.unit.code} / tree"
                )
            if cast(bool, options["dry_run"]):
                transaction.set_rollback(True)
        suffix = " (simulation annulee)" if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"delegations responsables: creees={created} conservees={skipped}"
                f"{suffix}"
            )
        )
