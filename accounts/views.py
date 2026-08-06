"""Account activation views."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.tokens import default_token_generator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from accounts.forms import ActivationForm
from accounts.models import User


def activate(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Activate a pre-created account after validating the emailed token."""
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id, is_active=True)
    except (ValueError, TypeError, OverflowError, User.DoesNotExist) as error:
        raise Http404("Lien d'activation invalide.") from error
    if not default_token_generator.check_token(user, token):
        raise Http404("Lien d'activation invalide ou expire.")
    form = ActivationForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        login(request, user)
        messages.success(request, "Votre compte est active.")
        return redirect("react-app")
    return render(request, "accounts/activate.html", {"form": form})
