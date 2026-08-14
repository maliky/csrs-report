"""Safely clear task and agenda data without touching organization records."""

from __future__ import annotations

from typing import cast

from django.core.management.base import BaseCommand, CommandError, CommandParser

from accounts.models import User
from work.reporting_cleanup import reset_reporting_data


class Command(BaseCommand):
    help = "Supprime les taches, propositions et agendas en conservant l'organigramme."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--actor", default="dev")
        parser.add_argument("--reason", required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        dry_run = cast(bool, options["dry_run"])
        confirm = cast(bool, options["confirm"])
        if dry_run == confirm:
            raise CommandError("Choisissez exactement --dry-run ou --confirm.")
        alias = cast(str, options["actor"])
        try:
            actor = User.objects.get(login_alias__iexact=alias)
        except User.DoesNotExist as exc:
            raise CommandError(f"Compte acteur inconnu: {alias}") from exc

        try:
            result = reset_reporting_data(
                actor=actor,
                reason=cast(str, options["reason"]),
                dry_run=dry_run,
            )
        except Exception as exc:
            if isinstance(exc, CommandError):
                raise
            raise CommandError(str(exc)) from exc

        summary = " ".join(f"{key}={value}" for key, value in result.counts.items())
        if dry_run:
            self.stdout.write(f"simulation annulee: {summary}")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"reporting reinitialise: audit={result.audit_id} "
                f"pdf={result.deleted_files} {summary}"
            )
        )
