"""Authentication by institutional email or short pilot alias."""

from __future__ import annotations

from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest
from django.db.models import Q

from accounts.models import User


class AliasOrEmailBackend(ModelBackend):
    """Authenticate case-insensitively with an email or a short alias."""

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: object,
    ) -> User | None:
        identifier = username or str(kwargs.get(User.USERNAME_FIELD, ""))
        if not identifier or password is None:
            return None
        try:
            user = User.objects.get(
                Q(email__iexact=identifier.strip())
                | Q(login_alias__iexact=identifier.strip())
            )
        except User.DoesNotExist:
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
