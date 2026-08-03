"""Portable audit export for a closed process case."""

from __future__ import annotations

from io import BytesIO
import json
import textwrap
from zipfile import ZIP_DEFLATED, ZipFile

from processes.models import ProcessCase
from processes.services import document_bytes


def _pdf_escape(value: str) -> bytes:
    normalized = value.encode("latin-1", errors="replace").decode("latin-1")
    return (
        normalized.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .encode("latin-1")
    )


def simple_audit_pdf(lines: list[str]) -> bytes:
    """Produce a small valid PDF without adding a host-specific renderer."""
    wrapped = [part for line in lines for part in (textwrap.wrap(line, 92) or [""])]
    commands = [b"BT", b"/F1 10 Tf", b"48 800 Td", b"13 TL"]
    for index, line in enumerate(wrapped[:56]):
        if index:
            commands.append(b"T*")
        commands.append(b"(" + _pdf_escape(line) + b") Tj")
    commands.append(b"ET")
    stream = b"\n".join(commands)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, item in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode())
        output.write(item)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return output.getvalue()


def export_case_zip(case: ProcessCase) -> bytes:
    mission = case.mission_order
    signature = getattr(case, "signature", None)
    documents = list(case.documents.filter(replaced_by__isnull=True).order_by("pk"))
    events = list(case.events.select_related("actor").order_by("occurred_at", "pk"))
    manifest = {
        "export_type": "Dossier d'audit CSRS Report",
        "official_document": False,
        "reference": case.reference,
        "status": case.status,
        "revision": case.revision,
        "documents": [
            {
                "id": document.pk,
                "name": document.original_name,
                "kind": document.kind,
                "size": document.size,
                "sha256": document.sha256,
                "scan_status": document.scan_status,
            }
            for document in documents
        ],
        "signature": (
            {
                "signer_id": signature.signer_id,
                "signed_at": signature.signed_at.isoformat(),
                "confirmation": signature.confirmation,
                "snapshot_sha256": signature.snapshot_sha256,
                "document_manifest": signature.document_manifest,
            }
            if signature is not None
            else None
        ),
    }
    lines = [
        "Dossier d'audit CSRS Report — ce document n'est pas un ordre de mission officiel",
        f"Référence : {case.reference}",
        f"État : {case.get_status_display()}",
        f"Demandeur : {case.initiator}",
        f"Service : {case.origin_unit_name}",
        f"Mission : {mission.get_mission_type_display()} — {mission.destination}",
        f"Période : {mission.departure_date:%d/%m/%Y} au {mission.return_date:%d/%m/%Y}",
        f"Motif : {mission.purpose}",
        "Historique :",
    ]
    lines.extend(
        f"{event.occurred_at:%d/%m/%Y %H:%M} — {event.actor} — {event.kind} — {event.message}"
        for event in events
    )
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("audit.pdf", simple_audit_pdf(lines))
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        )
        for document in documents:
            safe_name = document.original_name.replace("/", "_").replace("\\", "_")
            archive.writestr(
                f"pieces/{document.pk:04d}-{safe_name}", document_bytes(document)
            )
    return target.getvalue()
