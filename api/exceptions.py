from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from work.services import StaleRevisionError, StaleSelectionError

logger = logging.getLogger(__name__)


def _field_messages(data: Any) -> tuple[str, dict[str, list[str]]]:
    """Normalize DRF and Django validation shapes for the React client."""
    if isinstance(data, Mapping):
        fields = {
            str(key): [str(item) for item in value]
            if isinstance(value, (list, tuple))
            else [str(value)]
            for key, value in data.items()
        }
        first = next((messages[0] for messages in fields.values() if messages), "")
        return first or "Les données envoyées sont invalides.", fields
    if isinstance(data, (list, tuple)):
        messages = [str(item) for item in data]
        return (messages[0] if messages else "Requête invalide."), {}
    return str(data), {}


def api_exception_handler(exc: Exception, context: dict[str, object]) -> Response:
    """Return one predictable error envelope for every API endpoint."""
    if isinstance(exc, StaleRevisionError):
        return Response(
            {
                "error": {
                    "code": "stale_revision",
                    "message": str(exc),
                    "fields": {"revision": [str(exc.current_revision)]},
                }
            },
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, StaleSelectionError):
        return Response(
            {
                "error": {
                    "code": "stale_selection",
                    "message": str(exc),
                    "fields": {
                        "assignments": [
                            ",".join(str(item) for item in exc.assignment_ids)
                        ]
                    },
                }
            },
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, DjangoValidationError):
        data: Any = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        message, fields = _field_messages(data)
        return Response(
            {
                "error": {
                    "code": "validation_error",
                    "message": message,
                    "fields": fields,
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    response = exception_handler(exc, context)
    if response is None:
        logger.error(
            "Unhandled API exception",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return Response(
            {
                "error": {
                    "code": "server_error",
                    "message": "Le serveur n'a pas pu traiter cette demande.",
                    "fields": {},
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    message, fields = _field_messages(response.data)
    code = {
        400: "validation_error",
        401: "not_authenticated",
        403: "forbidden",
        404: "not_found",
    }.get(response.status_code, "request_error")
    response.data = {"error": {"code": code, "message": message, "fields": fields}}
    return response
