"""User model for institution-managed accounts."""

from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager["User"]):
    """Create users identified by their email address."""

    use_in_migrations = True

    def create_user(
        self, email: str, password: str | None = None, **extra: object
    ) -> "User":
        if not email:
            raise ValueError("Une adresse email est obligatoire.")
        user = self.model(email=self.normalize_email(email), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email: str, password: str | None = None, **extra: object
    ) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_it_admin", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("Un superutilisateur doit avoir is_staff et is_superuser.")
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    """Minimal CSRS user profile."""

    username = None  # type: ignore[assignment]
    email = models.EmailField("adresse email", unique=True)
    login_alias = models.CharField(
        "identifiant court",
        max_length=32,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^[a-z][a-z0-9_-]*$",
                message="Utilisez des lettres minuscules, chiffres, tirets ou underscores.",
            )
        ],
    )
    position = models.CharField("fonction", max_length=160, blank=True)
    phone = models.CharField("telephone", max_length=32, blank=True)
    phone_verified_at = models.DateTimeField(
        "telephone verifie le", null=True, blank=True
    )
    is_it_admin = models.BooleanField("administrateur IT", default=False)

    USERNAME_FIELD = "email"  # type: ignore[misc]
    REQUIRED_FIELDS: list[str] = []  # type: ignore[misc]

    objects = UserManager()  # type: ignore[misc,assignment]

    class Meta:
        ordering = ["last_name", "first_name", "email"]
        constraints = [
            models.UniqueConstraint(
                Lower("login_alias"),
                condition=models.Q(login_alias__isnull=False),
                name="unique_login_alias_ci",
            )
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        if self.login_alias:
            self.login_alias = self.login_alias.strip().lower()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    def __str__(self) -> str:
        return self.get_full_name() or self.position or self.login_alias or self.email
