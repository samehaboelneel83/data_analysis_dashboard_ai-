"""A query that returns two columns with the same name must say so.

Found while building hospital dashboards. The query selected `l.unit` (a lab
result's unit of measure) and `COALESCE(d.unit, d.department) AS unit` (the
department's unit) — two different things that happen to share a word. SQL is
perfectly happy with that; pandas is not. `df["unit"]` stops being a Series and
becomes a DataFrame, and the first truth test on it raises:

    The truth value of a Series is ambiguous. Use a.empty, a.bool(), a.item(),
    a.any() or a.all()

which is what the import returned to the user, verbatim, as a 400.

That message is unusable. It names no column, no table and nothing the person
wrote, and it points at pandas internals for a mistake made in SQL. The mistake
is easy to make and trivial to describe — so describe it.
"""
import sqlite3

import pytest

from app.services.ingest import duplicate_columns


class TestDetection:
    def test_it_finds_a_repeated_name(self):
        assert duplicate_columns(["lab_id", "unit", "value", "unit"]) == ["unit"]

    def test_it_reports_every_repeated_name_once(self):
        assert duplicate_columns(["a", "b", "a", "c", "b", "a"]) == ["a", "b"]

    def test_a_clean_query_has_none(self):
        assert duplicate_columns(["lab_id", "unit", "value"]) == []

    def test_it_is_case_insensitive(self):
        """SQLite resolves `Unit` and `unit` to the same key, so a case-only
        difference is the same collision wearing a hat."""
        assert duplicate_columns(["Unit", "unit"]) == ["unit"]

    def test_it_preserves_the_order_they_appeared_in(self):
        """So the message reads in the order the person wrote their SELECT."""
        assert duplicate_columns(["z", "a", "z", "a"]) == ["z", "a"]


async def _source_with_labs(db_session, org_id, tmp_path):
    from app.models.models import DataSource
    path = tmp_path / "his.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE lab (lab_id INTEGER, unit TEXT, value REAL)")
    conn.execute("CREATE TABLE dept (dept_id INTEGER, unit TEXT)")
    conn.executemany("INSERT INTO lab VALUES (?,?,?)", [(1, "mg/dL", 5.2), (2, "g/L", 1.1)])
    conn.executemany("INSERT INTO dept VALUES (?,?)", [(1, "Haematology"), (2, "Chemistry")])
    conn.commit()
    conn.close()
    src = DataSource(name="HIS", type="sqlite", config={"filepath": str(path)},
                     org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    return src


async def test_the_import_names_the_duplicated_column(
        client, db_session, two_orgs, auth_headers, tmp_path):
    src = await _source_with_labs(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "Labs", "mode": "import",
              "query": "SELECT l.unit, d.unit, l.value FROM lab l JOIN dept d "
                       "ON d.dept_id = l.lab_id"},
        headers=auth_headers["a"])

    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "unit" in detail, detail
    assert "ambiguous" not in detail.lower(), (
        "the pandas message reached the user again: " + detail)


async def test_the_message_says_what_to_do_about_it(
        client, db_session, two_orgs, auth_headers, tmp_path):
    src = await _source_with_labs(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "Labs", "mode": "import",
              "query": "SELECT l.unit, d.unit FROM lab l JOIN dept d ON d.dept_id = l.lab_id"},
        headers=auth_headers["a"])
    assert "AS" in r.json()["detail"], "the fix is an alias; the message should say so"


async def test_a_query_without_duplicates_still_imports(
        client, db_session, two_orgs, auth_headers, tmp_path):
    src = await _source_with_labs(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "Labs", "mode": "import",
              "query": "SELECT l.unit AS lab_unit, d.unit AS dept_unit FROM lab l "
                       "JOIN dept d ON d.dept_id = l.lab_id"},
        headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] == 2
