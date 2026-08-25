"""Audited inputs and immutable weekly agenda versions."""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords


class VisitorVisit(models.Model):
    """A visitor group recorded on arrival and closed when it leaves."""

    arrived_at = models.DateTimeField("arrivée", default=timezone.now)
    departed_at = models.DateTimeField("départ", null=True, blank=True)
    party_size = models.PositiveSmallIntegerField(
        "nombre de visiteurs", validators=[MinValueValidator(1)]
    )
    visitor_names = models.JSONField("noms facultatifs", default=list, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_visitor_visits",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_visitor_visits",
    )
    revision = models.PositiveBigIntegerField(default=1)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-arrived_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(departed_at__isnull=True)
                | Q(departed_at__gte=models.F("arrived_at")),
                name="visitor_departure_not_before_arrival",
            ),
            models.CheckConstraint(
                condition=(Q(cancelled_at__isnull=True) & Q(cancellation_reason=""))
                | (Q(cancelled_at__isnull=False) & ~Q(cancellation_reason="")),
                name="visitor_cancellation_has_reason",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.departed_at and self.arrived_at and self.departed_at < self.arrived_at:
            raise ValidationError({"departed_at": "Le départ doit suivre l’arrivée."})
        if not isinstance(self.visitor_names, list):
            raise ValidationError({"visitor_names": "La liste des noms est invalide."})
        names = [str(name).strip() for name in self.visitor_names if str(name).strip()]
        if any(len(name) > 160 for name in names):
            raise ValidationError(
                {"visitor_names": "Un nom ne peut pas dépasser 160 caractères."}
            )
        if len(names) > self.party_size:
            raise ValidationError(
                {"visitor_names": "Le nombre de noms dépasse le nombre de visiteurs."}
            )
        self.visitor_names = names
        if self.cancelled_at and not self.cancellation_reason.strip():
            raise ValidationError(
                {"cancellation_reason": "Le motif d’annulation est obligatoire."}
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class AvailabilityKind(models.TextChoices):
    LEAVE = "leave", "Congé"
    ABSENCE = "absence", "Absence"
    MISSION = "mission", "Mission"


class StaffAvailability(models.Model):
    """A dated leave, absence, or mission entered by Human Resources."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="availability_periods",
    )
    kind = models.CharField(max_length=12, choices=AvailabilityKind.choices)
    start_date = models.DateField("début")
    end_date = models.DateField("fin")
    note = models.TextField("observation", blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_availability_periods",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_availability_periods",
    )
    revision = models.PositiveBigIntegerField(default=1)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["start_date", "employee", "kind"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="availability_end_not_before_start",
            ),
            models.CheckConstraint(
                condition=(Q(cancelled_at__isnull=True) & Q(cancellation_reason=""))
                | (Q(cancelled_at__isnull=False) & ~Q(cancellation_reason="")),
                name="availability_cancellation_has_reason",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La fin doit suivre le début."})
        if (
            self.employee_id
            and self.start_date
            and self.end_date
            and not self.cancelled_at
        ):
            overlaps = StaffAvailability.objects.filter(
                employee_id=self.employee_id,
                cancelled_at__isnull=True,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError(
                    "Une autre indisponibilité active couvre déjà cette période."
                )
        if self.cancelled_at and not self.cancellation_reason.strip():
            raise ValidationError(
                {"cancellation_reason": "Le motif d’annulation est obligatoire."}
            )

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class AgendaDirection(models.TextChoices):
    PROGRAMS = "programs", "Direction des programmes"
    ADMINISTRATION = "administration", "Direction administrative"
    LEGACY = "legacy", "Agenda global historique"

    @classmethod
    def presentation_label(cls, value: str) -> str:
        """Return the user-facing title without changing persisted choices."""
        if value == cls.ADMINISTRATION:
            return "Agenda DAF"
        return str(cls(value).label)


class AgendaDraft(models.Model):
    """The shared secretary note for an inclusive reporting period."""

    period_start = models.DateField("début de période")
    period_end = models.DateField("fin de période")
    major_events = models.TextField("événements majeurs", blank=True)
    revision = models.PositiveBigIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_agenda_drafts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-period_start", "-period_end"]
        constraints = [
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F("period_start")),
                name="agenda_draft_end_not_before_start",
            ),
            models.UniqueConstraint(
                fields=["period_start", "period_end"],
                name="unique_agenda_draft_period",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.period_start and self.period_end:
            if self.period_end < self.period_start:
                raise ValidationError(
                    {"period_end": "La fin doit suivre le début de la période."}
                )
            if self.period_end - self.period_start > timedelta(days=30):
                raise ValidationError(
                    {"period_end": "La période ne peut pas dépasser 31 jours inclusifs."}
                )

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class AgendaVersionQuerySet(models.QuerySet["AgendaVersion"]):
    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Une version d’agenda générée ne peut pas être supprimée.")


class AgendaVersion(models.Model):
    """An append-only snapshot and its privately stored printable PDF."""

    draft = models.ForeignKey(
        AgendaDraft, on_delete=models.PROTECT, related_name="versions"
    )
    period_start = models.DateField("début de période")
    period_end = models.DateField("fin de période")
    agenda_direction = models.CharField(
        "direction",
        max_length=16,
        choices=AgendaDirection.choices,
    )
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    snapshot_sha256 = models.CharField(max_length=64)
    storage_provider = models.CharField(max_length=24)
    storage_key = models.CharField(max_length=500)
    pdf_sha256 = models.CharField(max_length=64)
    pdf_size = models.PositiveIntegerField()
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_agendas",
    )
    generated_at = models.DateTimeField(default=timezone.now)

    objects = AgendaVersionQuerySet.as_manager()

    class Meta:
        ordering = ["-period_start", "agenda_direction", "-version"]
        constraints = [
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F("period_start")),
                name="agenda_version_end_not_before_start",
            ),
            models.UniqueConstraint(
                fields=[
                    "period_start",
                    "period_end",
                    "agenda_direction",
                    "version",
                ],
                name="unique_agenda_version",
            ),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk:
            raise ValidationError(
                "Une version d’agenda générée ne peut pas être modifiée."
            )
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Une version d’agenda générée ne peut pas être supprimée.")


def period_days(period_start: date, period_end: date) -> int:
    return (period_end - period_start).days + 1
