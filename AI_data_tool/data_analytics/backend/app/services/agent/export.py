"""Chat results as files: the stored snapshot serialized to Excel or PDF.

The rows already left the server as JSON on the answer (results.py), so these
functions change the FORMAT of that same egress, not what egresses — the
row-level security that shaped the SQL shaped the snapshot too.

Both builders are pure and synchronous: the router runs them under
`asyncio.to_thread`, the same discipline the widget export uses, because xlsx
and PDF serialization are CPU-bound and must not sit on the event loop.

PDF follows the conventions of services/pdf_export.py (reportlab platypus,
`rtl_text` shaping): Arabic cells are shaped AND drawn with the DejaVu font —
either alone produces blank or disjointed glyphs, see rtl_text's docstring.
"""
from __future__ import annotations

import io
import re
from xml.sax.saxutils import escape

import pandas as pd

from .. import rtl_text

#: Characters Excel forbids in a sheet name, plus the 31-char limit.
_SHEET_BAD = re.compile(r"[\[\]:*?/\\]")


def _sheet_name(step_id: str, index: int) -> str:
    name = _SHEET_BAD.sub("_", str(step_id) or f"step{index + 1}").strip() or f"step{index + 1}"
    return name[:31]


def trunc_note(shown: int, total: int) -> str:
    """The wording under a partial table. Its own function so the honesty
    rule -- a truncated table must say so -- is pinned as text, not fished
    out of a compressed PDF stream."""
    return f"Showing the first {shown:,} of {total:,} rows."


def build_result_xlsx(snapshots: list[tuple[str, dict]]) -> bytes:
    """One sheet per sink step. Cells arrive JSON-safe from the snapshot
    (results.coerce_scalar), so pandas writes them without surprises."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for i, (step_id, snap) in enumerate(snapshots):
            frame = pd.DataFrame(snap.get("rows") or [],
                                 columns=snap.get("columns") or [])
            frame.to_excel(writer, index=False, sheet_name=_sheet_name(step_id, i))
    return buf.getvalue()


def build_result_pdf(question: str, answer: str | None, sqls: list[str],
                     snapshots: list[tuple[str, dict]]) -> bytes:
    """Question, answer, the result table(s), and the SQL that produced them.

    Portrait A4 -- a chat result is a handful of columns, not a report page --
    with the table flowing across pages and the header repeated. When the
    snapshot is only the head of a larger result, a note (`trunc_note`) says
    exactly how much is missing: a silently truncated table is a wrong answer
    that looks like a right one (the same rule pdf_export's tables follow).
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    styles = getSampleStyleSheet()

    def para(text: str, style) -> Paragraph:
        # Shaped for RTL, escaped for Paragraph's XML-ish parser (an
        # unescaped "<>" in SQL would raise deep inside reportlab), and
        # switched to an Arabic-capable font when the text needs one.
        shaped = str(rtl_text.shape(str(text)))
        if rtl_text.has_rtl(text) and rtl_text.ensure_rtl_font():
            style = ParagraphStyle(f"{style.name}-rtl", parent=style,
                                   fontName=rtl_text.RTL_FONT_NAME,
                                   alignment=TA_RIGHT)
        return Paragraph(escape(shaped), style)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.2 * cm,
                            title="Ask AI result")

    small_grey = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8,
                                textColor=colors.HexColor("#666"))
    story: list = [para(question, styles["Title"]), Spacer(1, 0.2 * cm)]
    if answer:
        story += [para(answer, styles["Normal"]), Spacer(1, 0.4 * cm)]

    for i, (step_id, snap) in enumerate(snapshots):
        columns = [str(c) for c in (snap.get("columns") or [])]
        rows = snap.get("rows") or []
        if len(snapshots) > 1:
            story.append(para(f"Step {step_id}", styles["Heading3"]))
        if not columns:
            story.append(para("No rows.", small_grey))
            continue
        cells = [[rtl_text.shape("" if v is None else str(v)) for v in row]
                 for row in rows]
        # One font decision per table: any RTL cell switches the whole table
        # to DejaVu (it covers Latin too), because reportlab has no per-cell
        # fallback and Helvetica draws Arabic as nothing at all.
        all_text = "".join(columns) + "".join(str(v) for r in rows for v in r if v is not None)
        font = rtl_text.font_for(all_text, "Helvetica")
        tbl = Table([columns] + cells, repeatRows=1, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f8")),
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d5e0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f7f8fc")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(tbl)
        total = snap.get("total", len(rows))
        if snap.get("truncated") or total > len(rows):
            story.append(para(trunc_note(len(rows), total), small_grey))
        story.append(Spacer(1, 0.3 * cm))

    if sqls:
        mono = ParagraphStyle("sql", parent=styles["Normal"], fontName="Courier",
                              fontSize=7, leading=9,
                              textColor=colors.HexColor("#444"))
        story.append(Spacer(1, 0.2 * cm))
        story.append(para("SQL", styles["Heading4"]))
        for sql in sqls:
            story.append(Paragraph(escape(sql), mono))

    doc.build(story)
    return buf.getvalue()
