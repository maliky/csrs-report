"""Create fictitious records for the responsive pilot walkthrough."""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from work.models import (
    ActionPlan,
    AssignmentStatus,
    InstitutionalAction,
    OrganizationUnit,
    ProgressEntry,
    StrategicPlan,
    Task,
    TaskAssignment,
    WorkCalendar,
    default_work_calendar_id,
)
from work.services import set_primary_supervisor, week_start_for


class Command(BaseCommand):
    help = "Cree des comptes et taches strictement fictifs pour le pilote."

    def handle(self, *args: object, **options: object) -> None:
        today = timezone.localdate()
        monday = week_start_for(today)
        unit, _ = OrganizationUnit.objects.get_or_create(
            code="IT-DEMO", defaults={"name": "Service IT — Demonstration"}
        )
        manager = self.ensure_user("responsable.demo@example.invalid", "Awa", "Manager")
        observer = self.ensure_user(
            "observateur.demo@example.invalid", "Yao", "Observateur"
        )
        employee = self.ensure_user("employe.demo@example.invalid", "Mariam", "Employe")
        set_primary_supervisor(
            employee=employee, supervisor=manager, unit_id=unit.pk, start_date=monday
        )
        from work.models import ReportingLine

        ReportingLine.objects.get_or_create(
            employee=employee,
            supervisor=observer,
            unit=unit,
            start_date=monday,
            defaults={"is_primary": False},
        )
        plan, _ = StrategicPlan.objects.get_or_create(
            name="Plan strategique fictif 2026–2028",
            defaults={"start_date": monday, "end_date": monday.replace(year=2028)},
        )
        action_plan, _ = ActionPlan.objects.get_or_create(
            code="PA-DEMO",
            defaults={"name": "Transformation numerique", "strategic_plan": plan},
        )
        action, _ = InstitutionalAction.objects.get_or_create(
            code="ACT-DEMO",
            defaults={"name": "Ameliorer le support interne", "action_plan": action_plan},
        )
        task, _ = Task.objects.get_or_create(
            code="TSK-DEMO-001",
            defaults={
                "title": "Documenter les demandes de support",
                "description": "Constituer une fiche simple avec les demandes fictives de la semaine.",
                "action": action,
                "created_by": manager,
            },
        )
        assignment, _ = TaskAssignment.objects.get_or_create(
            task=task,
            employee=employee,
            defaults={
                "manager": manager,
                "start_date": monday,
                "due_date": WorkCalendar.objects.get(
                    pk=default_work_calendar_id()
                ).due_date_for(monday, Decimal("3.00")),
                "estimated_work_days": Decimal("3.00"),
                "calendar_id": default_work_calendar_id(),
                "status": AssignmentStatus.ACTIVE,
            },
        )
        ProgressEntry.objects.update_or_create(
            assignment=assignment,
            entry_date=today,
            defaults={
                "percentage": 40,
                "note": "Exemple fictif pour le test d'interface.",
                "author": employee,
            },
        )
        self.stdout.write(
            self.style.SUCCESS("Donnees fictives creees sans mot de passe.")
        )

    @staticmethod
    def ensure_user(email: str, first_name: str, position: str) -> User:
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": "Demo",
                "position": position,
            },
        )
        if user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user
