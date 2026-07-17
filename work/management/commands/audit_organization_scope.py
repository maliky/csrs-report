"""Report legacy rows that still lack an explicit organization scope."""

from __future__ import annotations

from typing import cast

from django.core.management.base import BaseCommand, CommandError, CommandParser

from accounts.models import User
from work.models import OrganizationMembership, TaskAssignment, TaskProposal


class Command(BaseCommand):
    help = "Verifie les appartenances et services historiques des donnees metier."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--fail-on-unresolved", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        assignments = TaskAssignment.objects.filter(organization_unit__isnull=True)
        proposals = TaskProposal.objects.filter(organization_unit__isnull=True)
        primary_users = OrganizationMembership.objects.filter(
            is_primary=True,
            end_date__isnull=True,
        ).values_list("user_id", flat=True)
        users = User.objects.filter(is_active=True, is_it_admin=False).exclude(
            pk__in=primary_users
        )
        self.stdout.write(
            "audit organisation: "
            f"affectations_sans_service={assignments.count()} "
            f"propositions_sans_service={proposals.count()} "
            f"utilisateurs_sans_appartenance={users.count()}"
        )
        for assignment in assignments.select_related("task", "employee")[:20]:
            self.stdout.write(
                f"  affectation {assignment.pk}: {assignment.task.code} / "
                f"{assignment.employee.email}"
            )
        for proposal in proposals.select_related("employee")[:20]:
            self.stdout.write(
                f"  proposition {proposal.pk}: {proposal.title} / "
                f"{proposal.employee.email}"
            )
        for user in users[:20]:
            self.stdout.write(f"  utilisateur {user.pk}: {user.email}")
        unresolved = assignments.exists() or proposals.exists() or users.exists()
        if cast(bool, options["fail_on_unresolved"]) and unresolved:
            raise CommandError("Des rattachements organisationnels restent a corriger.")
