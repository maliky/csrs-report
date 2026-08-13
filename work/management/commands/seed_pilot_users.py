"""Load a safe organizational illustration with twelve weeks of activity."""

from __future__ import annotations

import os
from uuid import uuid4
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

from accounts.agenda_directions import classify_agenda_direction
from accounts.models import User
from access.models import GrantScope, RoleGrant, ScopedRole
from agenda.models import (
    AgendaDraft,
    AgendaVersion,
    StaffAvailability,
    VisitorVisit,
)
from processes.models import (
    ProcessCase,
    ProcessDocument,
    ProcessEvent,
    ProcessSignature,
    ProcessWorkItem,
)
from work.models import (
    ActionPlan,
    ActivityKind,
    AssignmentStatus,
    InstitutionalAction,
    NotificationDelivery,
    OrganizationUnit,
    OrganizationUnitLink,
    OrganizationMembership,
    ProgressEntry,
    ProgressSeriesCache,
    ProposalStatus,
    ReportingLine,
    StrategicPlan,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskProposal,
    WorkCalendar,
    default_work_calendar_id,
)
from work.pilot_scenarios import (
    EXPECTED_SCENARIO_COUNTS,
    IsWorkingDay,
    PilotScenario,
    ScenarioKind,
    build_pilot_scenario,
    scenario_counts,
)
from work.organogram import OrgUnitSpec, load_organogram
from work.progress_cache import rebuild_progress_caches
from work.services import set_primary_membership, set_primary_supervisor, week_start_for


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


ORGANOGRAM_SPECS = load_organogram()
UNIT_SPECS = tuple(
    (spec.code, spec.long_name, spec.parent_code) for spec in ORGANOGRAM_SPECS
)
UNIT_SHORT_NAMES = {spec.code: spec.short_name for spec in ORGANOGRAM_SPECS}
UNIT_PARENT_CODES = {spec.code: spec.parent_code for spec in ORGANOGRAM_SPECS}
UNIT_KINDS = {spec.code: spec.kind for spec in ORGANOGRAM_SPECS}

SCENARIO_ALIASES = {
    "agriculture",
    "atall",
    "biodiversite",
    "caissier",
    "communication",
    "comptable",
    "daf",
    "finances",
    "kpon",
    "labo",
    "programmes",
    "sante",
    "societe",
    "uar",
}


def _pilot_users_from_organogram(
    specs: tuple[OrgUnitSpec, ...],
) -> tuple[PilotUserSpec, ...]:
    by_code = {spec.code: spec for spec in specs}
    alias_by_code = {
        spec.code: spec.demo_alias for spec in specs if spec.demo_alias is not None
    }

    def manager_alias(spec: OrgUnitSpec) -> str | None:
        parent_code = spec.parent_code
        while parent_code is not None:
            alias = alias_by_code.get(parent_code)
            if alias is not None:
                return alias
            parent_code = by_code[parent_code].parent_code
        return None

    users: list[PilotUserSpec] = [
        PilotUserSpec("dev", "Administrateur technique", None, None, False)
    ]
    for spec in specs:
        if spec.demo_alias is None or spec.demo_position is None:
            continue
        users.append(
            PilotUserSpec(
                spec.demo_alias,
                spec.demo_position,
                spec.code,
                manager_alias(spec),
                spec.demo_alias in SCENARIO_ALIASES,
            )
        )
        if spec.code == "DG":
            users.append(
                PilotUserSpec(
                    "secretariat_dg",
                    "Secrétaire de la Direction générale",
                    "DG",
                    "dg",
                    False,
                )
            )
    return tuple(users)


PILOT_USERS = _pilot_users_from_organogram(ORGANOGRAM_SPECS)

LEGACY_EMAILS = (
    "responsable.demo@example.invalid",
    "observateur.demo@example.invalid",
    "employe.demo@example.invalid",
)

TASK_SUBJECTS = (
    "Consolider le programme mensuel",
    "Finaliser les priorités de la quinzaine",
    "Mettre à jour le registre des engagements",
    "Vérifier les pièces du dossier prioritaire",
    "Préparer la réunion de coordination",
    "Organiser la revue des livrables",
    "Actualiser le calendrier opérationnel",
    "Rapprocher les indicateurs du service",
    "Finaliser la note de synthèse",
    "Classer les justificatifs du trimestre",
    "Résoudre les points restés en attente",
    "Préparer le bilan de la période",
    "Mettre à jour le dossier de référence",
    "Documenter les décisions de coordination",
    "Vérifier la conformité des livrables",
    "Planifier les prochaines interventions",
    "Consolider les demandes des collaborateurs",
    "Finaliser le compte rendu de suivi",
    "Mettre en ordre les documents partagés",
    "Préparer le point avec la direction",
)

PROGRESS_MESSAGES = (
    "Le cadrage et les responsabilités ont été confirmés",
    "Les informations utiles ont été rassemblées et contrôlées",
    "Une première version exploitable a été produite",
    "Les retours des personnes concernées ont été intégrés",
    "Les derniers écarts ont été traités",
    "Le résultat attendu a été finalisé et transmis",
)

PILOT_PROPOSAL_TITLES = (
    "Optimiser le classement des livrables",
    "Mettre en place un point quotidien",
    "Formaliser le tableau de priorités",
)

LEGACY_PROPOSAL_TITLES = {
    "Formaliser le tableau de priorités": "Formaliser le tableau de priorites",
}


def pilot_service_short_name(user: User) -> str:
    """Return the configured service abbreviation for one pilot user."""
    alias = cast(str, user.login_alias)
    spec = next(item for item in PILOT_USERS if item.alias == alias)
    return UNIT_SHORT_NAMES.get(spec.unit_code or "", alias)


def pilot_actor_service_label(user: User) -> str:
    """Identify one pilot author while retaining the short service name."""
    alias = cast(str, user.login_alias)
    service = pilot_service_short_name(user)
    return service if alias == service else f"{alias} ({service})"


class Command(BaseCommand):
    help = "Cree les comptes et douze semaines d'activite d'illustration."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--replace-legacy", action="store_true")
        parser.add_argument("--reset-password", action="store_true")
        parser.add_argument("--refresh-scenarios-only", action="store_true")
        parser.add_argument("--prune-noncanonical-users", action="store_true")
        parser.add_argument("--confirm-prune", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        dry_run = cast(bool, options["dry_run"])
        refresh_only = cast(bool, options["refresh_scenarios_only"])
        prune_users = cast(bool, options["prune_noncanonical_users"])
        confirm_prune = cast(bool, options["confirm_prune"])
        if refresh_only:
            if (
                cast(bool, options["replace_legacy"])
                or cast(bool, options["reset_password"])
                or prune_users
                or confirm_prune
            ):
                raise CommandError(
                    "--refresh-scenarios-only est incompatible avec le remplacement "
                    "des comptes, leur purge ou les mots de passe."
                )
            users = self._existing_scenario_users()
            with transaction.atomic():
                self._ensure_scenarios(users)
                self._warm_progress_caches()
                self._assert_scenario_counts(tuple(users))
                self._assert_session_access(users)
                if dry_run:
                    transaction.set_rollback(True)
            suffix = " (simulation annulee)" if dry_run else ""
            self.stdout.write(
                self.style.SUCCESS(
                    f"scenarios actualises: users={len(users)} assignments=73 "
                    f"proposals=42{suffix}"
                )
            )
            return

        if confirm_prune and not prune_users:
            raise CommandError("--confirm-prune exige --prune-noncanonical-users.")
        if prune_users and not dry_run and not confirm_prune:
            raise CommandError(
                "La purge réelle exige --confirm-prune après une simulation et une "
                "sauvegarde vérifiée."
            )

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
        with transaction.atomic():
            retained_user_ids: dict[str, int] | None = None
            if prune_users:
                retained_user_ids = self._select_canonical_users()
                self._delete_noncanonical_users(retained_user_ids)
                self._prepare_retained_users(retained_user_ids)
            if cast(bool, options["replace_legacy"]):
                self._delete_legacy_demo()
            units = self._ensure_units()
            users = self._ensure_users(
                demo_password,
                admin_password,
                reset_password=reset_password,
                retained_user_ids=retained_user_ids,
            )
            self._ensure_hierarchy(users, units)
            self._ensure_agenda_roles(users, units)
            self._ensure_scenarios(users)
            self._warm_progress_caches()
            self._assert_counts()
            if prune_users:
                self._assert_exact_user_set()
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
    def _existing_scenario_users() -> dict[str, User]:
        """Load only accounts required to regenerate the 73 pilot assignments."""
        aliases = {"dg"}
        for spec in PILOT_USERS:
            if spec.manager_alias and spec.has_scenarios:
                aliases.add(spec.alias)
                aliases.add(spec.manager_alias)
        users = {
            cast(str, user.login_alias): user
            for user in User.objects.filter(login_alias__in=aliases)
        }
        missing = sorted(aliases - users.keys())
        if missing:
            raise CommandError(
                "Comptes requis absents pour les scenarios: " + ", ".join(missing)
            )
        return users

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
    def _select_canonical_users() -> dict[str, int]:
        """Select at most one retained row per canonical alias, preferring aliases."""
        retained: dict[str, int] = {}
        used_ids: set[int] = set()
        for spec in PILOT_USERS:
            user_id = (
                User.objects.filter(login_alias__iexact=spec.alias)
                .values_list("pk", flat=True)
                .first()
            )
            if user_id is not None:
                retained[spec.alias] = user_id
                used_ids.add(user_id)
        for spec in PILOT_USERS:
            if spec.alias in retained:
                continue
            user_id = (
                User.objects.filter(email__iexact=spec.email)
                .exclude(pk__in=used_ids)
                .values_list("pk", flat=True)
                .first()
            )
            if user_id is not None:
                retained[spec.alias] = user_id
                used_ids.add(user_id)
        return retained

    def _delete_noncanonical_users(self, retained_user_ids: dict[str, int]) -> None:
        """Delete every aggregate connected to users outside the canonical set."""
        retained_ids = set(retained_user_ids.values())
        targets = User.objects.exclude(pk__in=retained_ids)
        target_rows = list(targets.values_list("pk", "login_alias", "email"))
        if not target_rows:
            self.stdout.write("purge comptes: aucun compte non canonique")
            return
        target_ids = [row[0] for row in target_rows]

        task_ids = list(
            Task.objects.filter(
                Q(created_by_id__in=target_ids)
                | Q(assignments__employee_id__in=target_ids)
                | Q(assignments__manager_id__in=target_ids)
                | Q(assignments__progress_entries__author_id__in=target_ids)
                | Q(assignments__activities__actor_id__in=target_ids)
            )
            .distinct()
            .values_list("pk", flat=True)
        )
        proposals = TaskProposal.objects.filter(
            Q(employee_id__in=target_ids)
            | Q(reviewed_by_id__in=target_ids)
            | Q(accepted_assignment__task_id__in=task_ids)
        ).distinct()

        case_ids = list(
            ProcessCase.objects.filter(
                Q(initiator_id__in=target_ids)
                | Q(mission_participants__user_id__in=target_ids)
                | Q(work_items__claimed_by_id__in=target_ids)
                | Q(events__actor_id__in=target_ids)
                | Q(documents__uploaded_by_id__in=target_ids)
                | Q(signature__signer_id__in=target_ids)
            )
            .distinct()
            .values_list("pk", flat=True)
        )

        draft_ids = list(
            AgendaDraft.objects.filter(
                Q(updated_by_id__in=target_ids)
                | Q(versions__generated_by_id__in=target_ids)
            )
            .distinct()
            .values_list("pk", flat=True)
        )
        visits = VisitorVisit.objects.filter(
            Q(recorded_by_id__in=target_ids) | Q(updated_by_id__in=target_ids)
        ).distinct()
        availability = StaffAvailability.objects.filter(
            Q(employee_id__in=target_ids)
            | Q(recorded_by_id__in=target_ids)
            | Q(updated_by_id__in=target_ids)
        ).distinct()
        grants = RoleGrant._base_manager.filter(
            Q(user_id__in=target_ids)
            | Q(granted_by_id__in=target_ids)
            | Q(revoked_by_id__in=target_ids)
        ).distinct()

        counts = {
            "users": len(target_ids),
            "tasks": len(task_ids),
            "proposals": proposals.count(),
            "processes": len(case_ids),
            "agenda_drafts": len(draft_ids),
            "visits": visits.count(),
            "availability": availability.count(),
            "grants": grants.count(),
        }
        labels = sorted(alias or email for _, alias, email in target_rows)
        self.stdout.write(
            "purge comptes: "
            + " ".join(f"{name}={count}" for name, count in counts.items())
        )
        self.stdout.write("comptes non canoniques: " + ", ".join(labels))

        grants.delete()
        visits.delete()
        availability.delete()
        if draft_ids:
            AgendaVersion._base_manager.filter(draft_id__in=draft_ids).delete()
            AgendaDraft.objects.filter(pk__in=draft_ids).delete()

        if case_ids:
            ProcessSignature._base_manager.filter(case_id__in=case_ids).delete()
            ProcessDocument.objects.filter(replaced_by__case_id__in=case_ids).update(
                replaced_by=None
            )
            ProcessDocument.objects.filter(case_id__in=case_ids).update(replaced_by=None)
            ProcessDocument._base_manager.filter(case_id__in=case_ids).delete()
            ProcessEvent._base_manager.filter(case_id__in=case_ids).delete()
            ProcessWorkItem.objects.filter(case_id__in=case_ids).delete()
            ProcessCase.objects.filter(pk__in=case_ids).delete()

        proposals.delete()
        if task_ids:
            TaskActivity.objects.filter(
                supersedes__isnull=False,
            ).filter(
                Q(assignment__task_id__in=task_ids)
                | Q(supersedes__assignment__task_id__in=task_ids)
            ).update(supersedes=None)
            Task.objects.filter(pk__in=task_ids).delete()
        User.objects.filter(pk__in=target_ids).delete()

    @staticmethod
    def _prepare_retained_users(retained_user_ids: dict[str, int]) -> None:
        """Release aliases and emails so swaps can be normalized deterministically."""
        for user_id in retained_user_ids.values():
            User.objects.filter(pk=user_id).update(
                login_alias=None,
                email=f"reconcile-{user_id}-{uuid4().hex}@demo.invalid",
            )

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
        spec_by_code = {spec.code: spec for spec in ORGANOGRAM_SPECS}
        canonical_codes = set(spec_by_code)
        OrganizationUnit.objects.exclude(code__in=canonical_codes).update(active=False)
        for code, long_name, _parent_code in UNIT_SPECS:
            spec = spec_by_code[code]
            unit, _ = OrganizationUnit.objects.update_or_create(
                code=code,
                defaults={
                    "short_name": UNIT_SHORT_NAMES[code],
                    "long_name": long_name,
                    "kind": spec.kind,
                    "display_order": spec.display_order,
                    "active": True,
                },
            )
            units[code] = unit
        OrganizationUnitLink.objects.filter(
            collaborator_service__code__in=canonical_codes
        ).exclude(supervisor_service__code__in=canonical_codes).delete()
        for code, _long_name, supervisor_code in UNIT_SPECS:
            if supervisor_code is None:
                continue
            OrganizationUnitLink.objects.update_or_create(
                collaborator_service=units[code],
                defaults={"supervisor_service": units[supervisor_code]},
            )
            OrganizationUnitLink.objects.filter(collaborator_service=units[code]).exclude(
                supervisor_service=units[supervisor_code],
            ).delete()
        return units

    @staticmethod
    def _ensure_users(
        demo_password: str,
        admin_password: str,
        *,
        reset_password: bool,
        retained_user_ids: dict[str, int] | None = None,
    ) -> dict[str, User]:
        users: dict[str, User] = {}
        for spec in PILOT_USERS:
            is_admin = spec.alias == "dev"
            retained_id = (retained_user_ids or {}).get(spec.alias)
            if retained_id is None:
                user, created = User.objects.get_or_create(email=spec.email)
            else:
                user = User.objects.get(pk=retained_id)
                created = False
            user.email = spec.email
            user.login_alias = spec.alias
            user.position = spec.position
            user.first_name = ""
            user.last_name = ""
            user.phone = ""
            user.is_active = True
            user.is_staff = is_admin
            user.is_superuser = is_admin
            user.is_it_admin = is_admin
            if not user.agenda_direction and spec.unit_code:
                user.agenda_direction = classify_agenda_direction(
                    unit_code=spec.unit_code,
                    unit_kind=UNIT_KINDS[spec.unit_code],
                    parent_by_code=UNIT_PARENT_CODES,
                )
            if created or reset_password or not user.has_usable_password():
                user.set_password(admin_password if is_admin else demo_password)
            user.save()
            users[spec.alias] = user
        return users

    @staticmethod
    def _ensure_hierarchy(
        users: dict[str, User], units: dict[str, OrganizationUnit]
    ) -> None:
        start = week_start_for(timezone.localdate()) - timedelta(weeks=11)
        for spec in PILOT_USERS:
            if not spec.unit_code:
                continue
            set_primary_membership(
                user=users[spec.alias],
                unit_id=units[spec.unit_code].pk,
                start_date=start,
            )
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

    @staticmethod
    def _ensure_agenda_roles(
        users: dict[str, User], units: dict[str, OrganizationUnit]
    ) -> None:
        """Give the dedicated fictitious accounts their dated agenda roles."""
        dev = users["dev"]
        specs = (
            ("secretariat_dg", "AGENDA_SECRETARIAT", "DG"),
            ("rh", "AGENDA_HR", "CA"),
            ("dg", "AGENDA_VIEWER", "CA"),
        )
        valid_from = timezone.now() - timedelta(weeks=12)
        for alias, role_code, unit_code in specs:
            role = ScopedRole.objects.get(code=role_code)
            RoleGrant.objects.get_or_create(
                user=users[alias],
                role=role,
                unit=units[unit_code],
                scope=GrantScope.UNIT_TREE,
                revoked_at__isnull=True,
                defaults={
                    "valid_from": valid_from,
                    "granted_by": dev,
                    "grant_reason": "Rôle fictif du scénario d’agenda hebdomadaire.",
                },
            )

    def _ensure_scenarios(self, users: dict[str, User]) -> None:
        today = timezone.localdate()
        current = week_start_for(today)
        start = current - timedelta(weeks=11)
        actions = self._ensure_action_plan(start)
        calendar = WorkCalendar.objects.prefetch_related("days").get(
            pk=default_work_calendar_id()
        )
        overrides = {item.day: item.is_working_day for item in calendar.days.all()}

        def is_working_day(day: date) -> bool:
            return overrides.get(day, day.weekday() < 5)

        activities = TaskActivity.objects.filter(
            assignment__task__code__startswith="PIL-"
        )
        activities.filter(supersedes__isnull=False).update(supersedes=None)
        activities.delete()
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
                    scenario=build_pilot_scenario(
                        profile_variant * 5 + slot - 1,
                        today=today,
                        is_working_day=is_working_day,
                    ),
                    scenario_index=profile_variant * 5 + slot - 1,
                    calendar=calendar,
                )
                for slot in range(1, 6)
            ]
            self._ensure_proposals(
                employee, manager, actions[0], assignments[2], start, current
            )
        self._ensure_dg_tasks(users["dg"], actions, today, calendar, is_working_day)

    @staticmethod
    def _warm_progress_caches() -> None:
        """Persist derived graph rows after all canonical pilot history is loaded."""
        assignments = (
            TaskAssignment.objects.filter(task__code__startswith="PIL-")
            .select_related("calendar")
            .prefetch_related("calendar__days", "progress_entries")
        )
        rebuild_progress_caches(assignments)

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
            ("ACT-PRIORITES", "Exécuter les priorités"),
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
        scenario: PilotScenario,
        calendar: WorkCalendar,
    ) -> TaskAssignment:
        normalized_due = calendar.due_date_for(scenario.start_date, scenario.workload)
        if normalized_due != scenario.due_date:
            raise CommandError(
                f"Echeance incoherente pour {code}: {normalized_due} != "
                f"{scenario.due_date}."
            )
        status = cls._scenario_status(scenario)
        completed_at = (
            cls._at(scenario.completion_date, 16)
            if scenario.completion_date is not None
            else None
        )
        closed_reason = (
            "Le responsable a clôturé la tâche avant achèvement après avoir "
            "réorienté la priorité."
            if scenario.kind == ScenarioKind.CLOSED_EARLY
            else ""
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
        assignment, _created = TaskAssignment.objects.update_or_create(
            task=task,
            employee=employee,
            defaults={
                "manager": manager,
                "organization_unit": OrganizationMembership.objects.get(
                    user=employee,
                    is_primary=True,
                    end_date__isnull=True,
                ).unit,
                "start_date": scenario.start_date,
                "due_date": normalized_due,
                "estimated_work_days": scenario.workload,
                "calendar": calendar,
                "status": status,
                "closed_reason": closed_reason,
                "completed_at": completed_at,
            },
        )
        return assignment

    @staticmethod
    def _scenario_status(scenario: PilotScenario) -> str:
        if scenario.kind == ScenarioKind.CLOSED_EARLY:
            return AssignmentStatus.CLOSED_EARLY
        if scenario.kind in (
            ScenarioKind.ON_TIME,
            ScenarioKind.EARLY_COMPLETED,
            ScenarioKind.SLIGHT_LATE_COMPLETED,
            ScenarioKind.REOPENED_COMPLETED,
            ScenarioKind.BIG_LATE_COMPLETED,
        ):
            return AssignmentStatus.COMPLETED
        return AssignmentStatus.ACTIVE

    def _ensure_activity_task(
        self,
        *,
        slot: int,
        employee: User,
        manager: User,
        action: InstitutionalAction,
        scenario: PilotScenario,
        scenario_index: int,
        calendar: WorkCalendar,
    ) -> TaskAssignment:
        """Create one role-based activity and its dated progress history."""
        alias = cast(str, employee.login_alias)
        service = pilot_service_short_name(employee)
        title = TASK_SUBJECTS[scenario_index % len(TASK_SUBJECTS)]
        assignment = self._task(
            code=f"PIL-{alias.upper()}-{slot:02d}",
            title=title,
            description=(
                f"Produire un résultat vérifiable pour le service {service}, "
                "conserver les justificatifs utiles et partager les points "
                "d’attention avec le responsable."
            ),
            employee=employee,
            manager=manager,
            action=action,
            scenario=scenario,
            calendar=calendar,
        )
        self._materialize_scenario(assignment, employee, manager, scenario)
        self._ensure_conversation(assignment, employee, manager, scenario, scenario_index)
        return assignment

    def _materialize_scenario(
        self,
        assignment: TaskAssignment,
        employee: User,
        manager: User,
        scenario: PilotScenario,
    ) -> None:
        """Persist progress and lifecycle events from one immutable narrative."""
        previous = 0
        for stage_index, milestone in enumerate(scenario.milestones):
            note = self._progress_message(
                assignment,
                employee,
                stage_index,
                milestone.percentage,
                previous,
                milestone.blocked,
            )
            self._ensure_progress(
                assignment,
                employee,
                milestone.day,
                milestone.percentage,
                milestone.blocked,
                note,
                previous,
            )
            previous = milestone.percentage

        for validation_index, validation_day in enumerate(scenario.validation_dates):
            repeated_validation = len(scenario.validation_dates) > 1
            label = (
                "Première validation"
                if repeated_validation and validation_index == 0
                else "Validation finale"
                if repeated_validation
                else "Achèvement"
            )
            TaskActivity.objects.create(
                assignment=assignment,
                kind=ActivityKind.VALIDATED,
                actor=manager,
                occurred_at=self._at(validation_day, 16),
                message=(
                    f"{label} de {assignment.task.title.lower()} après contrôle "
                    f"du résultat produit par le service "
                    f"{pilot_actor_service_label(employee)}."
                ),
                percentage_before=100,
                percentage_after=100,
            )

        if scenario.reopen_date is not None:
            reopened_percentage = next(
                item.percentage
                for item in scenario.milestones
                if item.day == scenario.reopen_date
            )
            TaskActivity.objects.create(
                assignment=assignment,
                kind=ActivityKind.REOPENED,
                actor=employee,
                occurred_at=self._at(scenario.reopen_date, 12),
                message=(
                    f"{assignment.task.title} rouverte après le contrôle : une "
                    f"correction précise reste à mener par le service "
                    f"{pilot_actor_service_label(employee)}."
                ),
                percentage_before=100,
                percentage_after=reopened_percentage,
            )

        if scenario.close_date is not None:
            percentage = scenario.milestones[-1].percentage
            TaskActivity.objects.create(
                assignment=assignment,
                kind=ActivityKind.CLOSED,
                actor=manager,
                occurred_at=self._at(scenario.close_date, 16),
                message=(
                    f"{assignment.task.title} clôturée par le responsable avant "
                    "achèvement : la priorité a été réorientée et le travail produit "
                    f"par le service {pilot_actor_service_label(employee)} est conservé."
                ),
                percentage_before=percentage,
                percentage_after=percentage,
            )

    @staticmethod
    def _progress_message(
        assignment: TaskAssignment,
        employee: User,
        stage_index: int,
        percentage: int,
        previous: int,
        blocked: bool,
    ) -> str:
        if percentage < previous:
            event = "Une reprise ciblée a été ouverte après le contrôle"
        elif blocked:
            event = "Un accès nécessaire manque encore et le responsable est informé"
        else:
            event = PROGRESS_MESSAGES[min(stage_index, len(PROGRESS_MESSAGES) - 1)]
        return (
            f"{event} pour {assignment.task.title.lower()}, dans le cadre de "
            f"l’activité du service {pilot_actor_service_label(employee)}."
        )

    def _ensure_conversation(
        self,
        assignment: TaskAssignment,
        employee: User,
        manager: User,
        scenario: PilotScenario,
        scenario_index: int,
    ) -> None:
        first_day = scenario.milestones[0].day
        response_day = scenario.milestones[min(1, len(scenario.milestones) - 1)].day
        last_day = scenario.milestones[-1].day
        self._ensure_observation(
            assignment,
            employee,
            (
                f"Pour {assignment.task.title.lower()}, le service "
                f"{pilot_actor_service_label(employee)} a regroupé les pièces utiles "
                "et fixé le prochain point de suivi."
            ),
            first_day,
            9,
        )
        if scenario_index % 3:
            self._ensure_observation(
                assignment,
                manager,
                (
                    f"Le point sur {assignment.task.title.lower()} transmis par "
                    f"{pilot_actor_service_label(employee)} est bien reçu ; les "
                    "justificatifs sont à conserver et tout écart de calendrier "
                    "doit être signalé."
                ),
                response_day,
                15,
            )
        if scenario_index % 5 == 0:
            self._ensure_observation(
                assignment,
                employee,
                (
                    f"Le dossier de {assignment.task.title.lower()} tient maintenant "
                    f"compte du retour adressé au service "
                    f"{pilot_actor_service_label(employee)} et des pièces complémentaires."
                ),
                last_day,
                14,
            )

    def _ensure_progress(
        self,
        assignment: TaskAssignment,
        author: User,
        day: date,
        percentage: int,
        blocked: bool,
        note: str,
        previous: int,
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
        TaskActivity.objects.create(
            assignment=assignment,
            kind=ActivityKind.PROGRESS,
            progress_entry=entry,
            actor=author,
            occurred_at=stamp,
            message=note,
            percentage_before=previous,
            percentage_after=percentage,
        )

    def _ensure_observation(
        self, assignment: TaskAssignment, author: User, body: str, day: date, hour: int
    ) -> None:
        TaskActivity.objects.create(
            assignment=assignment,
            kind=ActivityKind.COMMENT,
            actor=author,
            message=body,
            occurred_at=self._at(day, hour),
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
                PILOT_PROPOSAL_TITLES[0],
                ProposalStatus.ACCEPTED,
                start + timedelta(weeks=1),
                accepted_assignment,
                "",
            ),
            (
                PILOT_PROPOSAL_TITLES[1],
                ProposalStatus.REJECTED,
                start + timedelta(weeks=6),
                None,
                "Priorité reportée au prochain cycle de planification.",
            ),
            (
                PILOT_PROPOSAL_TITLES[2],
                ProposalStatus.SUBMITTED,
                current + timedelta(days=1),
                None,
                "",
            ),
        )
        for subject, status, created_day, linked, reason in specs:
            title = subject
            legacy_title = LEGACY_PROPOSAL_TITLES.get(subject)
            title_filter = Q(title__startswith=subject)
            if legacy_title:
                title_filter |= Q(title__startswith=legacy_title)
            proposal = TaskProposal.objects.filter(
                title_filter, employee=employee
            ).first()
            created = proposal is None
            if proposal is None:
                calendar = WorkCalendar.objects.get(pk=default_work_calendar_id())
                proposal = TaskProposal.objects.create(
                    employee=employee,
                    organization_unit=OrganizationMembership.objects.get(
                        user=employee,
                        is_primary=True,
                        end_date__isnull=True,
                    ).unit,
                    title=title,
                    description=(
                        "Organiser le travail, produire un résultat vérifiable et "
                        "partager les points d’attention."
                    ),
                    action=action,
                    start_date=created_day,
                    due_date=calendar.due_date_for(created_day, Decimal("4.0")),
                    estimated_work_days=Decimal("4.0"),
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
        today: date,
        calendar: WorkCalendar,
        is_working_day: IsWorkingDay,
    ) -> None:
        specs = (
            ("Suivre les engagements de la direction", 71),
            ("Arbitrer les priorités institutionnelles", 70),
            ("Valider la note d'orientation trimestrielle", 72),
        )
        for slot, (title, scenario_index) in enumerate(specs, 1):
            scenario = build_pilot_scenario(
                scenario_index, today=today, is_working_day=is_working_day
            )
            assignment = self._task(
                code=f"PIL-DG-{slot:02d}",
                title=title,
                description=(
                    "Examiner les informations consolidées, consigner les arbitrages "
                    "et suivre leur exécution avec les directions concernées."
                ),
                employee=dg,
                manager=dg,
                action=actions[(slot - 1) % len(actions)],
                scenario=scenario,
                calendar=calendar,
            )
            self._materialize_scenario(assignment, dg, dg, scenario)
            self._ensure_conversation(assignment, dg, dg, scenario, scenario_index)

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
        memberships = OrganizationMembership.objects.filter(
            user_id__in=user_ids,
            is_primary=True,
            end_date__isnull=True,
        )
        if memberships.count() != len(PILOT_USERS) - 1:
            raise CommandError(
                "Le nombre d'appartenances organisationnelles est incoherent."
            )
        Command._assert_scenario_counts(tuple(aliases))

    @staticmethod
    def _assert_exact_user_set() -> None:
        expected = {(spec.alias, spec.email) for spec in PILOT_USERS}
        actual = set(User.objects.values_list("login_alias", "email"))
        if actual != expected:
            raise CommandError(
                "La base ne contient pas exactement les comptes canoniques attendus."
            )

    @staticmethod
    def _assert_scenario_counts(aliases: tuple[str, ...]) -> None:
        """Verify scenario data independently from optional extension accounts."""
        assignments = TaskAssignment.objects.filter(task__code__startswith="PIL-")
        if assignments.count() != 73:
            raise CommandError("Le nombre d'affectations d'illustration n'est pas 73.")
        if assignments.filter(organization_unit__isnull=True).exists():
            raise CommandError("Une affectation d'illustration n'a pas de service.")
        if scenario_counts() != EXPECTED_SCENARIO_COUNTS:
            raise CommandError("La repartition des scenarios est incoherente.")
        if assignments.filter(estimated_work_days__lte=Decimal("10.0")).count() != 65:
            raise CommandError("La repartition des charges courtes est incoherente.")
        proposals = TaskProposal.objects.filter(
            employee__login_alias__in=aliases,
            title__in=PILOT_PROPOSAL_TITLES,
        )
        if proposals.count() != 42:
            raise CommandError("Le nombre de propositions d'illustration n'est pas 42.")
        if proposals.filter(organization_unit__isnull=True).exists():
            raise CommandError("Une proposition d'illustration n'a pas de service.")
        if ProgressSeriesCache.objects.filter(assignment__in=assignments).count() != 73:
            raise CommandError("Le nombre de caches de progression n'est pas 73.")
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
        host = Command._dashboard_request_host()
        storage = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        }
        with override_settings(STORAGES=storage):
            for alias in ("dg", "daf", "kpon", "atall", "secretariat_dg", "rh"):
                if alias not in users:
                    continue
                client = Client()
                if demo_password:
                    if not client.login(username=alias, password=demo_password):
                        raise CommandError(f"Echec de session pour {alias}.")
                else:
                    client.force_login(users[alias])
                response = client.get("/app/", secure=True, HTTP_HOST=host)
                if response.status_code != 200:
                    raise CommandError(
                        f"Tableau de bord indisponible pour {alias}: {response.status_code}."
                    )

    @staticmethod
    def _dashboard_request_host() -> str:
        """Select a request host accepted by the current Django configuration."""
        allowed_hosts = [
            value.strip() for value in settings.ALLOWED_HOSTS if value.strip()
        ]
        external_host = next(
            (
                value
                for value in allowed_hosts
                if value not in {"localhost", "127.0.0.1", "testserver", "*"}
                and not value.startswith(".")
            ),
            None,
        )
        if external_host:
            return external_host
        if "*" in allowed_hosts:
            return "testserver"
        if allowed_hosts:
            return allowed_hosts[0].removeprefix(".")
        raise CommandError(
            "DJANGO_ALLOWED_HOSTS doit contenir au moins un nom d'hote "
            "pour verifier les tableaux de bord."
        )
