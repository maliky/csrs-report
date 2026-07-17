from rest_framework.authentication import SessionAuthentication


class CsrfSessionAuthentication(SessionAuthentication):
    """Use Django sessions while returning HTTP 401 for anonymous API calls."""

    def authenticate_header(self, request: object) -> str:
        return "Session"
