from django.test import Client
from django.urls import reverse

from accounts.models import User


def test_react_shell_requires_a_session() -> None:
    response = Client().get(reverse("react-app"))

    assert response.status_code == 302
    assert response.url.startswith("/connexion/")


def test_react_shell_supports_client_side_routes(people: dict[str, User]) -> None:
    client = Client()
    client.force_login(people["employee"])

    response = client.get("/app/taches/31/")

    assert response.status_code == 200
    assert b'/static/react/assets/app.js' in response.content
    assert b'id="root"' in response.content
