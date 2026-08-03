"""Auditable workflow records shared by the typed business processes."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from access.models import GrantScope, ScopedRole
from work.models import OrganizationUnit, WorkCalendar


class CaseStatus(models.TextChoices):
    DRAFT = "draft", "Brouillon"
    ASSISTANCE = "assistance", "Préparation par l'assistance"
    SIGNATURE = "signature", "Décision du DG"
    DISTRIBUTION = "distribution", "Distribution"
    FLEET = "fleet", "Préparation du véhicule"
    COMPLETED = "completed", "Terminé"
    REJECTED = "rejected", "Rejeté"
    ABANDONED = "abandoned", "Abandonné"


TERMINAL_CASE_STATUSES = frozenset(
    {CaseStatus.COMPLETED, CaseStatus.REJECTED, CaseStatus.ABANDONED}
)


class QueueKind(models.TextChoices):
    ASSISTANCE = "assistance", "Assistance"
    SIGNATURE = "signature", "Signature DG"
    DISTRIBUTION = "distribution", "Secrétariat et distribution"
    FLEET = "fleet", "Parc automobile"


class WorkItemStatus(models.TextChoices):
    OPEN = "open", "À prendre"
    CLAIMED = "claimed", "Pris en charge"
    COMPLETED = "completed", "Traité"
    CANCELED = "canceled", "Annulé"


class ScanStatus(models.TextChoices):
    PENDING = "pending", "Analyse en attente"
    CLEAN = "clean", "Sain"
    INFECTED = "infected", "Infecté"
    ERROR = "error", "Analyse impossible"


class MissionType(models.TextChoices):
    DOMESTIC = "domestic", "Mission nationale"
    INTERNATIONAL = "international", "Mission internationale"


class DocumentKind(models.TextChoices):
    TERMS_OF_REFERENCE = "terms_of_reference", "Termes de référence"
    INVITATION = "invitation", "Invitation"
    TICKET = "ticket", "Billet de transport"
    ORDER_DRAFT = "order_draft", "Projet d'ordre de mission"
    OTHER = "other", "Autre pièce"


class ProcessDefinition(models.Model):
    """One immutable workflow vocabulary version."""

    code = models.CharField(max_length=48)
    version = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=160)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "version"], name="unique_process_definition_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version} — {self.name}"


class ProcessQueue(models.Model):
    """A service queue routed by role and organizational coverage."""

    definition = models.ForeignKey(
        ProcessDefinition, on_delete=models.PROTECT, related_name="queues"
    )
    kind = models.CharField(max_length=20, choices=QueueKind.choices)
    name = models.CharField(max_length=160)
    role = models.ForeignKey(
        ScopedRole, on_delete=models.PROTECT, related_name="process_queues"
    )
    handler_unit = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="handled_process_queues",
    )
    coverage_unit = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="covered_process_queues",
    )
    coverage_scope = models.CharField(
        max_length=8, choices=GrantScope.choices, default=GrantScope.UNIT_TREE
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["definition", "kind", "name", "pk"]
        indexes = [models.Index(fields=["definition", "kind", "active"])]

    def __str__(self) -> str:
        return f"{self.definition.code} — {self.name}"


class ProcessCase(models.Model):
    """One authoritative workflow dossier with optimistic revision control."""

    definition = models.ForeignKey(
        ProcessDefinition, on_delete=models.PROTECT, related_name="cases"
    )
    reference = models.CharField(max_length=40, unique=True)
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="initiated_process_cases",
    )
    origin_unit = models.ForeignKey(
        OrganizationUnit, on_delete=models.PROTECT, related_name="process_cases"
    )
    origin_unit_name = models.CharField(max_length=220)
    status = models.CharField(
        max_length=20, choices=CaseStatus.choices, default=CaseStatus.DRAFT
    )
    current_step = models.CharField(max_length=32, default=CaseStatus.DRAFT)
    revision = models.PositiveIntegerField(default=1)
    calendar = models.ForeignKey(
        WorkCalendar, on_delete=models.PROTECT, related_name="process_cases"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateField(null=True, blank=True)
    legal_hold = models.BooleanField(default=False)
    legal_hold_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "current_step"]),
            models.Index(fields=["initiator", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(legal_hold=False) | ~Q(legal_hold_reason=""),
                name="process_legal_hold_has_reason",
            )
        ]

    def __str__(self) -> str:
        return self.reference


class MissionOrder(models.Model):
    """Typed mission-order fields kept outside the common workflow core."""

    case = models.OneToOneField(
        ProcessCase, on_delete=models.CASCADE, related_name="mission_order"
    )
    mission_type = models.CharField(max_length=20, choices=MissionType.choices)
    destination = models.CharField(max_length=220)
    purpose = models.TextField()
    itinerary = models.TextField(blank=True)
    transport_mode = models.CharField(max_length=120, blank=True)
    transport_company = models.CharField(max_length=160, blank=True)
    departure_date = models.DateField()
    return_date = models.DateField()
    funding_source = models.CharField(max_length=220, blank=True)
    costs_covered = models.TextField(blank=True)
    vehicle_required = models.BooleanField(default=False)
    vehicle_details = models.TextField(blank=True)
    official_number = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["case"]
        constraints = [
            models.CheckConstraint(
                condition=Q(return_date__gte=models.F("departure_date")),
                name="mission_return_not_before_departure",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.return_date and self.departure_date:
            if self.return_date < self.departure_date:
                raise ValidationError(
                    {"return_date": "La date de retour doit suivre le départ."}
                )
        if not self.destination.strip():
            raise ValidationError({"destination": "La destination est obligatoire."})
        if not self.purpose.strip():
            raise ValidationError({"purpose": "Le motif est obligatoire."})

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class MissionParticipant(models.Model):
    case = models.ForeignKey(
        ProcessCase, on_delete=models.CASCADE, related_name="mission_participants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mission_participations",
    )
    name_snapshot = models.CharField(max_length=220)
    position_snapshot = models.CharField(max_length=180, blank=True)

    class Meta:
        ordering = ["name_snapshot", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "user"], name="unique_mission_participant"
            )
        ]


class ProcessWorkItem(models.Model):
    case = models.ForeignKey(
        ProcessCase, on_delete=models.PROTECT, related_name="work_items"
    )
    queue = models.ForeignKey(
        ProcessQueue, on_delete=models.PROTECT, related_name="work_items"
    )
    step = models.CharField(max_length=32, choices=QueueKind.choices)
    status = models.CharField(
        max_length=12, choices=WorkItemStatus.choices, default=WorkItemStatus.OPEN
    )
    due_date = models.DateField()
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="claimed_process_work_items",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [
            models.Index(fields=["queue", "status", "due_date"]),
            models.Index(fields=["claimed_by", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(Q(claimed_by__isnull=True) & Q(claimed_at__isnull=True))
                | (Q(claimed_by__isnull=False) & Q(claimed_at__isnull=False)),
                name="process_claim_has_actor_and_date",
            )
        ]


class ProcessEventQuerySet(models.QuerySet["ProcessEvent"]):
    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Un événement de dossier ne peut pas être supprimé.")


class ProcessEvent(models.Model):
    """Append-only, human-readable business audit event."""

    case = models.ForeignKey(ProcessCase, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="process_events",
    )
    kind = models.CharField(max_length=40)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    message = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = ProcessEventQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "pk"]
        indexes = [models.Index(fields=["case", "occurred_at"])]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk:
            raise ValidationError("Un événement de dossier ne peut pas être modifié.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Un événement de dossier ne peut pas être supprimé.")


class ProcessDocument(models.Model):
    case = models.ForeignKey(
        ProcessCase, on_delete=models.PROTECT, related_name="documents"
    )
    kind = models.CharField(max_length=32, choices=DocumentKind.choices)
    provider = models.CharField(max_length=20)
    object_key = models.CharField(max_length=500, unique=True)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_status = models.CharField(max_length=12, choices=ScanStatus.choices)
    scan_details = models.CharField(max_length=240, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_process_documents",
    )
    replaced_by = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replaces",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["case", "kind", "scan_status"])]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk:
            raise ValidationError("Une pièce enregistrée ne peut pas être modifiée.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Une pièce enregistrée ne peut pas être supprimée.")


class ProcessSignature(models.Model):
    case = models.OneToOneField(
        ProcessCase, on_delete=models.PROTECT, related_name="signature"
    )
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="process_signatures",
    )
    event = models.OneToOneField(
        ProcessEvent, on_delete=models.PROTECT, related_name="signature"
    )
    confirmation = models.CharField(max_length=120)
    snapshot = models.JSONField()
    snapshot_sha256 = models.CharField(max_length=64)
    document_manifest = models.JSONField()
    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-signed_at"]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk:
            raise ValidationError("Une signature ne peut pas être modifiée.")
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError("Une signature ne peut pas être supprimée.")
