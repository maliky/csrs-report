"""Read the canonical Org organizational tree used by demo data and tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


HEADING_RE = re.compile(r"^(?P<stars>\*+)\s+(?P<title>.+?)\s*$")
PROPERTY_RE = re.compile(r"^:(?P<key>[A-Z_]+):\s*(?P<value>.*?)\s*$")


@dataclass(frozen=True)
class OrgUnitSpec:
    """One validated organizational unit recovered from the canonical Org file."""

    code: str
    long_name: str
    short_name: str
    kind: str
    parent_code: str | None
    display_order: int
    demo_alias: str | None = None
    demo_position: str | None = None


def canonical_organogram_path() -> Path:
    return Path(settings.BASE_DIR) / "docs" / "organogram.org"


def load_organogram(  # noqa: C901 - validation mirrors the compact Org grammar
    path: Path | None = None,
) -> tuple[OrgUnitSpec, ...]:
    """Parse unit headings and property drawers while preserving document order."""
    source = path or canonical_organogram_path()
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ImproperlyConfigured(
            f"Organigramme canonique indisponible : {source}"
        ) from exc

    raw_units: list[tuple[int, str, dict[str, str]]] = []
    index = 0
    while index < len(lines):
        heading = HEADING_RE.match(lines[index])
        if heading is None:
            index += 1
            continue
        level = len(heading.group("stars"))
        title = heading.group("title")
        properties: dict[str, str] = {}
        cursor = index + 1
        if cursor < len(lines) and lines[cursor].strip() == ":PROPERTIES:":
            cursor += 1
            while cursor < len(lines) and lines[cursor].strip() != ":END:":
                match = PROPERTY_RE.match(lines[cursor].strip())
                if match is not None:
                    properties[match.group("key")] = match.group("value")
                cursor += 1
            if cursor >= len(lines):
                raise ImproperlyConfigured(
                    f"Tiroir de propriétés non fermé pour « {title} »."
                )
        if "UNIT_CODE" in properties:
            raw_units.append((level, title, properties))
        index = max(index + 1, cursor + 1)

    if not raw_units:
        raise ImproperlyConfigured("L’organigramme canonique ne contient aucune unité.")

    stack: list[tuple[int, str]] = []
    specs: list[OrgUnitSpec] = []
    seen_codes: set[str] = set()
    seen_aliases: set[str] = set()
    for order, (level, title, properties) in enumerate(raw_units):
        code = properties["UNIT_CODE"].strip().upper()
        short_name = properties.get("SHORT_NAME", "").strip()
        kind = properties.get("UNIT_KIND", "").strip()
        alias = properties.get("DEMO_ALIAS", "").strip() or None
        position = properties.get("DEMO_POSITION", "").strip() or None
        if not code or not short_name or not kind:
            raise ImproperlyConfigured(
                f"L’unité « {title} » doit définir UNIT_CODE, SHORT_NAME et UNIT_KIND."
            )
        if code in seen_codes:
            raise ImproperlyConfigured(f"Code d’unité dupliqué : {code}.")
        if alias and alias in seen_aliases:
            raise ImproperlyConfigured(f"Alias de démonstration dupliqué : {alias}.")
        if bool(alias) != bool(position):
            raise ImproperlyConfigured(
                f"L’unité {code} doit définir DEMO_ALIAS et DEMO_POSITION ensemble."
            )

        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_code = stack[-1][1] if stack else None
        if specs and parent_code is None:
            raise ImproperlyConfigured(
                "L’organigramme doit avoir une seule racine organisationnelle."
            )
        if stack and level != stack[-1][0] + 1:
            raise ImproperlyConfigured(
                f"Niveau hiérarchique invalide pour l’unité {code}."
            )
        spec = OrgUnitSpec(
            code=code,
            long_name=title,
            short_name=short_name,
            kind=kind,
            parent_code=parent_code,
            display_order=order,
            demo_alias=alias,
            demo_position=position,
        )
        specs.append(spec)
        seen_codes.add(code)
        if alias:
            seen_aliases.add(alias)
        stack.append((level, code))

    return tuple(specs)
