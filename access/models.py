"""Audited roles delegated within an organizational scope."""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from work.models import OrganizationUnit


class GrantScope(models.TextChoices):
    UNIT_ONLY = "unit", "Ce service uniquement"
    UNIT_TREE = "tree", "Ce service et ses sous-services"


class ScopedRole(models.Model):
    """A versioned business role backed by a Django permission group."""

    code = models.CharField("code", max_length=40, unique=True)
    name = models.CharField("nom", max_length=120)
    description = models.TextField("description", blank=True)
    active = models.BooleanField("actif", default=True)
    group = models.OneToOneField(
        Group,
        on_delete=models.PROTECT,
        related_name="scoped_role",
        verbose_name="groupe de permissions",
    )

    class Meta:
        ordering = ["code"]
        permissions = [
            ("view_unit_scope", "Consulter les donnees d'un service"),
            ("manage_unit_assignments", "Gerer les taches d'un service"),
            ("correct_unit_progress", "Corriger la progression d'un service"),
            ("review_unit_proposals", "Decider les propositions d'un service"),
            ("export_unit_data", "Exporter les donnees d'un service"),
            ("view_process_scope", "Consulter les dossiers d'un service"),
            ("work_mission_assistance", "Preparer les ordres de mission"),
            ("sign_mission_order", "Signer les ordres de mission"),
            ("work_mission_distribution", "Distribuer les ordres de mission"),
            ("work_mission_fleet", "Preparer les vehicules de mission"),
            ("export_process", "Exporter un dossier de processus"),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class RoleGrantQuerySet(models.QuerySet["RoleGrant"]):
    """Reusable validity filter evaluated for every authorization request."""

    def active_at(self, at: datetime) -> "RoleGrantQuerySet":
        return (
            self.filter(
                user__is_active=True,
                role__active=True,
                unit__active=True,
                valid_from__lte=at,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=at))
            .filter(Q(revoked_at__isnull=True) | Q(revoked_at__gt=at))
        )

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError(
            "Une delegation doit etre revoquee et ne peut pas etre supprimee."
        )


class RoleGrant(models.Model):
    """One revocable role delegated to a user for a unit and time window."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="role_grants",
    )
    role = models.ForeignKey(
        ScopedRole,
        on_delete=models.PROTECT,
        related_name="grants",
    )
    unit = models.ForeignKey(
        OrganizationUnit,
        on_delete=models.PROTECT,
        related_name="role_grants",
    )
    scope = models.CharField(
        "portee", max_length=8, choices=GrantScope.choices, default=GrantScope.UNIT_TREE
    )
    valid_from = models.DateTimeField("valide a partir de", default=timezone.now)
    valid_until = models.DateTimeField("valide jusqu'au", null=True, blank=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="granted_role_grants",
    )
    grant_reason = models.TextField("motif de l'attribution")
    revoked_at = models.DateTimeField("revoquee le", null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="revoked_role_grants",
    )
    revoke_reason = models.TextField("motif de la revocation", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    objects = RoleGrantQuerySet.as_manager()

    class Meta:
        ordering = ["-valid_from", "user", "role"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True)
                | Q(valid_until__gt=models.F("valid_from")),
                name="role_grant_valid_window",
            ),
            models.CheckConstraint(
                condition=(Q(revoked_at__isnull=True) & Q(revoked_by__isnull=True))
                | (Q(revoked_at__isnull=False) & Q(revoked_by__isnull=False)),
                name="role_grant_revocation_actor",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "valid_from", "valid_until"]),
            models.Index(fields=["unit", "role"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.role.code} — {self.unit.code}"

    def clean(self) -> None:
        """Validate the auditable grant and revocation metadata."""
        super().clean()
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValidationError(
                {"valid_until": "La fin doit suivre le debut de la delegation."}
            )
        if not self.grant_reason.strip():
            raise ValidationError({"grant_reason": "Le motif est obligatoire."})
        if self.revoked_at is not None:
            if self.revoked_by_id is None:
                raise ValidationError({"revoked_by": "Indiquez l'auteur."})
            if not self.revoke_reason.strip():
                raise ValidationError(
                    {"revoke_reason": "Le motif de revocation est obligatoire."}
                )
        elif self.revoked_by_id is not None or self.revoke_reason.strip():
            raise ValidationError("Une revocation doit avoir une date, un auteur et un motif.")
        if self.user_id and self.role_id and self.unit_id and self.revoked_at is None:
            overlaps = RoleGrant.objects.filter(
                user_id=self.user_id,
                role_id=self.role_id,
                unit_id=self.unit_id,
                scope=self.scope,
                revoked_at__isnull=True,
            ).exclude(pk=self.pk)
            overlaps = overlaps.filter(
                Q(valid_until__isnull=True) | Q(valid_until__gt=self.valid_from)
            )
            if self.valid_until is not None:
                overlaps = overlaps.filter(valid_from__lt=self.valid_until)
            if overlaps.exists():
                raise ValidationError(
                    "Une delegation equivalente couvre deja cette periode."
                )

    def save(self, *args: object, **kwargs: object) -> None:
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        del args, kwargs
        raise ValidationError(
            "Une delegation doit etre revoquee et ne peut pas etre supprimee."
        )
