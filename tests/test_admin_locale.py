import pytest
from django.conf import settings
from django.urls import reverse

from accounts.models import User


@pytest.mark.django_db
def test_admin_stays_in_french_for_an_english_browser(client) -> None:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    login_response = client.get(reverse("login"), HTTP_ACCEPT_LANGUAGE="en")
    assert login_response.headers["Content-Language"] == "en"

    administrator = User.objects.create_superuser("admin@example.test")
    client.force_login(administrator)
    response = client.get(reverse("admin:index"), HTTP_ACCEPT_LANGUAGE="en")

    assert response.status_code == 200
    assert response.headers["Content-Language"] == "fr"
    content = response.content.decode()
    assert '<html lang="fr"' in content
    assert "Site d’administration" in content
