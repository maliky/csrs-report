"""Core CSRS work-tracking data model."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from math import ceil

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords


class OrganizationUnit(models.Model):
    """A service, department, or nested organizational unit."""

    long_name = models.CharField("nom long", max_length=180)
    short_name = models.CharField("nom court", max_length=80)
    code = models.CharField("code", max_length=32, unique=True)
    kind = models.CharField("type d'unite", max_length=32, default="unit")
    display_order = models.PositiveIntegerField("ordre d'affichage", default=0)
    active = models.BooleanField("active", default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["display_order", "long_name"]

    def __str__(self) -> str:
        suffix = " [archivee]" if not self.active else ""
        return f"{self.code} — {self.long_name}{suffix}"


class OrganizationUnitLink(models.Model):
    """A directed dependency from a supervising service to a collaborator."""

    supervisor_service = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="collaborator_links",
    )
    collaborator_service = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="supervisor_links",
    )
    history = HistoricalRecords()

    class Meta:
        ordering = [
            "supervisor_service__code",
            "collaborator_service__code",
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(supervisor_service=models.F("collaborator_service")),
                name="organization_unit_link_distinct_services",
            ),
            models.UniqueConstraint(
                fields=["supervisor_service", "collaborator_service"],
                name="unique_organization_unit_link",
            ),
            models.UniqueConstraint(
                fields=["collaborator_service"],
                name="one_parent_per_organization_unit",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.supervisor_service.code} → {self.collaborator_service.code}"

    def clean(self) -> None:
        """Reject a directed link that would introduce a service cycle."""
        super().clean()
        if not self.supervisor_service_id or not self.collaborator_service_id:
            return
        if self.supervisor_service_id == self.collaborator_service_id:
            raise ValidationError("Un service ne peut pas dependre de lui-meme.")
        links = OrganizationUnitLink.objects.all()
        if self.pk:
            links = links.exclude(pk=self.pk)
        if links.filter(collaborator_service_id=self.collaborator_service_id).exists():
            raise ValidationError(
                {
                    "collaborator_service": (
                        "Cette unite possede deja une unite superieure. "
                        "Modifiez son rattachement existant."
                    )
                }
            )
        edges: dict[int, set[int]] = {}
        for supervisor_id, collaborator_id in links.values_list(
            "supervisor_service_id", "collaborator_service_id"
        ):
            edges.setdefault(supervisor_id, set()).add(collaborator_id)
        frontier = [self.collaborator_service_id]
        visited: set[int] = set()
        while frontier:
            service_id = frontier.pop()
            if service_id == self.supervisor_service_id:
                raise ValidationError(
                    "Ce lien creerait une boucle dans la hierarchie des services."
                )
            if service_id in visited:
                continue
            visited.add(service_id)
            frontier.extend(edges.get(service_id, ()))

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class OrganizationMembership(models.Model):
    """A dated user membership in one organizational unit."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    unit = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    job_title = models.CharField("fonction dans le service", max_length=160, blank=True)
    start_date = models.DateField("debut", default=date.today)
    end_date = models.DateField("fin", null=True, blank=True)
    is_primary = models.BooleanField("appartenance principale", default=False)
    history = HistoricalRecords()

    class Meta:
        ordering = ["user", "-is_primary", "-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(end_date__gte=models.F("start_date")),
                name="organization_membership_valid_dates",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_primary=True, end_date__isnull=True),
                name="one_open_primary_membership",
            ),
        ]

    def __str__(self) -> str:
        qualifier = "principale" if self.is_primary else "secondaire"
        return f"{self.user} — {self.unit.code} ({qualifier})"

    def clean(self) -> None:
        """Reject overlapping primary memberships for the same person."""
        super().clean()
        if not self.user_id or not self.is_primary or not self.start_date:
            return
        memberships = OrganizationMembership.objects.filter(
            user_id=self.user_id,
            is_primary=True,
        )
        if self.pk:
            memberships = memberships.exclude(pk=self.pk)
        if self.end_date is not None:
            memberships = memberships.filter(start_date__lte=self.end_date)
        memberships = memberships.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=self.start_date)
        )
        if memberships.exists():
            raise ValidationError(
                "Deux appartenances principales ne peuvent pas se chevaucher."
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class ReportingLine(models.Model):
    """A dated manager-to-employee relationship."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reporting_lines"
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supervised_lines",
    )
    unit = models.ForeignKey(
        OrganizationUnit, on_delete=models.PROTECT, related_name="reporting_lines"
    )
    start_date = models.DateField("debut", default=date.today)
    end_date = models.DateField("fin", null=True, blank=True)
    is_primary = models.BooleanField("responsable principal", default=False)
    history = HistoricalRecords()

    class Meta:
        ordering = ["employee", "-is_primary", "-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(employee=models.F("supervisor")),
                name="reporting_line_distinct_people",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(end_date__gte=models.F("start_date")),
                name="reporting_line_valid_dates",
            ),
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(is_primary=True, end_date__isnull=True),
                name="one_active_primary_supervisor",
            ),
        ]

    def __str__(self) -> str:
        qualifier = "principal" if self.is_primary else "secondaire"
        return f"{self.employee} → {self.supervisor} ({qualifier})"

    def clean(self) -> None:
        """Reject cycles and inconsistent employee service membership."""
        super().clean()
        if not self.employee_id or not self.supervisor_id:
            return
        if self.employee_id == self.supervisor_id:
            raise ValidationError("Une personne ne peut pas etre son propre responsable.")
        edges: dict[int, set[int]] = {}
        lines = ReportingLine.objects.filter(end_date__isnull=True)
        if self.pk:
            lines = lines.exclude(pk=self.pk)
        for manager_id, employee_id in lines.values_list("supervisor_id", "employee_id"):
            edges.setdefault(manager_id, set()).add(employee_id)
        frontier = [self.employee_id]
        visited = {self.employee_id}
        while frontier:
            person_id = frontier.pop()
            for child_id in edges.get(person_id, set()):
                if child_id == self.supervisor_id:
                    raise ValidationError(
                        "Le rattachement creerait une boucle hierarchique."
                    )
                if child_id not in visited:
                    visited.add(child_id)
                    frontier.append(child_id)
        if self.unit_id and self.start_date:
            memberships = OrganizationMembership.objects.filter(
                user_id=self.employee_id,
                unit_id=self.unit_id,
                start_date__lte=self.start_date,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=self.start_date))
            if not memberships.exists():
                raise ValidationError(
                    {"unit": "Le collaborateur doit appartenir a ce service."}
                )


class StrategicPlan(models.Model):
    name = models.CharField("nom", max_length=220)
    start_date = models.DateField("debut")
    end_date = models.DateField("fin")
    active = models.BooleanField("actif", default=True)

    def __str__(self) -> str:
        return self.name


class ActionPlan(models.Model):
    strategic_plan = models.ForeignKey(
        StrategicPlan, on_delete=models.PROTECT, related_name="action_plans"
    )
    name = models.CharField("nom", max_length=220)
    code = models.CharField("code", max_length=40, unique=True)

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class InstitutionalAction(models.Model):
    action_plan = models.ForeignKey(
        ActionPlan, on_delete=models.PROTECT, related_name="actions"
    )
    name = models.CharField("nom", max_length=220)
    code = models.CharField("code", max_length=40, unique=True)
    active = models.BooleanField("active", default=True)

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class TaskCodeSequence(models.Model):
    """Transactional counter used to generate task codes per action and year."""

    action = models.ForeignKey(
        InstitutionalAction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="code_sequences",
    )
    year = models.PositiveSmallIntegerField("annee")
    next_value = models.PositiveIntegerField("prochain numero", default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["action", "year"],
                condition=Q(action__isnull=False),
                name="one_task_sequence_per_action_year",
            ),
            models.UniqueConstraint(
                fields=["year"],
                condition=Q(action__isnull=True),
                name="one_unclassified_task_sequence_per_year",
            ),
        ]


class WorkCalendar(models.Model):
    """Versioned working calendar retained by historical assignments."""

    name = models.CharField("nom", max_length=120)
    version = models.CharField("version", max_length=32)
    is_default = models.BooleanField("calendrier par defaut", default=False)
    active = models.BooleanField("actif", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "version"], name="unique_work_calendar_version"
            ),
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="one_default_work_calendar",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.version})"

    def is_working_day(self, day: date) -> bool:
        """Return the configured value, falling back to Monday through Friday."""
        override = (
            self.days.filter(day=day).values_list("is_working_day", flat=True).first()
        )
        return bool(override) if override is not None else day.weekday() < 5

    def due_date_for(self, start: date, workload: Decimal) -> date:
        """Return the workday reached after the start for the rounded-up workload."""
        remaining = ceil(workload)
        cursor = start
        while remaining:
            cursor += timedelta(days=1)
            if self.is_working_day(cursor):
                remaining -= 1
        return cursor

    def workdays_between(self, start: date, end: date) -> int:
        """Count working days after start through end, including end."""
        if end <= start:
            return 0
        cursor = start + timedelta(days=1)
        total = 0
        while cursor <= end:
            total += int(self.is_working_day(cursor))
            cursor += timedelta(days=1)
        return total


class WorkCalendarDay(models.Model):
    """One explicit non-working holiday or exceptional working day."""

    calendar = models.ForeignKey(
        WorkCalendar, on_delete=models.CASCADE, related_name="days"
    )
    day = models.DateField("date")
    name = models.CharField("libelle", max_length=180)
    is_working_day = models.BooleanField("jour ouvre", default=False)

    class Meta:
        ordering = ["day"]
        constraints = [
            models.UniqueConstraint(
                fields=["calendar", "day"], name="one_override_per_calendar_day"
            )
        ]

    def __str__(self) -> str:
        nature = "ouvre" if self.is_working_day else "non ouvre"
        return f"{self.day:%d/%m/%Y} — {self.name} ({nature})"

    def clean(self) -> None:
        """Freeze calendar overrides as soon as the version is referenced."""
        super().clean()
        if self.calendar_id and self.calendar.assignments.exists():
            raise ValidationError(
                "Ce calendrier est deja utilise; clonez-le pour le modifier."
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


def default_work_calendar_id() -> int:
    """Return a stable default calendar, creating the development fallback if needed."""
    calendar = WorkCalendar.objects.filter(is_default=True).first()
    if calendar is None:
        calendar, _created = WorkCalendar.objects.get_or_create(
            name="Cote d'Ivoire",
            version="2026.1",
            defaults={"is_default": True, "active": True},
        )
        if not calendar.is_default:
            WorkCalendar.objects.exclude(pk=calendar.pk).update(is_default=False)
            WorkCalendar.objects.filter(pk=calendar.pk).update(is_default=True)
            calendar.is_default = True
    return calendar.pk


class AssignmentStatus(models.TextChoices):
    PLANNED = "planned", "Planifiee"
    ACTIVE = "active", "En cours"
    AWAITING_VALIDATION = "awaiting_validation", "A valider"
    COMPLETED = "completed", "Terminee"
    CLOSED_EARLY = "closed_early", "Cloturee avant achevement"


class RecurrenceFrequency(models.TextChoices):
    WEEKLY = "weekly", "Chaque semaine"


class RecurrenceStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FINISHED = "finished", "Terminee"
    CANCELLED = "cancelled", "Annulee"


class Task(models.Model):
    """Reusable task definition shared by one or more assignments."""

    code = models.CharField("code interne", max_length=40, unique=True)
    title = models.CharField("nom court", max_length=180)
    description = models.TextField("description")
    action = models.ForeignKey(
        InstitutionalAction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_tasks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class TaskRecurrence(models.Model):
    """Template and lifecycle for a weekly series of task assignments."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="task_recurrences",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_task_recurrences",
    )
    title = models.CharField("nom court", max_length=180)
    description = models.TextField("description")
    action = models.ForeignKey(
        InstitutionalAction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="task_recurrences",
    )
    calendar = models.ForeignKey(
        WorkCalendar,
        on_delete=models.PROTECT,
        related_name="task_recurrences",
    )
    estimated_work_days = models.DecimalField(
        "charge estimee en jours",
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.1"))],
    )
    frequency = models.CharField(
        max_length=16,
        choices=RecurrenceFrequency.choices,
        default=RecurrenceFrequency.WEEKLY,
    )
    anchor_start_date = models.DateField("date d'ancrage")
    end_date = models.DateField("fin inclusive")
    status = models.CharField(
        max_length=16,
        choices=RecurrenceStatus.choices,
        default=RecurrenceStatus.ACTIVE,
    )
    revision = models.PositiveBigIntegerField(default=1)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_task_recurrences",
    )
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def clean(self) -> None:
        super().clean()
        if self.frequency != RecurrenceFrequency.WEEKLY:
            raise ValidationError(
                {"frequency": "Seule la repetition hebdomadaire est prise en charge."}
            )
        if (
            self.anchor_start_date
            and self.end_date
            and self.end_date < self.anchor_start_date + timedelta(days=7)
        ):
            raise ValidationError(
                {"end_date": "La date de fin doit permettre au moins une repetition."}
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def __str__(self) -> str:
        return self.title


class TaskAssignment(models.Model):
    """Individual ownership, schedule, and state for a task."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments")
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="task_assignments",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="managed_assignments",
    )
    organization_unit = models.ForeignKey(
        OrganizationUnit,
        null=True,
        on_delete=models.PROTECT,
        related_name="task_assignments",
        verbose_name="service historique",
    )
    calendar = models.ForeignKey(
        WorkCalendar,
        on_delete=models.PROTECT,
        related_name="assignments",
        default=default_work_calendar_id,
    )
    start_date = models.DateField("debut")
    due_date = models.DateField("echeance")
    estimated_work_days = models.DecimalField(
        "charge estimee en jours",
        max_digits=10,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.1"))],
    )
    status = models.CharField(
        "etat",
        max_length=24,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.PLANNED,
    )
    closed_reason = models.TextField("motif de cloture", blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveBigIntegerField(default=1)
    recurrence = models.ForeignKey(
        TaskRecurrence,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    recurrence_occurrence = models.PositiveIntegerField(null=True, blank=True)
    recurrence_anchor_date = models.DateField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["due_date", "task__title"]
        constraints = [
            models.CheckConstraint(
                condition=Q(due_date__gte=models.F("start_date")),
                name="assignment_due_after_start",
            ),
            models.UniqueConstraint(
                fields=["task", "employee"], name="unique_task_employee_assignment"
            ),
            models.UniqueConstraint(
                fields=["recurrence", "recurrence_occurrence"],
                condition=Q(recurrence__isnull=False),
                name="unique_task_recurrence_occurrence",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.task} — {self.employee}"

    def clean(self) -> None:
        """Reject schedules that diverge from the retained working calendar."""
        super().clean()
        if not self.start_date or not self.due_date or not self.estimated_work_days:
            return
        calendar = self.calendar
        expected = calendar.due_date_for(self.start_date, self.estimated_work_days)
        if self.due_date != expected:
            raise ValidationError(
                {
                    "due_date": (
                        "L'echeance doit correspondre a la date de debut, a la charge "
                        f"et au calendrier retenu ({expected:%d/%m/%Y})."
                    )
                }
            )

    def save(self, *args: object, **kwargs: object) -> None:
        """Guarantee schedule coherence for every application write path."""
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class ProposalStatus(models.TextChoices):
    SUBMITTED = "submitted", "Soumise"
    ACCEPTED = "accepted", "Validee"
    REJECTED = "rejected", "Rejetee"


class TaskProposal(models.Model):
    """Employee task proposal reviewed by the primary manager."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_proposals"
    )
    organization_unit = models.ForeignKey(
        OrganizationUnit,
        null=True,
        on_delete=models.PROTECT,
        related_name="task_proposals",
        verbose_name="service historique",
    )
    title = models.CharField("nom court", max_length=180)
    description = models.TextField("description")
    action = models.ForeignKey(
        InstitutionalAction, null=True, blank=True, on_delete=models.PROTECT
    )
    calendar = models.ForeignKey(
        WorkCalendar,
        on_delete=models.PROTECT,
        related_name="proposals",
        default=default_work_calendar_id,
    )
    start_date = models.DateField("debut")
    due_date = models.DateField("echeance")
    estimated_work_days = models.DecimalField(
        "charge estimee en jours", max_digits=10, decimal_places=4
    )
    status = models.CharField(
        max_length=16, choices=ProposalStatus.choices, default=ProposalStatus.SUBMITTED
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_proposals",
    )
    accepted_assignment = models.OneToOneField(
        TaskAssignment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_proposal",
    )
    recurrence_frequency = models.CharField(
        max_length=16,
        choices=RecurrenceFrequency.choices,
        blank=True,
    )
    recurrence_end_date = models.DateField(null=True, blank=True)
    accepted_recurrence = models.OneToOneField(
        TaskRecurrence,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accepted_proposal",
    )
    decision_note = models.TextField("motif", blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(due_date__gte=models.F("start_date")),
                name="proposal_due_after_start",
            )
        ]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        """Apply the same calendar invariant before a proposal can be accepted."""
        super().clean()
        if not self.start_date or not self.due_date or not self.estimated_work_days:
            return
        expected = self.calendar.due_date_for(self.start_date, self.estimated_work_days)
        if self.due_date != expected:
            raise ValidationError(
                {"due_date": f"L'echeance calculee est le {expected:%d/%m/%Y}."}
            )
        if self.recurrence_frequency:
            if self.recurrence_frequency != RecurrenceFrequency.WEEKLY:
                raise ValidationError(
                    {
                        "recurrence_frequency": "Seule la repetition hebdomadaire est prise en charge."
                    }
                )
            if not self.recurrence_end_date:
                raise ValidationError(
                    {"recurrence_end_date": "La date de fin est obligatoire."}
                )
            if self.recurrence_end_date < self.start_date + timedelta(days=7):
                raise ValidationError(
                    {
                        "recurrence_end_date": "La date de fin doit permettre au moins une repetition."
                    }
                )
            next_start = self.start_date + timedelta(days=7)
            while not self.calendar.is_working_day(next_start):
                next_start += timedelta(days=1)
            if self.due_date >= next_start:
                raise ValidationError(
                    {"estimated_work_days": "La charge fait chevaucher deux occurrences."}
                )
        elif self.recurrence_end_date:
            raise ValidationError(
                {"recurrence_frequency": "La frequence de repetition est obligatoire."}
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class ProgressEntry(models.Model):
    """One mutable daily observation; history retains saved corrections."""

    assignment = models.ForeignKey(
        TaskAssignment, on_delete=models.CASCADE, related_name="progress_entries"
    )
    entry_date = models.DateField("date")
    percentage = models.PositiveSmallIntegerField(
        "avancement",
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    note = models.TextField("observation", blank=True)
    blocked = models.BooleanField("blocage", default=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["entry_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "entry_date"],
                name="one_progress_per_assignment_day",
            )
        ]

    def __str__(self) -> str:
        return f"{self.assignment}: {self.percentage}% ({self.entry_date})"


class ProgressSeriesCache(models.Model):
    """Rebuildable JSON projection used only to accelerate chart reads."""

    assignment = models.OneToOneField(
        TaskAssignment,
        on_delete=models.CASCADE,
        related_name="progress_series_cache",
    )
    schema_version = models.PositiveSmallIntegerField(default=1)
    through_date = models.DateField("serie calculee jusqu'au")
    payload = models.JSONField(default=list)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["assignment_id"]

    def __str__(self) -> str:
        return f"Cache progression {self.assignment_id} au {self.through_date}"


class ActivityKind(models.TextChoices):
    PROGRESS = "progress", "Progression"
    COMMENT = "comment", "Observation"
    VALIDATED = "validated", "Achevement valide"
    REJECTED = "rejected", "Reprise demandee"
    REOPENED = "reopened", "Tache rouverte"
    CLOSED = "closed", "Tache cloturee"
    SCHEDULE = "schedule", "Planification modifiee"
    RECURRENCE = "recurrence", "Repetition"


class TaskActivity(models.Model):
    """Append-only user-facing activity stream for one assignment."""

    assignment = models.ForeignKey(
        TaskAssignment, on_delete=models.CASCADE, related_name="activities"
    )
    kind = models.CharField("type", max_length=24, choices=ActivityKind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_activities"
    )
    occurred_at = models.DateTimeField("date", default=timezone.now)
    message = models.TextField("observation")
    percentage_before = models.PositiveSmallIntegerField(null=True, blank=True)
    percentage_after = models.PositiveSmallIntegerField(null=True, blank=True)
    progress_entry = models.ForeignKey(
        ProgressEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    details = models.JSONField(default=dict, blank=True)
    supersedes = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )

    class Meta:
        ordering = ["occurred_at", "pk"]
        indexes = [models.Index(fields=["assignment", "occurred_at"])]

    def save(self, *args: object, **kwargs: object) -> None:
        """Prevent edits while allowing creation of a correcting successor."""
        if self.pk:
            raise ValidationError("Une activite publiee ne peut pas etre modifiee.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class ReportingDeletionKind(models.TextChoices):
    TASK_BATCH = "task_batch", "Suppression groupee de taches"
    REPORTING_RESET = "reporting_reset", "Reinitialisation du reporting"


class ReportingDeletionAuditQuerySet(models.QuerySet["ReportingDeletionAudit"]):
    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Un journal de suppression ne peut pas etre supprime.")


class ReportingDeletionAudit(models.Model):
    """Immutable minimal witness retained after destructive reporting cleanup."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reporting_deletion_audits",
    )
    kind = models.CharField(max_length=24, choices=ReportingDeletionKind.choices)
    reason = models.TextField("motif")
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ReportingDeletionAuditQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk:
            raise ValidationError("Un journal de suppression ne peut pas etre modifie.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Un journal de suppression ne peut pas etre supprime.")


class Holiday(models.Model):
    """Institution-maintained non-working day for Côte d'Ivoire."""

    day = models.DateField("date", unique=True)
    name = models.CharField("libelle", max_length=180)

    class Meta:
        ordering = ["day"]

    def __str__(self) -> str:
        return f"{self.day:%d/%m/%Y} — {self.name}"


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    SENT = "sent", "Envoyee"
    FAILED = "failed", "Echec definitif"


class NotificationDelivery(models.Model):
    """Bounded email outbox without verification codes or exposed credentials."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    event_type = models.CharField("evenement", max_length=32)
    subject = models.CharField("sujet", max_length=180)
    body = models.TextField("message")
    status = models.CharField(
        max_length=12,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error_type = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    def __str__(self) -> str:
        return f"{self.event_type} — {self.status}"
