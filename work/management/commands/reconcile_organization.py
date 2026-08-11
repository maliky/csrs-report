"""Safely reconcile current memberships, managers and scoped grants."""

from datetime import date, datetime, time, timedelta
from typing import cast

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from access.models import RoleGrant
from access.services import grant_role, primary_membership, revoke_role
from accounts.models import User
from work.models import OrganizationMembership, OrganizationUnit, OrganizationUnitLink
from work.services import (
    attribute_history,
    set_primary_membership,
    set_primary_supervisor,
)


class Command(BaseCommand):
    help = (
        "Reconcilie l'organigramme sans supprimer les anciennes relations. "
        "Les options peuvent etre repetees."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--actor", required=True)
        parser.add_argument("--effective-date", required=True)
        parser.add_argument("--primary-membership", action="append", default=[])
        parser.add_argument("--close-membership", action="append", default=[])
        parser.add_argument("--line", action="append", default=[])
        parser.add_argument("--replace-grant", action="append", default=[])
        parser.add_argument("--revoke-grant", action="append", default=[])
        parser.add_argument("--remove-unit-link", action="append", default=[])
        parser.add_argument("--position", action="append", default=[])
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args: object, **options: object) -> None:  # noqa: C901
        del args
        dry_run = cast(bool, options["dry_run"])
        if not dry_run and not cast(bool, options["confirm"]):
            raise CommandError(
                "L'ecriture exige --confirm apres une execution --dry-run."
            )
        try:
            effective_date = date.fromisoformat(cast(str, options["effective_date"]))
        except ValueError as exc:
            raise CommandError("--effective-date doit utiliser YYYY-MM-DD.") from exc
        actor = self._user(cast(str, options["actor"]))
        if not actor.is_active or not (actor.is_it_admin or actor.is_superuser):
            raise CommandError("L'acteur doit etre un administrateur IT actif.")

        counts = {
            "positions": 0,
            "appartenances_principales": 0,
            "appartenances_cloturees": 0,
            "lignes": 0,
            "delegations": 0,
            "delegations_revoquees": 0,
            "liens_unites_retires": 0,
        }
        with transaction.atomic():
            for raw in cast(list[str], options["position"]):
                alias, position = self._split(raw, "=", 2, "--position ALIAS=FONCTION")
                user = self._user(alias)
                if user.position != position:
                    user.position = position
                    attribute_history(
                        user,
                        actor,
                        "Correction de fonction pendant la reconciliation",
                    )
                    user.save(update_fields=["position"])
                    counts["positions"] += 1

            for raw in cast(list[str], options["primary_membership"]):
                alias, unit_code = self._split(
                    raw, ":", 2, "--primary-membership ALIAS:UNITE"
                )
                membership = set_primary_membership(
                    user=self._user(alias),
                    unit_id=self._unit(unit_code).pk,
                    start_date=effective_date,
                    actor=actor,
                    reason="Reconciliation de l'organigramme",
                )
                self.stdout.write(
                    f"appartenance principale: {alias} -> {membership.unit.code}"
                )
                counts["appartenances_principales"] += 1

            for raw in cast(list[str], options["close_membership"]):
                alias, unit_code = self._split(
                    raw, ":", 2, "--close-membership ALIAS:UNITE"
                )
                memberships = OrganizationMembership.objects.select_for_update().filter(
                    user=self._user(alias),
                    unit=self._unit(unit_code),
                    end_date__isnull=True,
                    is_primary=False,
                )
                for membership in memberships:
                    membership.end_date = max(
                        membership.start_date, effective_date - timedelta(days=1)
                    )
                    attribute_history(
                        membership,
                        actor,
                        "Cloture d'une appartenance obsolete",
                    )
                    membership.save(update_fields=["end_date"])
                    counts["appartenances_cloturees"] += 1

            for raw in cast(list[str], options["line"]):
                employee_alias, supervisor_alias = self._split(
                    raw, ":", 2, "--line COLLABORATEUR:RESPONSABLE"
                )
                employee = self._user(employee_alias)
                employee_membership = primary_membership(employee, effective_date)
                if employee_membership is None:
                    raise CommandError(
                        f"{employee_alias} n'a pas d'unite principale au {effective_date}."
                    )
                line = set_primary_supervisor(
                    employee=employee,
                    supervisor=self._user(supervisor_alias),
                    unit_id=employee_membership.unit_id,
                    start_date=effective_date,
                    actor=actor,
                    reason="Reconciliation de l'organigramme",
                    require_supervisor_membership=True,
                )
                self.stdout.write(
                    f"ligne principale: {employee_alias} -> {supervisor_alias} ({line.unit.code})"
                )
                counts["lignes"] += 1

            for raw in cast(list[str], options["replace_grant"]):
                alias, old_code, new_code = self._split(
                    raw, ":", 3, "--replace-grant ALIAS:ANCIENNE:NOUVELLE"
                )
                user = self._user(alias)
                old_unit = self._unit(old_code)
                old_grants = RoleGrant.objects.select_for_update().filter(
                    user=user, unit=old_unit, revoked_at__isnull=True
                )
                for old_grant in old_grants:
                    new_unit = self._unit(new_code)
                    revoke_role(
                        actor=actor,
                        grant=old_grant,
                        reason="Unite archivee pendant la reconciliation",
                    )
                    equivalent_exists = RoleGrant.objects.filter(
                        user=user,
                        role=old_grant.role,
                        unit=new_unit,
                        scope=old_grant.scope,
                        revoked_at__isnull=True,
                    ).exists()
                    if not equivalent_exists:
                        grant_role(
                            actor=actor,
                            user=user,
                            role=old_grant.role,
                            unit=new_unit,
                            scope=old_grant.scope,
                            valid_from=self._effective_datetime(effective_date),
                            valid_until=old_grant.valid_until,
                            reason="Transfert depuis une unite archivee",
                        )
                    counts["delegations"] += 1

            for raw in cast(list[str], options["revoke_grant"]):
                alias, unit_code = self._split(raw, ":", 2, "--revoke-grant ALIAS:UNITE")
                grants = RoleGrant.objects.select_for_update().filter(
                    user=self._user(alias),
                    unit=self._unit(unit_code),
                    revoked_at__isnull=True,
                )
                for grant in grants:
                    revoke_role(
                        actor=actor,
                        grant=grant,
                        reason="Unite archivee pendant la reconciliation",
                    )
                    counts["delegations_revoquees"] += 1

            for raw in cast(list[str], options["remove_unit_link"]):
                parent_code, child_code = self._split(
                    raw, ":", 2, "--remove-unit-link PARENT:ENFANT"
                )
                links = OrganizationUnitLink.objects.select_for_update().filter(
                    supervisor_service=self._unit(parent_code),
                    collaborator_service=self._unit(child_code),
                )
                for link in links:
                    attribute_history(
                        link,
                        actor,
                        "Retrait d'un lien vers une unite archivee",
                    )
                    link.delete()
                    counts["liens_unites_retires"] += 1

            if dry_run:
                transaction.set_rollback(True)

        suffix = " (simulation annulee)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                "reconciliation: "
                + " ".join(f"{key}={value}" for key, value in counts.items())
                + suffix
            )
        )

    @staticmethod
    def _split(raw: str, separator: str, size: int, usage: str) -> tuple[str, ...]:
        parts = tuple(part.strip() for part in raw.split(separator, maxsplit=size - 1))
        if len(parts) != size or not all(parts):
            raise CommandError(f"Format attendu: {usage}")
        return parts

    @staticmethod
    def _user(alias: str) -> User:
        try:
            return User.objects.get(login_alias=alias)
        except User.DoesNotExist as exc:
            raise CommandError(f"Utilisateur introuvable: {alias}") from exc

    @staticmethod
    def _unit(code: str) -> OrganizationUnit:
        try:
            return OrganizationUnit.objects.get(code=code)
        except OrganizationUnit.DoesNotExist as exc:
            raise CommandError(f"Unite introuvable: {code}") from exc

    @staticmethod
    def _effective_datetime(day: date) -> datetime:
        return timezone.make_aware(datetime.combine(day, time.min))
