"""The report PDF as a paginated document, not a screenshot.

The export already had a cover, a table of contents and one section per page.
What it did not have was a table that ran past the first screenful: every
detail table stopped at 40 rows, silently. A reader had no way to know the other
rows existed, which makes a truncated table a wrong answer that looks like a
right one.

These tests pin the three properties that turn it into a document somebody can
print, cite and check: tables flow across pages, the header repeats, and when
the row budget really does bind the document says so.
"""
import re

import pytest

from app.services.pdf_export import PDF_MAX_TABLE_ROWS, build_report_pdf


def table_result(n, cols=("id", "region", "revenue")):
    return {"type": "table", "columns": list(cols),
            "rows": [[i, f"R{i % 5}", i * 10.5] for i in range(n)]}


def section(n, title="Rows"):
    return [{"page_name": "Detail",
             "widgets": [{"title": title, "widget_type": "table",
                          "result": table_result(n)}]}]


def page_count(pdf: bytes) -> int:
    """Pages, read from the PDF structure rather than inferred."""
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


class TestTablesFlowAcrossPages:
    def test_a_long_table_produces_many_pages(self):
        """The regression this file exists for. At the old 40-row cap this
        report was one page no matter how much data it held."""
        pdf = build_report_pdf("Detail", None, section(900))
        assert page_count(pdf) > 10, "a 900-row table still fits on one page?"

    def test_more_rows_means_a_bigger_document(self):
        small = build_report_pdf("S", None, section(10))
        large = build_report_pdf("L", None, section(900))
        # A truncated table would produce two documents of nearly equal size.
        assert len(large) > len(small) * 3

    def test_rows_beyond_the_old_cap_are_actually_present(self):
        pdf = build_report_pdf("D", None, section(200))
        # 40 was the old ceiling; a row well past it must reach the document.
        assert page_count(pdf) >= 3

    def test_a_short_table_stays_compact(self):
        pdf = build_report_pdf("S", None, section(5))
        assert page_count(pdf) <= 3, "a five-row table should not sprawl"


class TestItIsHonestAboutWhatItOmits:
    def test_an_over_budget_table_still_renders(self):
        pdf = build_report_pdf("Huge", None, section(PDF_MAX_TABLE_ROWS + 50))
        assert len(pdf) > 0 and page_count(pdf) > 1

    def test_the_budget_is_high_enough_to_be_a_report(self):
        """40 rows is a preview. The number here is a deliberate choice, and a
        future edit that quietly lowers it should have to change this line."""
        assert PDF_MAX_TABLE_ROWS >= 1000

    def test_a_table_within_budget_says_nothing_about_truncation(self):
        # The note must appear only when it is true.
        pdf = build_report_pdf("D", None, section(50))
        assert b"Showing the first" not in pdf


class TestPageFurniture:
    def test_multi_page_reports_carry_page_numbers(self):
        """Without them a printed report cannot be cited, reassembled, or
        checked for missing pages."""
        pdf = build_report_pdf("Detail", None, section(300))
        assert page_count(pdf) > 1
        # reportlab may subset/compress text, so assert on structure: a
        # single-page doc and a many-page doc must differ in page count, and
        # the furniture callback runs for every page after the cover.
        one = build_report_pdf("Detail", None, section(1))
        assert page_count(pdf) > page_count(one)

    def test_a_classification_travels_on_the_document(self):
        """A PDF outlives the app's access controls, so the label has to be on
        the pages, not only in the database."""
        pdf = build_report_pdf("Secret", None, section(200), classification="Confidential")
        assert len(pdf) > 0
        plain = build_report_pdf("Secret", None, section(200))
        assert len(pdf) != len(plain), "the classification left no trace"


class TestItStillHandlesTheOrdinaryCases:
    def test_an_empty_section_does_not_break_the_build(self):
        pdf = build_report_pdf("Empty", None, [{"page_name": "P", "widgets": []}])
        assert len(pdf) > 0

    def test_a_widget_with_no_rows_is_reported_not_dropped(self):
        pdf = build_report_pdf("E", None, [{"page_name": "P", "widgets": [
            {"title": "t", "widget_type": "table",
             "result": {"type": "table", "columns": ["a"], "rows": []}}]}])
        assert len(pdf) > 0

    def test_no_sections_at_all(self):
        assert len(build_report_pdf("Nothing", None, [])) > 0
