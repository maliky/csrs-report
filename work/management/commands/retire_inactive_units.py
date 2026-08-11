"""Retire explicitly selected inactive units without cascading business data."""

from datetime import date
from typing import cast

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.db.models import Q

from accounts.models import User
from work.models import (
    OrganizationMembership,
    OrganizationUnit,
    OrganizationUnitLink,
    ReportingLine,
)
from work.services import attribute_history


BASELINE_REASON = "Etat initial lors de l'activation de l'audit"


class Command(BaseCommand):
    help = "Retire des unites inactives explicitement nommees et sans reference metier."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--actor", required=True)
        parser.add_argument("--unit", action="append", required=True)
        parser.add_argument("--protect-since", required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        del args
        dry_run = cast(bool, options["dry_run"])
        if not dry_run and not cast(bool, options["confirm"]):
            raise CommandError(
                "L'ecriture exige --confirm apres une execution --dry-run."
            )
        try:
            protect_since = date.fromisoformat(cast(str, options["protect_since"]))
        except ValueError as exc:
            raise CommandError("--protect-since doit utiliser YYYY-MM-DD.") from exc
        try:
            actor = User.objects.get(login_alias=cast(str, options["actor"]))
        except User.DoesNotExist as exc:
            raise CommandError("Acteur introuvable.") from exc
        if not actor.is_active or not (actor.is_it_admin or actor.is_superuser):
            raise CommandError("L'acteur doit etre un administrateur IT actif.")

        codes = tuple(dict.fromkeys(cast(list[str], options["unit"])))
        with transaction.atomic():
            units = list(
                OrganizationUnit.objects.select_for_update()
                .filter(code__in=codes)
                .order_by("code")
            )
            missing = sorted(set(codes) - {unit.code for unit in units})
            if missing:
                raise CommandError("Unites introuvables: " + ", ".join(missing))
            for unit in units:
                self._validate(unit, protect_since)
            for unit in units:
                links = OrganizationUnitLink.objects.select_for_update().filter(
                    Q(supervisor_service=unit) | Q(collaborator_service=unit)
                )
                for link in links:
                    attribute_history(
                        link,
                        actor,
                        "Retrait d'une unite inactive sans reference metier",
                    )
                    link.delete()
                attribute_history(
                    unit,
                    actor,
                    "Retrait d'une unite inactive sans reference metier",
                )
                unit.delete()
                self.stdout.write(f"unite retirable: {unit.code}")
            if dry_run:
                transaction.set_rollback(True)

        suffix = " (simulation annulee)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"unites retirees={len(units)}{suffix}"))

    @staticmethod
    def _validate(unit: OrganizationUnit, protect_since: date) -> None:
        if unit.active:
            raise CommandError(f"{unit.code} est encore active.")
        related = {
            "appartenances": unit.memberships.count(),
            "lignes": unit.reporting_lines.count(),
            "taches": unit.task_assignments.count(),
            "propositions": unit.task_proposals.count(),
            "delegations": unit.role_grants.count(),
            "files_traitees": unit.handled_process_queues.count(),
            "files_couvertes": unit.covered_process_queues.count(),
            "dossiers_processus": unit.process_cases.count(),
        }
        blocking = {name: count for name, count in related.items() if count}
        if blocking:
            details = " ".join(f"{name}={count}" for name, count in blocking.items())
            raise CommandError(f"{unit.code} conserve des references metier: {details}")
        recent_unit_history = unit.history.filter(
            history_date__date__gte=protect_since
        ).exclude(history_change_reason=BASELINE_REASON)
        recent_relation_history = (
            OrganizationMembership.history.filter(
                unit_id=unit.pk, history_date__date__gte=protect_since
            ).exists()
            or ReportingLine.history.filter(
                unit_id=unit.pk, history_date__date__gte=protect_since
            ).exists()
        )
        if recent_unit_history.exists() or recent_relation_history:
            raise CommandError(
                f"{unit.code} possede une modification protegee depuis le {protect_since:%d/%m/%Y}."
            )
