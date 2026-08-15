"""Pure rules used to initialize a user's agenda direction."""

from __future__ import annotations

from collections.abc import Mapping


PROGRAMS = "programs"
ADMINISTRATION = "administration"

PROGRAM_KINDS = frozenset({"programme", "laboratory", "station"})
ADMINISTRATION_KINDS = frozenset({"cell", "service"})


def classify_agenda_direction(
    *,
    unit_code: str,
    unit_kind: str,
    parent_by_code: Mapping[str, str | None],
) -> str:
    """Classify one unit while giving the DP and DAF branches priority."""
    code = unit_code.strip().upper()
    ancestors: set[str] = set()
    current: str | None = code
    while current is not None and current not in ancestors:
        ancestors.add(current)
        parent = parent_by_code.get(current)
        current = parent.strip().upper() if parent else None

    if "DP" in ancestors:
        return PROGRAMS
    if "DAF" in ancestors:
        return ADMINISTRATION

    kind = unit_kind.strip().lower()
    if kind in PROGRAM_KINDS:
        return PROGRAMS
    if kind in ADMINISTRATION_KINDS:
        return ADMINISTRATION
    return ""
