"""Private document storage and antivirus boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import socket
import struct
from typing import Protocol, cast
from urllib import error, parse, request
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


class DocumentStorage(Protocol):
    provider: str

    def save(self, *, case_reference: str, name: str, content: bytes) -> str: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class MalwareScanner(Protocol):
    def scan(self, content: bytes) -> "ScanResult": ...


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    details: str


class DisabledScanner:
    """Explicit development-only scanner selected through configuration."""

    def scan(self, content: bytes) -> ScanResult:
        del content
        return ScanResult(clean=True, details="Analyse désactivée par configuration.")


class ClamAVScanner:
    """Small ClamAV INSTREAM client that fails closed."""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def scan(self, content: bytes) -> ScanResult:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            ) as connection:
                connection.sendall(b"zINSTREAM\0")
                for offset in range(0, len(content), 64 * 1024):
                    chunk = content[offset : offset + 64 * 1024]
                    connection.sendall(struct.pack("!I", len(chunk)))
                    connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                response = connection.recv(4096).decode("utf-8", errors="replace")
        except OSError as exc:
            raise ValidationError(
                "Le contrôle antivirus est indisponible. Réessayez plus tard."
            ) from exc
        if " FOUND" in response:
            return ScanResult(clean=False, details=response.strip("\0\r\n")[:240])
        if " OK" not in response:
            raise ValidationError("Le contrôle antivirus n'a pas pu conclure.")
        return ScanResult(clean=True, details=response.strip("\0\r\n")[:240])


class LocalPrivateStorage:
    provider = "local"

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, *, case_reference: str, name: str, content: bytes) -> str:
        suffix = Path(name).suffix.lower()
        key = f"{case_reference}/{uuid4().hex}{suffix}"
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return key

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in candidate.parents:
            raise ValidationError("Clé de document invalide.")
        return candidate

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class MicrosoftGraphStorage:
    """SharePoint drive adapter using app-only Microsoft Graph credentials."""

    provider = "sharepoint"

    def __init__(self) -> None:
        required = {
            "tenant": settings.MICROSOFT_GRAPH_TENANT_ID,
            "client": settings.MICROSOFT_GRAPH_CLIENT_ID,
            "secret": settings.MICROSOFT_GRAPH_CLIENT_SECRET,
            "site": settings.MICROSOFT_GRAPH_SITE_ID,
            "drive": settings.MICROSOFT_GRAPH_DRIVE_ID,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ImproperlyConfigured(
                "Configuration Microsoft Graph incomplète : " + ", ".join(missing)
            )
        self.tenant = required["tenant"]
        self.client = required["client"]
        self.secret = required["secret"]
        self.site = required["site"]
        self.drive = required["drive"]
        self.folder = str(settings.MICROSOFT_GRAPH_FOLDER).strip("/")

    def _token(self) -> str:
        body = parse.urlencode(
            {
                "client_id": self.client,
                "client_secret": self.secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            }
        ).encode()
        token_request = request.Request(
            f"https://login.microsoftonline.com/{parse.quote(self.tenant)}/oauth2/v2.0/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with request.urlopen(token_request, timeout=20) as response:
                payload = json.loads(response.read())
        except (OSError, error.HTTPError, json.JSONDecodeError) as exc:
            raise ValidationError("Microsoft Graph est indisponible.") from exc
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValidationError("Microsoft Graph n'a pas délivré de jeton.")
        return token

    def _call(self, method: str, url: str, content: bytes | None = None) -> bytes:
        graph_request = request.Request(
            url,
            data=content,
            method=method,
            headers={"Authorization": f"Bearer {self._token()}"},
        )
        try:
            with request.urlopen(graph_request, timeout=45) as response:
                return cast(bytes, response.read())
        except (OSError, error.HTTPError) as exc:
            raise ValidationError("Microsoft Graph est indisponible.") from exc

    def save(self, *, case_reference: str, name: str, content: bytes) -> str:
        suffix = Path(name).suffix.lower()
        key = f"{self.folder}/{case_reference}-{uuid4().hex}{suffix}"
        encoded = parse.quote(key, safe="/")
        url = (
            f"https://graph.microsoft.com/v1.0/sites/{parse.quote(self.site)}"
            f"/drives/{parse.quote(self.drive)}/root:/{encoded}:/content"
        )
        payload = json.loads(self._call("PUT", url, content))
        item_id = payload.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ValidationError("Microsoft Graph n'a pas confirmé le dépôt.")
        return item_id

    def read(self, key: str) -> bytes:
        url = (
            f"https://graph.microsoft.com/v1.0/sites/{parse.quote(self.site)}"
            f"/drives/{parse.quote(self.drive)}/items/{parse.quote(key)}/content"
        )
        return self._call("GET", url)

    def delete(self, key: str) -> None:
        url = (
            f"https://graph.microsoft.com/v1.0/sites/{parse.quote(self.site)}"
            f"/drives/{parse.quote(self.drive)}/items/{parse.quote(key)}"
        )
        self._call("DELETE", url)


def configured_storage() -> DocumentStorage:
    backend = str(settings.PROCESS_DOCUMENT_BACKEND).lower()
    if backend == "local":
        return LocalPrivateStorage(Path(settings.PROCESS_DOCUMENT_ROOT))
    if backend == "sharepoint":
        return MicrosoftGraphStorage()
    raise ImproperlyConfigured(f"Stockage de processus inconnu : {backend}")


def configured_scanner() -> MalwareScanner:
    if not settings.PROCESS_DOCUMENT_SCAN_REQUIRED:
        return DisabledScanner()
    return ClamAVScanner(
        str(settings.CLAMAV_HOST),
        int(settings.CLAMAV_PORT),
        float(settings.CLAMAV_TIMEOUT_SECONDS),
    )
