"""Account email services."""

from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import HttpRequest
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import User


def activation_url(request: HttpRequest, user: User) -> str:
    """Build a one-time account activation URL."""
    path = reverse(
        "activate",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    return request.build_absolute_uri(path)


def send_activation(request: HttpRequest, user: User) -> int:
    """Send an activation link without logging its token."""
    url = activation_url(request, user)
    return send_mail(
        "Activation de votre compte CSRS Report",
        (
            f"Bonjour {user.get_full_name() or user.email},\n\n"
            "Le service IT a cree votre compte CSRS Report. "
            f"Choisissez votre mot de passe avec ce lien :\n{url}\n\n"
            "Si vous n'attendiez pas ce message, contactez le service IT."
        ),
        None,
        [user.email],
        fail_silently=False,
    )
