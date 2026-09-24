"""Server-rendered report PDF.

A real, emailable artifact — not the browser's print-to-PDF: rendered
entirely server-side (matplotlib's headless Agg backend for chart images,
reportlab for document layout), so it can be downloaded on demand AND attached
to a scheduled delivery with no browser in the loop.

Structure mirrors SAS's report PDF: a cover (title, description, generated
timestamp), a table of contents, then one section per page with each data
widget drawn. Charts of the common families render as images; every other
widget type falls back to its shaped data as a table, so nothing is silently
dropped. Data is resolved through the ordinary widget-data pipeline, so
row-level security applies exactly as on screen (the caller's identity for a
download, the schedule's creator for a delivery).
"""
from __future__ import annotations

import io
import logging

import matplotlib
matplotlib.use("Agg")  # headless: no display server, safe in a container
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A3, A4, LETTER, landscape, portrait  # noqa: E402

_PAPERS = {"A4": A4, "A3": A3, "Letter": LETTER}
from reportlab.lib.enums import TA_RIGHT  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # noqa: E402

from . import rtl_text  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

log = logging.getLogger(__name__)

_PALETTE = ["#6c8fff", "#34d399", "#f472b6", "#fbbf24", "#a78bfa",
            "#22d3ee", "#fb7185", "#4ade80", "#c084fc", "#facc15"]
_SKIP_TYPES = {"button", "image", "shape", "slicer", "container"}


def _chart_image(widget_type: str, result: dict, title: str) -> bytes | None:
    """Render one widget's shaped result to a PNG, or None if it has no chart
    form (the caller then falls back to a data table)."""
    rows = result.get("rows") or []
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=110)
    try:
        if widget_type in ("bar", "donut", "pie", "funnel", "treemap", "word_cloud") and rows:
            names = [str(r.get("name")) for r in rows][:30]
            vals = [float(r.get("value") or 0) for r in rows][:30]
            if widget_type in ("pie", "donut"):
                ax.pie(vals, labels=names, autopct="%1.0f%%",
                       colors=_PALETTE * (len(vals) // len(_PALETTE) + 1),
                       wedgeprops={"width": 0.45} if widget_type == "donut" else None)
                ax.axis("equal")
            else:
                ax.bar(names, vals, color=_PALETTE[0])
                ax.tick_params(axis="x", rotation=45, labelsize=7)
                for lab in ax.get_xticklabels():
                    lab.set_ha("right")
        elif widget_type in ("line", "area", "step", "needle", "dot_plot") and rows:
            names = [str(r.get("name")) for r in rows]
            vals = [float(r.get("value") or 0) for r in rows]
            drawstyle = "steps-mid" if widget_type == "step" else "default"
            ax.plot(names, vals, color=_PALETTE[0], marker="o", markersize=3, drawstyle=drawstyle)
            if widget_type == "area":
                ax.fill_between(range(len(vals)), vals, color=_PALETTE[0], alpha=0.25)
            ax.tick_params(axis="x", rotation=45, labelsize=7)
            for lab in ax.get_xticklabels():
                lab.set_ha("right")
        elif widget_type == "scatter" and rows:
            xs = [float(r.get("name")) if _isnum(r.get("name")) else i for i, r in enumerate(rows)]
            ys = [float(r.get("value") or 0) for r in rows]
            ax.scatter(xs, ys, color=_PALETTE[0], alpha=0.6, s=18)
        else:
            plt.close(fig)
            return None
        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        return buf.read()
    except Exception as e:  # noqa: BLE001 -- one bad widget falls back to a table
        log.info("PDF chart render fell back to table for %s: %s", widget_type, e)
        return None
    finally:
        plt.close(fig)


def _isnum(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _kpi_flowable(result: dict, title: str, styles):
    val = result.get("value")
    if val is None and result.get("rows"):
        val = result["rows"][0].get("value")
    big = ParagraphStyle("kpi", parent=styles["Title"], fontSize=28, spaceAfter=2)
    return [Paragraph(str(_fmt(val)), big),
            _para(title, styles["Normal"])]


#: Rows one table may carry into the PDF.
#:
#: Was 40 -- a single screenful, which quietly turned every detail table into a
#: preview. A banded report whose table stops at 40 rows without saying so is
#: not a report, it is a screenshot: the reader has no way to know the other
#: 9,960 rows existed. reportlab already flows a Table across pages and
#: `repeatRows=1` carries the header, so the only thing that was missing is a
#: budget big enough to be useful and a note when it binds.
#:
#: 5,000 is roughly 120 pages of dense rows -- past any reasonable printed
#: report, and low enough that one runaway table cannot exhaust the renderer.
PDF_MAX_TABLE_ROWS = 5_000


def _table_flowable(result: dict, styles):
    """A widget's shaped data as a bordered table (the universal fallback).

    Flows across pages, repeating the header. When the row budget binds, the
    table is followed by a line saying how many rows were omitted -- a silently
    truncated table is a wrong answer that looks like a right one.
    """
    from .display_rules import result_frame
    frame = result_frame(result)
    if frame is None or frame.empty:
        return None
    total_rows = len(frame)
    truncated = total_rows > PDF_MAX_TABLE_ROWS
    frame = frame.head(PDF_MAX_TABLE_ROWS)
    header = [str(c) for c in frame.columns]
    data = [header] + [[_fmt(v) for v in row] for row in frame.itertuples(index=False)]
    tbl = Table(data, repeatRows=1, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f8")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d5e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f8fc")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    if truncated:
        return [tbl, Paragraph(
            f"Showing the first {PDF_MAX_TABLE_ROWS:,} of {total_rows:,} rows.",
            ParagraphStyle("trunc", parent=styles["Normal"], fontSize=7,
                           textColor=colors.HexColor("#888"), spaceBefore=3))]
    return tbl


def _rtl_style(text, style):
    """`style`, switched to an Arabic-capable font when the text needs one.

    A Paragraph draws with the font named in its style, so shaping alone is not
    enough: the default Helvetica has no Arabic glyphs and silently draws
    nothing rather than raising. Latin text keeps the document's own font, so
    existing reports are byte-identical to before.
    """
    if not rtl_text.has_rtl(text) or not rtl_text.ensure_rtl_font():
        return style
    return ParagraphStyle(f"{style.name}-rtl", parent=style,
                          fontName=rtl_text.RTL_FONT_NAME,
                          # Right-aligned because that is where a reader of an
                          # RTL script starts the line.
                          alignment=TA_RIGHT)


def _para(text, style):
    """A Paragraph that renders right-to-left text correctly."""
    return Paragraph(rtl_text.shape(str(text)), _rtl_style(text, style))


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".") if v % 1 else f"{int(v):,}"
    if isinstance(v, int):
        return f"{v:,}"
    # Shaped here because every cell in every table funnels through this
    # function. Latin text is returned unchanged, so nothing about an existing
    # report moves; only strings that actually contain RTL script are touched.
    return rtl_text.shape(str(v))


_CLASSIFICATION_COLORS = {
    "Public": "#2e7d32", "Internal": "#1565c0",
    "Confidential": "#e65100", "Restricted": "#c62828",
}


def build_report_pdf(report_name: str, description: str | None,
                     sections: list[dict], classification: str | None = None,
                     paper: str = "A4", orientation: str = "landscape", contents: bool = True) -> bytes:
    """Assemble the PDF from pre-resolved sections.

    Each section: {page_name, widgets: [{title, widget_type, result}]}. Data is
    resolved by the caller (async, security-applied) and handed in here, so this
    function is pure and synchronous — safe to run under asyncio.to_thread."""
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    # Page setup (MASTER_PLAN Phase 5 item 6): paper and orientation are the
    # reader's choice; unknown values fall back to the long-standing default.
    size = (portrait if orientation == "portrait" else landscape)(_PAPERS.get(paper, A4))
    doc = SimpleDocTemplate(buf, pagesize=size,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.2 * cm,
                            title=report_name)
    from datetime import datetime, timezone
    story: list = []

    def _page_furniture(canvas, doc_):
        """Page number and report name on every page but the cover.

        Without these a printed report cannot be cited, reassembled after being
        dropped, or checked for missing pages -- the three things page numbers
        exist for.
        """
        if doc_.page == 1:
            return
        canvas.saveState()
        # The report name is user-supplied and may be RTL, so the footer needs
        # the same font swap the body does -- Helvetica would draw it blank.
        canvas.setFont(rtl_text.font_for(report_name, "Helvetica"), 7)
        canvas.setFillColor(colors.HexColor("#888"))
        width, _h = size
        canvas.drawString(1.5 * cm, 0.8 * cm,
                          str(rtl_text.shape(report_name))[:80])
        canvas.drawRightString(width - 1.5 * cm, 0.8 * cm, f"Page {doc_.page}")
        if classification:
            # The label travels on every page, not just the cover: pages get
            # separated from the documents they came from.
            canvas.drawCentredString(width / 2, 0.8 * cm, classification.upper())
        canvas.restoreState()

    # Cover
    story.append(Spacer(1, 4 * cm))
    if classification:
        # A sensitivity banner on the cover: a PDF outlives the app's access controls,
        # so the label has to travel on the document itself.
        color = _CLASSIFICATION_COLORS.get(classification, "#555")
        story.append(Paragraph(
            classification.upper(),
            ParagraphStyle("classif", parent=styles["Normal"], fontSize=12,
                           textColor=colors.white, backColor=colors.HexColor(color),
                           alignment=1, spaceAfter=12, borderPadding=5)))
    story.append(_para(report_name, ParagraphStyle(
        "cover", parent=styles["Title"], fontSize=30, spaceAfter=14)))
    if description:
        story.append(_para(description, ParagraphStyle(
            "coversub", parent=styles["Normal"], fontSize=12, textColor=colors.HexColor("#555"))))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        ParagraphStyle("gen", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#888"))))

    # Table of contents (page names)
    if sections and contents:
        story.append(Spacer(1, 1.2 * cm))
        story.append(Paragraph("Contents", ParagraphStyle(
            "toch", parent=styles["Heading2"], fontSize=14)))
        for i, sec in enumerate(sections, 1):
            story.append(Paragraph(f"{i}. {sec['page_name']}  ·  {len(sec['widgets'])} visuals",
                                   ParagraphStyle("toc", parent=styles["Normal"], fontSize=10, leftIndent=10)))
    story.append(PageBreak())

    for sec in sections:
        story.append(_para(sec["page_name"], styles["Heading1"]))
        story.append(Spacer(1, 0.3 * cm))
        if not sec["widgets"]:
            story.append(Paragraph("No visuals with data on this page.", styles["Italic"]))
        for w in sec["widgets"]:
            title, wt, result = w["title"], w["widget_type"], w["result"]
            if wt in ("kpi", "card"):
                story.extend(_kpi_flowable(result, title, styles))
                story.append(Spacer(1, 0.4 * cm))
                continue
            png = _chart_image(wt, result, title)
            if png is not None:
                # Fit the page's usable width, whatever the paper.
                usable = size[0] - 3 * cm
                story.append(Image(io.BytesIO(png), width=min(usable, 24 * cm), height=min(usable, 24 * cm) / 2,
                                   kind="proportional"))
            else:
                story.append(_para(title, styles["Heading3"]))
                tbl = _table_flowable(result, styles)
                if tbl is None:
                    story.append(Paragraph("(no tabular data)", styles["Italic"]))
                elif isinstance(tbl, list):
                    story.extend(tbl)
                else:
                    story.append(tbl)
            story.append(Spacer(1, 0.5 * cm))
        story.append(PageBreak())

    doc.build(story, onFirstPage=_page_furniture, onLaterPages=_page_furniture)
    buf.seek(0)
    return buf.read()
