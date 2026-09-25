"""Right-to-left text for server-side PDF export.

The screen and the downloaded file disagreed. The app mirrors right-to-left
end to end, but `pdf_export` handed strings to reportlab, which draws glyphs in
exactly the order it is given and performs no shaping at all. Arabic came out as
isolated letter forms in reversed order -- and the default Helvetica has no
Arabic glyphs whatsoever, so it silently drew nothing rather than raising.

Three separate problems, and all three must be solved or the output is wrong:

  1. SHAPING. Arabic letters change form by position (initial, medial, final,
     isolated). `arabic_reshaper` maps the source codepoints to the presentation
     forms a non-shaping renderer can draw one at a time.
  2. ORDERING. The Unicode bidirectional algorithm decides visual order for
     mixed text. `python-bidi` applies it, so "مبيعات 2026" puts the number
     where a reader expects rather than where the byte order happens to put it.
  3. GLYPH COVERAGE. Helvetica is Latin-only. DejaVu Sans covers Arabic and is
     ALREADY IN THE IMAGE via matplotlib, so nothing is downloaded and the
     air-gapped guarantee is untouched.

DELIBERATELY NOT A TRANSLATION LAYER. This changes how text is drawn, never what
it says. Interface strings stay English; only user data and titles that already
contain RTL script are affected.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Registered under this name once, at first use.
RTL_FONT_NAME = "DejaVuSans"
RTL_FONT_BOLD = "DejaVuSans-Bold"

# Shipped inside matplotlib rather than added as an asset: it is already present
# in every build of this image, so using it costs nothing and downloads nothing.
_MPL_FONTS = "matplotlib/mpl-data/fonts/ttf"

# The Unicode blocks whose presence means a string needs the RTL treatment.
# Checked as ranges rather than by locale or a user setting, because a single
# Arabic dataset value inside an otherwise-English report still has to render
# correctly, and nobody would think to flip a switch for it.
_RTL_RANGES = (
    (0x0590, 0x05FF),   # Hebrew
    (0x0600, 0x06FF),   # Arabic
    (0x0700, 0x074F),   # Syriac
    (0x0750, 0x077F),   # Arabic Supplement
    (0x08A0, 0x08FF),   # Arabic Extended-A
    (0xFB1D, 0xFDFF),   # Hebrew/Arabic presentation forms
    (0xFE70, 0xFEFF),   # Arabic presentation forms-B
)


def has_rtl(text: object) -> bool:
    """True when the string contains any right-to-left script.

    Cheap enough to call on every cell: it stops at the first RTL codepoint, and
    a pure-Latin string costs one pass with no allocation.
    """
    if not isinstance(text, str) or not text:
        return False
    for ch in text:
        cp = ord(ch)
        for lo, hi in _RTL_RANGES:
            if lo <= cp <= hi:
                return True
    return False


def _font_path(filename: str) -> str | None:
    """Locate a matplotlib-bundled TTF without importing matplotlib.

    Importing matplotlib here would pull in pyplot and a rendering backend for
    the sake of a file path -- expensive, and this module is imported on a
    request path.
    """
    try:
        import matplotlib
        base = os.path.dirname(matplotlib.__file__)
    except Exception:  # noqa: BLE001 -- absence is handled by the caller
        return None
    path = os.path.join(base, "mpl-data", "fonts", "ttf", filename)
    return path if os.path.exists(path) else None


_registered: bool | None = None


def ensure_rtl_font() -> bool:
    """Register DejaVu Sans with reportlab. True when RTL text is drawable.

    Idempotent and memoised: reportlab keeps a process-global font registry, so
    re-registering on every export would be wasted work. A failure is recorded
    as False so the caller falls back to the default font rather than retrying
    a lookup that will not start working.
    """
    global _registered
    if _registered is not None:
        return _registered
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        regular = _font_path("DejaVuSans.ttf")
        bold = _font_path("DejaVuSans-Bold.ttf")
        if not regular:
            logger.warning("No Arabic-capable font found; PDF RTL text will not render")
            _registered = False
            return False
        pdfmetrics.registerFont(TTFont(RTL_FONT_NAME, regular))
        if bold:
            pdfmetrics.registerFont(TTFont(RTL_FONT_BOLD, bold))
            from reportlab.lib.fonts import addMapping
            # Bold <b> inside a Paragraph resolves through this mapping; without
            # it reportlab silently falls back to a Latin-only face and the bold
            # run renders as nothing.
            addMapping(RTL_FONT_NAME, 0, 0, RTL_FONT_NAME)
            addMapping(RTL_FONT_NAME, 1, 0, RTL_FONT_BOLD)
        _registered = True
    except Exception as e:  # noqa: BLE001 -- never break an export over a font
        logger.warning("Could not register an RTL font: %s", e)
        _registered = False
    return _registered


def shape(text: object) -> object:
    """Reshape and bidi-order a string for a non-shaping renderer.

    NON-RTL INPUT IS RETURNED UNCHANGED, by identity. Most reports contain no
    RTL script at all, and running Latin text through the bidi algorithm would
    spend time to produce the same string -- worse, any bug in that path would
    then affect every report rather than only the ones this exists for.

    Non-strings pass through untouched so callers can hand cells straight in.
    """
    if not has_rtl(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception as e:  # noqa: BLE001
        # Unshaped RTL text is wrong but readable; a failed export is not.
        logger.warning("RTL shaping failed, drawing text unshaped: %s", e)
        return text


def font_for(text: object, default: str = "Helvetica") -> str:
    """The font to draw this string with.

    Only RTL strings are switched to DejaVu. Latin text keeps the document's own
    font, so enabling this changes nothing about how existing reports look --
    which is what makes it safe to apply everywhere rather than behind a flag.
    """
    if has_rtl(text) and ensure_rtl_font():
        return RTL_FONT_NAME
    return default
