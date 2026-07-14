import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import User


@pytest.mark.django_db
def test_activation_link_sets_initial_password(client) -> None:
    user = User.objects.create_user("new.user@example.test")
    assert not user.has_usable_password()
    url = reverse(
        "activate",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    password = f"Aa9!{get_random_string(20)}"
    response = client.post(
        url,
        {"new_password1": password, "new_password2": password},
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password(password)


@pytest.mark.django_db
def test_authentication_accepts_alias_or_email_case_insensitively() -> None:
    password = f"Aa9!{get_random_string(20)}"
    user = User.objects.create_user(
        "pilot.user@demo.invalid", password, login_alias="pilot"
    )
    assert authenticate(username="PILOT", password=password) == user
    assert authenticate(username="PILOT.USER@DEMO.INVALID", password=password) == user
    assert authenticate(username="unknown", password=password) is None


@pytest.mark.django_db
def test_alias_is_normalized_and_unique_without_case_ambiguity() -> None:
    first = User.objects.create_user("first@demo.invalid", login_alias="Pilot-One")
    assert first.login_alias == "pilot-one"
    second = User(email="second@demo.invalid", login_alias="PILOT-ONE")
    with pytest.raises(ValidationError):
        second.full_clean()


@pytest.mark.django_db
def test_login_page_labels_both_accepted_identifiers(client) -> None:
    content = client.get(reverse("login")).content.decode()
    assert "Email ou identifiant" in content
    assert "mot de passe" in content
    assert 'name="password"' in content
    assert 'type="password"' in content
