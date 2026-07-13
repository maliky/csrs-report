"""Load a safe organizational illustration with twelve weeks of activity."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import cast

from django.contrib.auth import authenticate
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.test import Client, override_settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from work.models import (
    ActionPlan,
    ActivityKind,
    AssignmentStatus,
    InstitutionalAction,
    NotificationDelivery,
    OrganizationUnit,
    ProgressEntry,
    ProposalStatus,
    ReportingLine,
    StrategicPlan,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskProposal,
)
from work.services import set_primary_supervisor, week_start_for


@dataclass(frozen=True)
class PilotUserSpec:
    alias: str
    position: str
    unit_code: str | None
    manager_alias: str | None
    has_scenarios: bool = True

    @property
    def email(self) -> str:
        return f"{self.alias}@demo.invalid"


PILOT_USERS = (
    PilotUserSpec("dev", "Administrateur technique", None, None),
    PilotUserSpec("dg", "Direction generale", "DG", None),
    PilotUserSpec("daf", "Direction administrative et financiere", "DAF", "dg"),
    PilotUserSpec("drv", "Direction de la valorisation et des expertises", "DRV", "dg"),
    PilotUserSpec(
        "finances", "Responsable comptabilite, finances et caisse", "FIN", "daf"
    ),
    PilotUserSpec(
        "kpon", "Responsable technologies et systemes d'information", "TSI", "daf"
    ),
    PilotUserSpec(
        "formation", "Responsable formation et renforcement des capacites", "FOR", "drv"
    ),
    PilotUserSpec(
        "valorisation", "Responsable valorisation et partenariats", "VAL", "drv"
    ),
    PilotUserSpec("comptable", "Comptable", "FIN", "finances"),
    PilotUserSpec("caissier", "Caissier", "FIN", "finances"),
    PilotUserSpec("atall", "Agent technologies et systemes d'information", "TSI", "kpon"),
    PilotUserSpec("assistant", "Assistant de formation", "FOR", "formation"),
    PilotUserSpec("bibliothecaire", "Bibliothecaire", "FOR", "formation"),
    PilotUserSpec("communication", "Charge de communication", "VAL", "valorisation"),
    PilotUserSpec("partenariat", "Charge des partenariats", "VAL", "valorisation"),
    PilotUserSpec("jardinier", "Jardinier", "VAL", "valorisation"),
    PilotUserSpec("ct", "Conseiller technique de la direction", "CT", "dg", False),
    PilotUserSpec(
        "rse", "Responsable communication institutionnelle et RSE", "RSE", "dg", False
    ),
    PilotUserSpec("genre", "Responsable genre, equite et inclusion", "GEI", "dg", False),
    PilotUserSpec("ethique", "Responsable ethique", "ETH", "dg", False),
    PilotUserSpec("suivi", "Responsable suivi et evaluation", "SE", "dg", False),
    PilotUserSpec("controle", "Responsable controle de gestion", "CG", "dg", False),
    PilotUserSpec(
        "rh", "Responsable ressources humaines et moyens generaux", "RH", "daf", False
    ),
    PilotUserSpec(
        "i2a", "Responsable intendance, accueil et assistance", "I2A", "daf", False
    ),
    PilotUserSpec(
        "achats", "Responsable achats et approvisionnements", "ACH", "daf", False
    ),
    PilotUserSpec(
        "documentation", "Responsable documentation et archives", "DOC", "daf", False
    ),
    PilotUserSpec(
        "recherche", "Coordonnateur recherche scientifique", "DRD", "drd", False
    ),
    PilotUserSpec("clinique", "Responsable recherche clinique", "CLIN", "drd", False),
    PilotUserSpec("observatoire", "Responsable observatoires", "OBS", "drd", False),
    PilotUserSpec("labo", "Responsable laboratoire central", "LAB", "drd", False),
    PilotUserSpec("microscopie", "Responsable unite de microscopie", "MIC", "drd", False),
    PilotUserSpec("sante", "Responsable axe sante", "AX-SAN", "recherche", False),
    PilotUserSpec(
        "environnement", "Responsable axe environnement", "AX-ENV", "recherche", False
    ),
    PilotUserSpec(
        "securite", "Responsable axe securite alimentaire", "AX-SEC", "recherche", False
    ),
    PilotUserSpec(
        "societe", "Responsable axe sciences sociales", "AX-SOC", "recherche", False
    ),
    PilotUserSpec(
        "qualite", "Responsable bonnes pratiques de laboratoire", "GLP", "labo", False
    ),
    PilotUserSpec(
        "patrimoine", "Responsable patrimoine et logistique", "PAT", "i2a", False
    ),
    PilotUserSpec(
        "stations",
        "Responsable stations, bureaux et logements",
        "STA",
        "patrimoine",
        False,
    ),
    PilotUserSpec("drd", "Direction recherche et developpement", "DRD-DIR", "dg", False),
    PilotUserSpec("uar", "Responsable unite d'appui a la recherche", "UAR", "drd", False),
    PilotUserSpec(
        "ressources", "Responsable gestion technique des ressources", "UGT", "drd", False
    ),
    PilotUserSpec(
        "capitalisation",
        "Responsable capitalisation et valorisation",
        "CAP",
        "drv",
        False,
    ),
    PilotUserSpec(
        "biodiversite", "Responsable axe biodiversite", "AX-BIO", "recherche", False
    ),
    PilotUserSpec(
        "agriculture",
        "Responsable axe agriculture et nutrition",
        "AX-AGR",
        "recherche",
        False,
    ),
    PilotUserSpec("moyens", "Responsable cellule moyens generaux", "MG", "rh", False),
)

UNIT_SPECS = (
    ("CSRS-DEMO", "CSRS", None),
    ("DG", "Direction generale", "CSRS-DEMO"),
    ("DAF", "Direction administrative et financiere", "DG"),
    ("DRV", "Direction de la valorisation et des expertises", "DG"),
    ("DRD-DIR", "Direction recherche et developpement", "DG"),
    ("FIN", "Comptabilite, finances et caisse", "DAF"),
    ("TSI", "Technologies et systemes d'information", "DAF"),
    ("FOR", "Formation et renforcement des capacites", "DRV"),
    ("VAL", "Valorisation et partenariats", "DRV"),
    ("CT", "Conseillers techniques", "DG"),
    ("RSE", "Communication institutionnelle et RSE", "DG"),
    ("GEI", "Genre, equite et inclusion", "DG"),
    ("ETH", "Ethique", "DG"),
    ("SE", "Suivi et evaluation", "DG"),
    ("CG", "Controle de gestion", "DG"),
    ("RH", "Ressources humaines et moyens generaux", "DAF"),
    ("I2A", "Intendance, accueil et assistance", "DAF"),
    ("ACH", "Achats et approvisionnements", "DAF"),
    ("DOC", "Documentation et archives", "DAF"),
    ("DRD", "Coordination de la recherche scientifique", "DRD-DIR"),
    ("CLIN", "Recherche clinique", "DRD-DIR"),
    ("OBS", "Observatoires", "DRD-DIR"),
    ("LAB", "Laboratoire central", "DRD-DIR"),
    ("MIC", "Microscopie", "DRD-DIR"),
    ("AX-SAN", "Axe sante", "DRD"),
    ("AX-ENV", "Axe environnement", "DRD"),
    ("AX-SEC", "Axe securite alimentaire", "DRD"),
    ("AX-SOC", "Axe sciences sociales", "DRD"),
    ("GLP", "Bonnes pratiques de laboratoire", "LAB"),
    ("PAT", "Patrimoine et logistique", "I2A"),
    ("STA", "Stations, bureaux et logements", "PAT"),
    ("UAR", "Unite d'appui a la recherche", "DRD-DIR"),
    ("UGT", "Gestion technique des ressources", "DRD-DIR"),
    ("CAP", "Capitalisation et valorisation", "DRV"),
    ("AX-BIO", "Axe biodiversite", "DRD"),
    ("AX-AGR", "Axe agriculture et nutrition", "DRD"),
    ("MG", "Moyens generaux", "RH"),
)

LEGACY_EMAILS = (
    "responsable.demo@example.invalid",
    "observateur.demo@example.invalid",
    "employe.demo@example.invalid",
)

ProgressHistoryItem = tuple[int, int, bool, str]


def vary_progress_history(
    history: tuple[ProgressHistoryItem, ...], *, variant: int
) -> tuple[ProgressHistoryItem, ...]:
    """Return a deterministic, credible variant of a progression history.

    Args:
        history: Base dated percentages for one task scenario.
        variant: Stable employee index used to vary dates and intermediate values.

    Returns:
        A new history with the same scenario shape. Final 100 percent observations
        remain final, while dates and other percentages vary by small increments.

    """
    day_shift = variant % 4
    percentage_shift = ((variant // 4) - 1) * 5
    return tuple(
        (
            offset + day_shift,
            percentage
            if percentage == 100
            else max(0, min(95, percentage + percentage_shift)),
            blocked,
            note,
        )
        for offset, percentage, blocked, note in history
    )


class Command(BaseCommand):
    help = "Cree les comptes et douze semaines d'activite d'illustration."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--replace-legacy", action="store_true")
        parser.add_argument("--reset-password", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        demo_password = os.environ.get("CSRS_DEMO_PASSWORD", "")
        admin_password = os.environ.get("CSRS_ADMIN_PASSWORD", "")
        reset_password = cast(bool, options["reset_password"])
        existing_aliases = set(
            User.objects.filter(
                login_alias__in=[spec.alias for spec in PILOT_USERS]
            ).values_list("login_alias", flat=True)
        )
        credentials_required = reset_password or len(existing_aliases) != len(PILOT_USERS)
        if credentials_required or demo_password or admin_password:
            self._validate_passwords(demo_password, admin_password)
        dry_run = cast(bool, options["dry_run"])
        with transaction.atomic():
            if cast(bool, options["replace_legacy"]):
                self._delete_legacy_demo()
            units = self._ensure_units()
            users = self._ensure_users(
                demo_password,
                admin_password,
                reset_password=reset_password,
            )
            self._ensure_hierarchy(users, units)
            self._ensure_scenarios(users)
            self._assert_counts()
            if demo_password and admin_password:
                self._assert_authentication(users, demo_password, admin_password)
            else:
                self._assert_session_access(users)
            if dry_run:
                transaction.set_rollback(True)
        suffix = " (simulation annulee)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"illustration: users={len(PILOT_USERS)} reporting_lines={len(PILOT_USERS) - 2} assignments=73 proposals=42"
                + suffix
            )
        )

    @staticmethod
    def _validate_passwords(demo_password: str, admin_password: str) -> None:
        if not demo_password or not admin_password:
            raise CommandError(
                "CSRS_DEMO_PASSWORD et CSRS_ADMIN_PASSWORD sont obligatoires."
            )
        if demo_password == admin_password:
            raise CommandError(
                "Les mots de passe metier et administrateur doivent differer."
            )
        if len(demo_password) < 8 or len(admin_password) < 8:
            raise CommandError("Chaque mot de passe doit contenir au moins 8 caracteres.")

    @staticmethod
    def _delete_legacy_demo() -> None:
        legacy = User.objects.filter(email__in=LEGACY_EMAILS)
        legacy_ids = list(legacy.values_list("pk", flat=True))
        if not legacy_ids:
            return
        tasks = Task.objects.filter(
            Q(created_by_id__in=legacy_ids)
            | Q(assignments__employee_id__in=legacy_ids)
            | Q(assignments__manager_id__in=legacy_ids)
        ).distinct()
        tasks.delete()
        TaskProposal.objects.filter(
            Q(employee_id__in=legacy_ids) | Q(reviewed_by_id__in=legacy_ids)
        ).delete()
        NotificationDelivery.objects.filter(recipient_id__in=legacy_ids).delete()
        ReportingLine.objects.filter(
            Q(employee_id__in=legacy_ids) | Q(supervisor_id__in=legacy_ids)
        ).delete()
        legacy.delete()

    @staticmethod
    def _ensure_units() -> dict[str, OrganizationUnit]:
        units: dict[str, OrganizationUnit] = {}
        for code, name, parent_code in UNIT_SPECS:
            parent = units.get(parent_code) if parent_code else None
            unit, _ = OrganizationUnit.objects.update_or_create(
                code=code,
                defaults={"name": name, "parent": parent, "active": True},
            )
            units[code] = unit
        return units

    @staticmethod
    def _ensure_users(
        demo_password: str,
        admin_password: str,
        *,
        reset_password: bool,
    ) -> dict[str, User]:
        users: dict[str, User] = {}
        for spec in PILOT_USERS:
            is_admin = spec.alias == "dev"
            user, created = User.objects.update_or_create(
                email=spec.email,
                defaults={
                    "login_alias": spec.alias,
                    "position": spec.position,
                    "first_name": "",
                    "last_name": "",
                    "phone": "",
                    "is_active": True,
                    "is_staff": is_admin,
                    "is_superuser": is_admin,
                    "is_it_admin": is_admin,
                },
            )
            if created or reset_password or not user.has_usable_password():
                user.set_password(admin_password if is_admin else demo_password)
                user.save(update_fields=["password"])
            users[spec.alias] = user
        return users

    @staticmethod
    def _ensure_hierarchy(
        users: dict[str, User], units: dict[str, OrganizationUnit]
    ) -> None:
        start = week_start_for(timezone.localdate()) - timedelta(weeks=11)
        for spec in PILOT_USERS:
            if not spec.manager_alias or not spec.unit_code:
                continue
            line = set_primary_supervisor(
                employee=users[spec.alias],
                supervisor=users[spec.manager_alias],
                unit_id=units[spec.unit_code].pk,
                start_date=start,
            )
            if line.start_date != start:
                line.start_date = start
                line.save(update_fields=["start_date"])

    def _ensure_scenarios(self, users: dict[str, User]) -> None:
        current = week_start_for(timezone.localdate())
        start = current - timedelta(weeks=11)
        actions = self._ensure_action_plan(start)
        TaskActivity.objects.filter(assignment__task__code__startswith="PIL-").delete()
        ProgressEntry.objects.filter(assignment__task__code__startswith="PIL-").delete()
        subordinate_specs = [
            spec for spec in PILOT_USERS if spec.manager_alias and spec.has_scenarios
        ]
        for profile_variant, spec in enumerate(subordinate_specs):
            employee = users[spec.alias]
            manager = users[cast(str, spec.manager_alias)]
            assignments = [
                self._ensure_activity_task(
                    slot=slot,
                    employee=employee,
                    manager=manager,
                    action=actions[slot - 1],
                    start=start,
                    current=current,
                    profile_variant=profile_variant,
                )
                for slot in range(1, 6)
            ]
            self._ensure_proposals(
                employee, manager, actions[0], assignments[2], start, current
            )
        self._ensure_dg_tasks(users["dg"], actions, start, current)

    @staticmethod
    def _ensure_action_plan(monday: date) -> tuple[InstitutionalAction, ...]:
        StrategicPlan.objects.filter(name="Plan strategique fictif du pilote").update(
            name="Plan strategique institutionnel 2026-2028",
            start_date=monday,
            end_date=date(2028, 12, 31),
        )
        plan, _ = StrategicPlan.objects.update_or_create(
            name="Plan strategique institutionnel 2026-2028",
            defaults={"start_date": monday, "end_date": date(2028, 12, 31)},
        )
        action_plan, _ = ActionPlan.objects.update_or_create(
            code="PA-PILOTE",
            defaults={"name": "Organisation et performance", "strategic_plan": plan},
        )
        action_specs = (
            ("ACT-PLAN", "Planifier et coordonner"),
            ("ACT-PRIORITES", "Executer les priorites"),
            ("ACT-DOCUMENTATION", "Fiabiliser la documentation"),
            ("ACT-RESOLUTION", "Lever les points bloquants"),
            ("ACT-LIVRABLES", "Finaliser les livrables"),
        )
        actions: list[InstitutionalAction] = []
        for code, name in action_specs:
            action, _ = InstitutionalAction.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "action_plan": action_plan,
                    "active": True,
                },
            )
            actions.append(action)
        return tuple(actions)

    @staticmethod
    def _at(day: date, hour: int) -> datetime:
        """Return a timezone-aware business-hour timestamp."""
        return timezone.make_aware(datetime.combine(day, time(hour=hour)))

    @classmethod
    def _task(
        cls,
        *,
        code: str,
        title: str,
        employee: User,
        manager: User,
        action: InstitutionalAction,
        description: str,
        start_date: date,
        due_date: date,
        status: str,
        work_days: Decimal,
    ) -> tuple[TaskAssignment, bool]:
        from work.models import WorkCalendar, default_work_calendar_id

        calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
        normalized_due = calendar.due_date_for(start_date, work_days)
        completed_at = (
            cls._at(normalized_due, 16) if status == AssignmentStatus.COMPLETED else None
        )
        task, _ = Task.objects.update_or_create(
            code=code,
            defaults={
                "title": title,
                "description": description,
                "action": action,
                "created_by": manager,
            },
        )
        assignment, created = TaskAssignment.objects.update_or_create(
            task=task,
            employee=employee,
            defaults={
                "manager": manager,
                "start_date": start_date,
                "due_date": normalized_due,
                "estimated_work_days": work_days,
                "calendar": calendar,
                "status": status,
                "completed_at": completed_at,
            },
        )
        return assignment, created

    def _ensure_activity_task(
        self,
        *,
        slot: int,
        employee: User,
        manager: User,
        action: InstitutionalAction,
        start: date,
        current: date,
        profile_variant: int,
    ) -> TaskAssignment:
        """Create one role-based activity and its dated progress history."""
        alias = cast(str, employee.login_alias)
        subjects = (
            "Consolider le programme trimestriel",
            "Finaliser les priorites de la quinzaine",
            "Mettre a jour le dossier de reference",
            "Lever les points bloquants du service",
            "Rattraper les livrables en retard",
        )
        starts = (
            start,
            current - timedelta(weeks=1),
            start + timedelta(weeks=2),
            start + timedelta(weeks=5),
            start + timedelta(weeks=7),
        )
        dues = (
            current + timedelta(weeks=2),
            current + timedelta(days=11),
            start + timedelta(weeks=4, days=4),
            start + timedelta(weeks=7, days=4),
            start + timedelta(weeks=9, days=4),
        )
        statuses = (
            AssignmentStatus.ACTIVE,
            AssignmentStatus.ACTIVE,
            AssignmentStatus.COMPLETED,
            AssignmentStatus.COMPLETED,
            AssignmentStatus.ACTIVE,
        )
        work = ("65.00", "14.00", "20.00", "20.00", "10.00")
        assignment, _created = self._task(
            code=f"PIL-{alias.upper()}-{slot:02d}",
            title=subjects[slot - 1],
            description=(
                f"Coordonner les travaux relevant de {employee.position.lower()}, "
                "documenter les resultats obtenus et signaler rapidement les difficultes."
            ),
            employee=employee,
            manager=manager,
            action=action,
            start_date=starts[slot - 1],
            due_date=dues[slot - 1],
            status=statuses[slot - 1],
            work_days=Decimal(work[slot - 1]),
        )
        histories: tuple[tuple[int, int, bool, str], ...]
        if slot == 1:
            histories = tuple(
                (week * 7 + 1, value, False, note)
                for week, (value, note) in enumerate(
                    zip(
                        (5, 15, 25, 35, 45, 55, 65, 75, 80),
                        (
                            "Cadrage partage avec les personnes concernees.",
                            "Premier lot d'informations consolide.",
                            "Donnees principales verifiees.",
                            "Points de coordination traites.",
                            "Version intermediaire transmise.",
                            "Retours integres dans le dossier.",
                            "Controle interne en cours.",
                            "Derniers ajustements engages.",
                            "Livrable presque finalise.",
                        ),
                        strict=True,
                    )
                )
            )
        elif slot == 2:
            histories = (
                (1, 25, False, "Priorites confirmees pour la quinzaine."),
                (3, 25, False, "Progression stable pendant la collecte des validations."),
                (4, 45, False, "Premiers livrables disponibles pour revue."),
            )
        elif slot == 3:
            histories = (
                (1, 20, False, "Dossier ouvert et pieces rassemblees."),
                (8, 65, False, "Contenu relu avec le responsable."),
                (17, 100, False, "Dossier final transmis et classe."),
            )
        elif slot == 4:
            histories = (
                (1, 15, True, "Acces a une information necessaire indisponible."),
                (8, 35, True, "Solution temporaire identifiee avec le responsable."),
                (15, 75, False, "Acces retabli et travaux repris."),
                (18, 100, False, "Point bloque resolu et resultat livre."),
            )
        else:
            histories = (
                (
                    (1, 40, False, "Premiere remise preparee."),
                    (8, 100, False, "Livrable remis et valide."),
                    (15, 75, False, "Une anomalie constatee impose une reprise."),
                    (22, 85, False, "Correction appliquee; dernier controle en cours."),
                )
                if alias == "jardinier"
                else (
                    (1, 10, False, "Rattrapage organise par ordre de priorite."),
                    (8, 35, False, "Deux livrables sur cinq termines."),
                    (
                        15,
                        30,
                        False,
                        "Une verification a impose la reprise d'un livrable.",
                    ),
                    (22, 55, False, "Reprise terminee et calendrier actualise."),
                )
            )
        if not (slot == 5 and alias == "jardinier"):
            histories = vary_progress_history(histories, variant=profile_variant)
        for offset, percentage, blocked, note in histories:
            self._ensure_progress(
                assignment,
                employee,
                starts[slot - 1] + timedelta(days=offset),
                percentage,
                blocked,
                f"{note} Dossier {assignment.task.title.lower()} — {employee.position.lower()}.",
            )
        if slot == 5 and alias == "jardinier":
            TaskActivity.objects.create(
                assignment=assignment,
                kind=ActivityKind.VALIDATED,
                actor=manager,
                occurred_at=self._at(starts[slot - 1] + timedelta(days=8), 16),
                message="Achevement valide apres controle du programme d'entretien.",
                percentage_before=100,
                percentage_after=100,
            )
            TaskActivity.objects.create(
                assignment=assignment,
                kind=ActivityKind.REOPENED,
                actor=employee,
                occurred_at=self._at(starts[slot - 1] + timedelta(days=15), 9),
                message="Tache rouverte a 75 % : une zone doit etre reprise apres le controle.",
                percentage_before=100,
                percentage_after=75,
            )
        if slot in (1, 2, 4, 5):
            self._ensure_observation(
                assignment,
                employee,
                f"Pour {assignment.task.title.lower()}, j'ai regroupe les pieces liees a {employee.position.lower()}; je poursuis comme convenu.",
                starts[slot - 1] + timedelta(days=2),
                10,
            )
            self._ensure_observation(
                assignment,
                manager,
                f"Bien recu pour {assignment.task.title.lower()} et le volet {employee.position.lower()}. Garde les justificatifs et signale-moi tout ecart, stp.",
                starts[slot - 1] + timedelta(days=3),
                15,
            )
        return assignment

    def _ensure_progress(
        self,
        assignment: TaskAssignment,
        author: User,
        day: date,
        percentage: int,
        blocked: bool,
        note: str,
    ) -> None:
        entry, _created = ProgressEntry.objects.update_or_create(
            assignment=assignment,
            entry_date=day,
            defaults={
                "percentage": min(percentage, 100),
                "blocked": blocked,
                "note": note,
                "author": author,
            },
        )
        stamp = self._at(day, 11)
        ProgressEntry.objects.filter(pk=entry.pk).update(
            created_at=stamp, updated_at=stamp
        )
        historical = entry.history.order_by("-history_date").first()
        if historical is not None:
            entry.history.model.objects.filter(history_id=historical.history_id).update(
                history_date=stamp
            )
        if percentage == 100 and assignment.status == AssignmentStatus.COMPLETED:
            TaskAssignment.objects.filter(pk=assignment.pk).update(completed_at=stamp)
            assignment.completed_at = stamp
        TaskActivity.objects.create(
            assignment=assignment,
            kind=ActivityKind.PROGRESS,
            progress_entry=entry,
            actor=author,
            occurred_at=stamp,
            message=note,
            percentage_after=percentage,
        )

    def _ensure_observation(
        self, assignment: TaskAssignment, author: User, body: str, day: date, hour: int
    ) -> None:
        TaskActivity.objects.get_or_create(
            assignment=assignment,
            kind=ActivityKind.COMMENT,
            actor=author,
            message=body,
            defaults={"occurred_at": self._at(day, hour)},
        )

    def _ensure_proposals(
        self,
        employee: User,
        manager: User,
        action: InstitutionalAction,
        accepted_assignment: TaskAssignment,
        start: date,
        current: date,
    ) -> None:
        specs = (
            (
                "Optimiser le classement des livrables",
                ProposalStatus.ACCEPTED,
                start + timedelta(weeks=1),
                accepted_assignment,
                "",
            ),
            (
                "Mettre en place un point quotidien",
                ProposalStatus.REJECTED,
                start + timedelta(weeks=6),
                None,
                "Priorite reportee au prochain cycle de planification.",
            ),
            (
                "Formaliser le tableau de priorites",
                ProposalStatus.SUBMITTED,
                current + timedelta(days=1),
                None,
                "",
            ),
        )
        for subject, status, created_day, linked, reason in specs:
            title = subject
            proposal = TaskProposal.objects.filter(
                employee=employee, title__startswith=subject
            ).first()
            created = proposal is None
            if proposal is None:
                from work.models import WorkCalendar, default_work_calendar_id

                calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
                proposal = TaskProposal.objects.create(
                    employee=employee,
                    title=title,
                    description="Organiser le travail, produire un resultat verifiable et partager les points d'attention.",
                    action=action,
                    start_date=created_day,
                    due_date=calendar.due_date_for(created_day, Decimal("4.00")),
                    estimated_work_days=Decimal("4.00"),
                    calendar=calendar,
                )
            created_stamp = self._at(created_day, 9)
            if created:
                TaskProposal.objects.filter(pk=proposal.pk).update(
                    created_at=created_stamp
                )
            changed = (
                proposal.title != title
                or proposal.action_id != action.pk
                or proposal.status != status
                or proposal.accepted_assignment_id != (linked.pk if linked else None)
                or proposal.decision_note != reason
            )
            if changed:
                proposal.title = title
                proposal.action = action
                proposal.status = status
                proposal.accepted_assignment = linked
                proposal.reviewed_by = (
                    manager if status != ProposalStatus.SUBMITTED else None
                )
                proposal.decision_note = reason
                proposal.decided_at = (
                    self._at(created_day + timedelta(days=3), 14)
                    if status != ProposalStatus.SUBMITTED
                    else None
                )
                proposal.save()

    def _ensure_dg_tasks(
        self,
        dg: User,
        actions: tuple[InstitutionalAction, ...],
        start: date,
        current: date,
    ) -> None:
        specs = (
            (
                "Suivre les engagements de la direction",
                start,
                current + timedelta(weeks=2),
                AssignmentStatus.ACTIVE,
                "65.00",
                (10, 35, 60, 80),
            ),
            (
                "Arbitrer les priorites institutionnelles",
                current - timedelta(weeks=1),
                current + timedelta(days=11),
                AssignmentStatus.ACTIVE,
                "14.00",
                (20, 45),
            ),
            (
                "Valider la note d'orientation trimestrielle",
                start + timedelta(weeks=3),
                start + timedelta(weeks=5),
                AssignmentStatus.COMPLETED,
                "20.00",
                (25, 70, 100),
            ),
        )
        for slot, (title, task_start, due, status, work, values) in enumerate(specs, 1):
            assignment, _created = self._task(
                code=f"PIL-DG-{slot:02d}",
                title=title,
                description="Examiner les informations consolidees, consigner les arbitrages et suivre leur execution.",
                employee=dg,
                manager=dg,
                action=actions[(slot - 1) % len(actions)],
                start_date=task_start,
                due_date=due,
                status=status,
                work_days=Decimal(work),
            )
            for step, value in enumerate(values):
                day = task_start + timedelta(days=step * 7 + 1)
                self._ensure_progress(
                    assignment,
                    dg,
                    day,
                    value,
                    False,
                    f"Point de direction a {value} % pour {title.lower()}; les prochaines actions sont confirmees.",
                )
            self._ensure_observation(
                assignment,
                dg,
                f"Les arbitrages concernant {title.lower()} sont consignes dans le dossier de suivi.",
                task_start + timedelta(days=2),
                16,
            )

    @staticmethod
    def _assert_counts() -> None:
        aliases = [spec.alias for spec in PILOT_USERS]
        users = User.objects.filter(login_alias__in=aliases)
        if users.count() != len(PILOT_USERS):
            raise CommandError("Le nombre de comptes d'illustration est incoherent.")
        user_ids = users.values_list("pk", flat=True)
        lines = ReportingLine.objects.filter(
            employee_id__in=user_ids, is_primary=True, end_date__isnull=True
        )
        if lines.count() != len(PILOT_USERS) - 2:
            raise CommandError(
                "Le nombre de rattachements d'illustration est incoherent."
            )
        assignments = TaskAssignment.objects.filter(task__code__startswith="PIL-")
        if assignments.count() != 73:
            raise CommandError("Le nombre d'affectations d'illustration n'est pas 73.")
        proposals = TaskProposal.objects.filter(employee__login_alias__in=aliases)
        if proposals.count() != 42:
            raise CommandError("Le nombre de propositions d'illustration n'est pas 42.")
        if TaskActivity.objects.filter(assignment__in=assignments).count() < 100:
            raise CommandError("L'historique d'observations est incomplet.")

    @staticmethod
    def _assert_authentication(
        users: dict[str, User], demo_password: str, admin_password: str
    ) -> None:
        for alias, user in users.items():
            password = admin_password if alias == "dev" else demo_password
            if authenticate(username=alias.upper(), password=password) != user:
                raise CommandError(f"Echec de connexion par alias pour {alias}.")
            if authenticate(username=user.email.upper(), password=password) != user:
                raise CommandError(f"Echec de connexion par email pour {alias}.")
        Command._assert_session_access(users, demo_password)

    @staticmethod
    def _assert_session_access(
        users: dict[str, User], demo_password: str | None = None
    ) -> None:
        """Verify representative dashboards without requiring stored credentials."""
        host = (
            "csrs.koba.sarl"
            if "csrs.koba.sarl" in settings.ALLOWED_HOSTS
            else "testserver"
        )
        storage = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
        with override_settings(STORAGES=storage):
            for alias in ("dg", "daf", "kpon", "atall", "jardinier"):
                client = Client()
                if demo_password:
                    if not client.login(username=alias, password=demo_password):
                        raise CommandError(f"Echec de session pour {alias}.")
                else:
                    client.force_login(users[alias])
                response = client.get("/", secure=True, HTTP_HOST=host)
                if response.status_code != 200:
                    raise CommandError(
                        f"Tableau de bord indisponible pour {alias}: {response.status_code}."
                    )
