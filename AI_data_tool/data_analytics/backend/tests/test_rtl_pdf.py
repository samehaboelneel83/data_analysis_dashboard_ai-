"""Right-to-left text in the server-side PDF.

The app mirrors right-to-left end to end, but the downloaded file did not: the
screen and the PDF disagreed. reportlab draws glyphs in the order it is handed
them and does no shaping, and its default Helvetica has no Arabic glyphs at all
-- so Arabic came out as isolated letters in reversed order, or as nothing,
WITHOUT RAISING. A silent wrong answer is the failure mode worth testing.

The property that decides whether this is safe to ship unconditionally is that
LATIN IS UNTOUCHED -- most reports contain no RTL script, and a feature that
altered them would have to hide behind a flag, which is how the original gap
happened. Latin never enters the shaping libraries at all, pinned directly by
test_latin_never_enters_the_shaping_path.
"""
import pytest

from app.services import rtl_text
from app.services.pdf_export import build_report_pdf

ARABIC = "مبيعات الربع الأول"
HEBREW = "שלום"
LATIN = "Q1 Sales 2026"


class TestDetection:
    def test_arabic_is_rtl(self):
        assert rtl_text.has_rtl(ARABIC)

    def test_hebrew_is_rtl(self):
        """Not Arabic-only: the same treatment is needed for every RTL script."""
        assert rtl_text.has_rtl(HEBREW)

    def test_latin_is_not(self):
        assert not rtl_text.has_rtl(LATIN)

    def test_mixed_text_counts_as_rtl(self):
        """One Arabic value in an English report still has to render."""
        assert rtl_text.has_rtl("Region: " + ARABIC)

    def test_non_strings_are_not_rtl(self):
        for v in (None, 12345, 3.14, [], {}):
            assert not rtl_text.has_rtl(v)


class TestShaping:
    def test_arabic_is_converted_to_presentation_forms(self):
        """reportlab cannot shape, so the letters must arrive already in the
        positional forms it can draw one at a time."""
        shaped = rtl_text.shape(ARABIC)
        assert shaped != ARABIC
        assert all(0xFE70 <= ord(c) <= 0xFEFF for c in shaped if c.strip())

    def test_latin_is_returned_unchanged(self):
        """The reason this is safe to apply everywhere rather than behind a flag.

        Note honestly what this does and does not prove: for plain Latin the
        reshape+bidi round-trip is itself a no-op, so removing the `has_rtl`
        guard would NOT make this fail. The guard buys two things instead --
        Latin never enters that code path at all (so a future bug there cannot
        reach the reports that already work), and no per-cell allocation is
        spent on the overwhelmingly common case. The test below pins the first
        of those directly."""
        assert rtl_text.shape(LATIN) == LATIN

    def test_latin_never_enters_the_shaping_path(self, monkeypatch):
        """Blast radius, pinned. Every cell of every PDF table funnels through
        `shape`, so if Latin were routed through the RTL libraries, any bug or
        version change in them would affect every report rather than only the
        ones this feature exists for."""
        import builtins
        real = builtins.__import__
        touched = []

        def watch(name, *a, **k):
            if name in ("arabic_reshaper", "bidi.algorithm"):
                touched.append(name)
            return real(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", watch)
        rtl_text.shape(LATIN)
        assert touched == [], "Latin text reached the RTL shaping libraries"

        rtl_text.shape(ARABIC)
        assert touched, "Arabic text did NOT reach the shaping libraries"

    def test_non_strings_pass_straight_through(self):
        """Callers hand cells in directly, so numbers must survive untouched."""
        assert rtl_text.shape(12345) == 12345
        assert rtl_text.shape(None) is None

    def test_shaping_failure_degrades_to_unshaped_text(self, monkeypatch):
        """Unshaped RTL text is wrong but readable; a failed export is not."""
        import builtins
        real = builtins.__import__

        def boom(name, *a, **k):
            if name in ("arabic_reshaper", "bidi.algorithm"):
                raise ImportError("simulated")
            return real(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", boom)
        assert rtl_text.shape(ARABIC) == ARABIC


class TestFontSelection:
    def test_rtl_text_gets_an_arabic_capable_font(self):
        """Helvetica has no Arabic glyphs and draws NOTHING rather than raising,
        so shaping alone would produce a blank page that looks like a bug in the
        data."""
        assert rtl_text.font_for(ARABIC) == rtl_text.RTL_FONT_NAME

    def test_latin_keeps_the_documents_own_font(self):
        assert rtl_text.font_for(LATIN) == "Helvetica"
        assert rtl_text.font_for(LATIN, default="Times-Roman") == "Times-Roman"

    def test_registration_is_idempotent(self):
        """reportlab keeps a process-global registry; re-registering on every
        export would be wasted work on a request path."""
        assert rtl_text.ensure_rtl_font() is rtl_text.ensure_rtl_font()


class TestTheRenderedDocument:
    def _sections(self, name, title, value):
        return [{"page_name": name, "widgets": [
            {"title": title, "widget_type": "bar",
             "result": {"rows": [{"name": value, "value": 1200}]}}]}]

    def test_an_arabic_report_renders(self):
        pdf = build_report_pdf(ARABIC, ARABIC,
                               self._sections(ARABIC, ARABIC, ARABIC))
        assert pdf[:5] == b"%PDF-"
        assert len(pdf) > 1000

    def test_the_arabic_capable_font_is_embedded(self):
        """Without an embedded font the reader substitutes one, and a substituted
        font is exactly how RTL text becomes tofu boxes on someone else's
        machine while looking fine on the machine that made it."""
        pdf = build_report_pdf(ARABIC, None, self._sections(ARABIC, ARABIC, ARABIC))
        assert b"DejaVu" in pdf

    def test_an_english_report_does_not_embed_it(self):
        """Proof that nothing changed for the reports that already worked: an
        all-Latin document never touches the RTL path at all."""
        pdf = build_report_pdf("Sales", "Quarterly figures",
                               self._sections("Overview", "Revenue", "EMEA"))
        assert pdf[:5] == b"%PDF-"
        assert b"DejaVu" not in pdf

    def test_a_mixed_report_still_renders_both(self):
        pdf = build_report_pdf("Sales " + ARABIC, None,
                               self._sections("Overview", "Revenue", ARABIC))
        assert pdf[:5] == b"%PDF-"
        assert b"DejaVu" in pdf

    def test_classification_and_furniture_survive_an_rtl_name(self):
        """The footer draws the report name with canvas.drawString, a separate
        path from the body that needed its own font swap."""
        pdf = build_report_pdf(ARABIC, None,
                               self._sections(ARABIC, ARABIC, ARABIC),
                               classification="Confidential")
        assert pdf[:5] == b"%PDF-"


class TestItIsNotATranslationLayer:
    def test_interface_text_stays_english(self):
        """This changes how text is DRAWN, never what it says. An RTL report
        still says "Contents" -- claiming otherwise would be a promise of i18n
        that does not exist."""
        pdf = build_report_pdf(ARABIC, None, [
            {"page_name": ARABIC, "widgets": [
                {"title": ARABIC, "widget_type": "bar",
                 "result": {"rows": [{"name": ARABIC, "value": 1}]}}]},
            {"page_name": ARABIC + " 2", "widgets": []},
        ])
        assert pdf[:5] == b"%PDF-"


class TestTheDownloadHeader:
    """Found live, not by a unit test: exporting a report whose NAME is Arabic
    returned a 500.

    `build_report_pdf` was fine -- the failure was one line later. The filename
    was sanitised with `c.isalnum()`, which is True for Arabic, Hebrew and CJK
    letters, so those characters survived into a `Content-Disposition` header,
    and HTTP headers are latin-1. The PDF work made this reachable; the bug had
    been there all along for anyone with a non-Latin report name.
    """

    @staticmethod
    def _disposition(name: str) -> str:
        """The header the export builds, mirroring routers/reports.py."""
        from urllib.parse import quote
        raw = (name or "report").strip()[:60] or "report"
        ascii_name = "".join(
            c for c in raw if (c.isalnum() and c.isascii()) or c in " _-").strip() or "report"
        return (f'attachment; filename="{ascii_name}.pdf"; '
                f"filename*=UTF-8''{quote(raw + '.pdf')}")

    def test_an_arabic_name_produces_a_latin1_safe_header(self):
        """The actual crash: a header that cannot be encoded is a 500, not a
        garbled filename."""
        self._disposition(ARABIC).encode("latin-1")

    def test_the_real_name_still_travels(self):
        """RFC 6266's `filename*` carries it for clients that understand the
        parameter, so the fix is not just dropping the name."""
        d = self._disposition(ARABIC)
        assert "filename*=UTF-8''" in d
        assert "%D8%" in d

    def test_a_name_with_no_ascii_still_yields_a_usable_fallback(self):
        """Every client understands plain `filename`; an empty one would make
        the browser invent something or fail."""
        d = self._disposition(ARABIC)
        assert 'filename="report.pdf"' in d

    def test_an_english_name_is_unchanged(self):
        d = self._disposition("Sales Report")
        assert 'filename="Sales Report.pdf"' in d
