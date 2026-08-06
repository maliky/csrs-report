"""Printable A4 rendering for immutable weekly agenda snapshots."""

from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


GREEN = colors.HexColor("#176B45")
PALE_GREEN = colors.HexColor("#EAF4EE")
MUTED = colors.HexColor("#52615A")
LIGHT_BORDER = colors.HexColor("#BCD1C4")


def _register_fonts() -> tuple[str, str]:
    regular = Path(str(settings.AGENDA_PDF_FONT_PATH))
    bold = Path(str(settings.AGENDA_PDF_FONT_BOLD_PATH))
    if regular.is_file() and bold.is_file():
        if "CSRSDejaVu" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("CSRSDejaVu", regular))
            pdfmetrics.registerFont(TTFont("CSRSDejaVu-Bold", bold))
        return "CSRSDejaVu", "CSRSDejaVu-Bold"
    return "Helvetica", "Helvetica-Bold"


def _text(value: object) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def _visitor_summary(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "RAS"
    total = sum(cast(int, row["party_size"]) for row in rows)
    names = [
        str(name)
        for row in rows
        for name in cast(list[object], row.get("visitor_names", []))
    ]
    suffix = f"<br/><font size='7'>{_text(', '.join(names))}</font>" if names else ""
    label = "visiteur" if total == 1 else "visiteurs"
    return f"<b>{total} {label}</b>{suffix}"


def _availability_summary(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "RAS"
    lines = []
    for row in rows:
        employee = cast(dict[str, object], row["employee"])
        dates = (
            str(row["start_date"])
            if row["start_date"] == row["end_date"]
            else f"{row['start_date']} au {row['end_date']}"
        )
        note = f" — {_text(row['note'])}" if row.get("note") else ""
        lines.append(
            f"<b>{_text(row['kind_label'])}</b> : {_text(employee['name'])} "
            f"({_text(dates)}){note}"
        )
    return "<br/>".join(lines)


def render_weekly_agenda_pdf(
    snapshot: dict[str, object], *, generated_at: datetime, version: int
) -> bytes:
    """Render the same frozen snapshot used by the preview API."""
    regular, bold = _register_fonts()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "AgendaTitle",
        parent=styles["Title"],
        fontName=bold,
        fontSize=19,
        leading=23,
        textColor=GREEN,
        alignment=TA_CENTER,
        spaceAfter=2 * mm,
    )
    subtitle = ParagraphStyle(
        "AgendaSubtitle",
        parent=styles["Normal"],
        fontName=regular,
        fontSize=9,
        leading=12,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=5 * mm,
    )
    box_title = ParagraphStyle(
        "AgendaBoxTitle",
        parent=styles["Normal"],
        fontName=bold,
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    box_body = ParagraphStyle(
        "AgendaBoxBody",
        parent=styles["Normal"],
        fontName=regular,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#20352A"),
        alignment=TA_CENTER,
    )
    unit_title = ParagraphStyle(
        "AgendaUnitTitle",
        parent=styles["Heading3"],
        fontName=bold,
        fontSize=9,
        leading=11,
        textColor=colors.white,
        alignment=TA_LEFT,
    )
    unit_body = ParagraphStyle(
        "AgendaUnitBody",
        parent=styles["BodyText"],
        fontName=regular,
        fontSize=7.4,
        leading=9.8,
        textColor=colors.HexColor("#24372D"),
        alignment=TA_LEFT,
    )

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=13 * mm,
        bottomMargin=15 * mm,
        title="Agenda de la semaine",
        author="CSRS Report",
    )
    story: list[object] = [
        Paragraph("AGENDA DE LA SEMAINE", title),
        Paragraph(
            f"Semaine du {_text(snapshot['week_start'])} au {_text(snapshot['week_end'])}",
            subtitle,
        ),
    ]

    summaries = (
        ("ÉVÉNEMENTS MAJEURS", _text(snapshot.get("major_events") or "RAS")),
        (
            "ARRIVÉES DE VISITEURS",
            _visitor_summary(cast(list[dict[str, object]], snapshot["arrivals"])),
        ),
        (
            "DÉPARTS DE VISITEURS",
            _visitor_summary(cast(list[dict[str, object]], snapshot["departures"])),
        ),
        (
            "CONGÉS, ABSENCES ET MISSIONS",
            _availability_summary(
                cast(list[dict[str, object]], snapshot["availability"])
            ),
        ),
    )
    boxes: list[list[object]] = []
    for label, body in summaries:
        boxes.append(
            [
                Table(
                    [
                        [Paragraph(label, box_title)],
                        [Paragraph(body, box_body)],
                    ],
                    colWidths=[88 * mm],
                    rowHeights=[9 * mm, None],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                            ("BACKGROUND", (0, 1), (-1, -1), PALE_GREEN),
                            ("BOX", (0, 0), (-1, -1), 0.6, LIGHT_BORDER),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                            ("TOPPADDING", (0, 1), (-1, -1), 3 * mm),
                            ("BOTTOMPADDING", (0, 1), (-1, -1), 3 * mm),
                        ]
                    ),
                )
            ]
        )
    story.append(
        Table(
            [[boxes[0][0], boxes[1][0]], [boxes[2][0], boxes[3][0]]],
            colWidths=[90 * mm, 90 * mm],
            hAlign="CENTER",
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 1 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 1 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm),
                ]
            ),
        )
    )
    story.append(Spacer(1, 5 * mm))

    unit_cards: list[Table] = []
    for unit in cast(list[dict[str, object]], snapshot["units"]):
        lines: list[str] = []
        for employee in cast(list[dict[str, object]], unit["employees"]):
            person = cast(dict[str, object], employee["person"])
            lines.append(
                f"<b>{_text(person['name'])}</b> — taux moyen : "
                f"<b>{cast(int, employee['completion_rate'])}%</b>"
            )
            for task in cast(list[dict[str, object]], employee["tasks"]):
                delta = cast(int, task["progress_delta"])
                delta_text = f"+{delta}" if delta >= 0 else str(delta)
                observation = (
                    f" — {_text(task['observation'])}" if task.get("observation") else ""
                )
                lines.append(
                    f"• {_text(task['title'])} — <b>{cast(int, task['percentage'])}%</b> "
                    f"({delta_text} pt) — {_text(task['status_label'])}{observation}"
                )
        card = Table(
            [
                [Paragraph(_text(unit["name"]), unit_title)],
                [Paragraph("<br/>".join(lines) or "RAS", unit_body)],
            ],
            colWidths=[88 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.6, LIGHT_BORDER),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            ),
        )
        unit_cards.append(card)

    if not unit_cards:
        story.append(
            Paragraph("Aucune activité enregistrée pour cette semaine.", unit_body)
        )
    else:
        for index in range(0, len(unit_cards), 2):
            pair: list[object] = [unit_cards[index]]
            pair.append(unit_cards[index + 1] if index + 1 < len(unit_cards) else "")
            story.append(
                KeepTogether(
                    Table(
                        [pair],
                        colWidths=[90 * mm, 90 * mm],
                        style=TableStyle(
                            [
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 1 * mm),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm),
                                ("TOPPADDING", (0, 0), (-1, -1), 1 * mm),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm),
                            ]
                        ),
                    )
                )
            )

    local_generated = timezone.localtime(generated_at)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(GREEN)
        canvas.setFont(bold, 8)
        canvas.drawString(12 * mm, A4[1] - 9 * mm, "CSRS REPORT")
        canvas.setFillColor(MUTED)
        canvas.setFont(regular, 7)
        canvas.drawString(
            12 * mm,
            8 * mm,
            f"Version {version} — générée le {local_generated:%d/%m/%Y à %H:%M}",
        )
        canvas.drawRightString(A4[0] - 12 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
