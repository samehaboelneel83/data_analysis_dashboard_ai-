"""Integer columns holding Unix epoch timestamps are dates, not numbers.

Found while using the platform against a real Moodle LMS database, where every
date is stored as an integer of seconds since 1970 (`mdl_course.startdate =
1771106400`). Three separate parts of the platform got that wrong, and each
wrongness was silent:

  * `detect_types` called the column `numeric`, so it sits under Measures in the
    report builder and a "courses per month" chart plots raw integers.
  * `pii.detect_semantic_type` called it `national_id` — the rule is
    `^\\d{9,20}$` and an epoch second is exactly 10 digits — so every date in the
    database was masked before the model ever saw it.
  * the one repair the UI offers, prep step `retype -> datetime`, ran
    `pd.to_datetime(col)` with no unit, so pandas read the integer as
    nanoseconds and put every row on 1970-01-01.

A wrong date that looks like a date is worse than an error, so all three are
pinned here by value, not by shape.
"""
import pandas as pd
import pytest

from app.services.ingest import detect_types
from app.services import pii
from app.services.prep import apply_prep_steps


#: 2026-02-14 22:00:00 UTC — a real `mdl_course.startdate` from the Moodle file.
EPOCH_S = 1771106400
#: The same instant in milliseconds, which is what a JavaScript-origin export gives.
EPOCH_MS = 1771106400000

#: Six real course start dates from that database, two semesters a year.
COURSE_STARTS = [1694725200, 1707948000, 1726347600, 1739570400, 1757883600, 1771106400]


class TestTypeDetection:
    def test_epoch_seconds_column_is_detected_as_datetime(self):
        df = pd.DataFrame({"startdate": COURSE_STARTS})
        assert detect_types(df)["startdate"] == "datetime"

    def test_epoch_milliseconds_column_is_detected_as_datetime(self):
        df = pd.DataFrame({"created_at": [v * 1000 for v in COURSE_STARTS]})
        assert detect_types(df)["created_at"] == "datetime"

    def test_an_ordinary_measure_is_still_numeric(self):
        """The guard that keeps this from eating real numbers.

        Grades, counts, prices and ids must not become dates because they happen
        to be integers. Only a column whose NAME reads like a time and whose
        VALUES all land in a plausible epoch window qualifies.
        """
        df = pd.DataFrame({"finalgrade": [39.65, 88.0, 45.09, 100.0]})
        assert detect_types(df)["finalgrade"] == "numeric"

    def test_a_ten_digit_id_column_is_still_numeric(self):
        """`national_id` values are also 10 digits. The name is what separates them."""
        df = pd.DataFrame({"national_id": [2901234567, 2801234568, 2701234569]})
        assert detect_types(df)["national_id"] == "numeric"

    def test_a_time_named_column_of_implausible_values_is_still_numeric(self):
        """`timeout_ms = 30000` is a duration, not an instant. 1970-01-01 is not
        a plausible course start date, and the range check is what says so."""
        df = pd.DataFrame({"timeout": [30000, 60000, 15000]})
        assert detect_types(df)["timeout"] == "numeric"


class TestPiiClassification:
    def test_epoch_timestamps_are_not_personal_data(self):
        """The bug that poisoned the model's view of the whole database."""
        values = [str(v) for v in COURSE_STARTS]
        assert pii.detect_semantic_type(values) != "national_id"

    def test_a_real_national_id_is_still_detected(self):
        """The masking this replaces must not get weaker. Egyptian national IDs
        are 14 digits and nowhere near the epoch window."""
        values = ["29801011234567", "28502021234568", "27703031234569"]
        assert pii.detect_semantic_type(values) == "national_id"


class TestPrepRetype:
    def test_retype_to_datetime_reads_epoch_seconds_as_seconds(self):
        df = pd.DataFrame({"startdate": [EPOCH_S]})
        out = apply_prep_steps(df, [{"kind": "retype", "column": "startdate", "to": "datetime"}])
        assert out["startdate"].iloc[0] == pd.Timestamp("2026-02-14 22:00:00")

    def test_retype_to_datetime_reads_epoch_milliseconds_as_milliseconds(self):
        df = pd.DataFrame({"startdate": [EPOCH_MS]})
        out = apply_prep_steps(df, [{"kind": "retype", "column": "startdate", "to": "datetime"}])
        assert out["startdate"].iloc[0] == pd.Timestamp("2026-02-14 22:00:00")

    def test_retype_still_parses_ordinary_date_strings(self):
        """The existing behaviour, kept: a text date column must not regress."""
        df = pd.DataFrame({"signed": ["2024-03-01", "2024-03-02"]})
        out = apply_prep_steps(df, [{"kind": "retype", "column": "signed", "to": "datetime"}])
        assert out["signed"].iloc[0] == pd.Timestamp("2024-03-01")

    # A `year = 2024` column is covered by `test_epoch_unit_detects_the_right_unit`:
    # it is not an epoch, so retype leaves it on the existing pandas path. What
    # that path then does with a bare year is a separate question, not this one.


@pytest.mark.parametrize("value,expected", [
    (EPOCH_S, "s"),
    (EPOCH_MS, "ms"),
    (2024, None),          # a year
    (30000, None),         # a duration in ms, but 1970 — not plausible
    (2901234567, None),    # a national ID, outside the window
])
def test_epoch_unit_detects_the_right_unit(value, expected):
    """The one shared decision, so the three call sites cannot disagree."""
    from app.services.ingest import epoch_unit
    assert epoch_unit(pd.Series([value])) == expected


# ---------------------------------------------------------------------------
# The end-to-end rung. Getting the TYPE right is not the same as getting the
# STORED DATA right: the import writes its CSV and only then calls detect_types,
# so the conversion landed on a frame that had already been saved. The column
# was labelled `datetime` while every widget kept re-reading integers off disk.
# Asserting on executed rows rather than on the type is what catches that.
# ---------------------------------------------------------------------------
import sqlite3

from app.services.widget_data import clear_widget_data_cache


@pytest.fixture(autouse=True)
def _clear_widget_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


async def _moodle_like_source(db_session, org_id, tmp_path):
    """A miniature of the real thing: course rows whose start date is an epoch."""
    from app.models.models import DataSource
    db_path = tmp_path / "moodle_like.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE mdl_course (id INTEGER, fullname TEXT, startdate INTEGER)")
    conn.executemany(
        "INSERT INTO mdl_course (id, fullname, startdate) VALUES (?, ?, ?)",
        [(1, "Probability Theory", 1771106400),      # 2026-02-14
         (2, "Logic", 1707948000),                   # 2024-02-14
         (3, "Anatomy", 1771106400)],                # 2026-02-14
    )
    conn.commit()
    conn.close()
    src = DataSource(name="Moodle-like", type="sqlite",
                     config={"filepath": str(db_path)}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    return src


async def test_imported_epoch_column_charts_as_dates_not_integers(
        client, db_session, two_orgs, auth_headers, tmp_path):
    src = await _moodle_like_source(db_session, two_orgs["a"]["org"].id, tmp_path)

    imported = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "Courses", "table": "mdl_course", "mode": "import"},
        headers=auth_headers["a"])
    assert imported.status_code == 200
    dataset_id = imported.json()["id"]

    charted = await client.post(
        f"/api/v1/datasets/{dataset_id}/widget-data",
        json={"config": {"dimension": "startdate", "measure": "id",
                         "aggregation": "count", "limit": 10}},
        headers=auth_headers["a"])
    assert charted.status_code == 200
    labels = [str(row["name"]) for row in charted.json()["rows"]]

    # The whole point: an instructor building "courses per start date" must see
    # dates on the axis. Before the fix these came back as "1771106400".
    assert any("2026" in label for label in labels), labels
    assert not any(label.isdigit() for label in labels), labels


# ---------------------------------------------------------------------------
# The name hints were too greedy. Matching "end" as a substring made `sentiment`
# a time column, and matching "start" would do the same to `startup_costs`. The
# full suite caught it (three demo tests failed); no unit test here did, because
# every name I thought of was one I had already written the rule for.
#
# The glued Moodle names must keep working -- `startdate` and `timefinish` are
# still covered, by "date" and "time" rather than by "start" and "finish".
# ---------------------------------------------------------------------------
from app.services.ingest import looks_like_time_column


@pytest.mark.parametrize("name", [
    "startdate", "enddate", "timecreated", "timemodified", "duedate",
    "timestart", "timefinish", "timeopen", "timeclose", "lastaccess",
    "firstaccess", "lastlogin", "timeadded", "created_at", "updated_at",
    "order_date", "last_seen", "timestamp",
])
def test_a_real_time_column_is_still_recognised(name):
    assert looks_like_time_column(name), name


@pytest.mark.parametrize("name", [
    "sentiment",        # contains "end" -- the one that actually broke the suite
    "startup_costs",    # contains "start"
    "trend",            # contains "end"
    "attendance",       # contains "end"
    "revenue",          # nothing, but the obvious measure
    "amount_due",       # "due" is not enough on its own
    "finished_goods",   # "finish" is not enough on its own
])
def test_an_ordinary_column_is_not_mistaken_for_a_time_column(name):
    assert not looks_like_time_column(name), name
