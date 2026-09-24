"""`week` is an offered granularity that produced an empty chart.

Found while building an instructor dashboard: "how many of my students showed up
each week" is the most natural question a teacher asks, and setting the
dimension granularity to `week` returned zero rows — no error, no warning, an
empty chart. `month` and `quarter` worked.

The cause is a disagreement inside one module. The forecast path already treats
week as real:

    season = {"month": 12, "quarter": 4, "week": 52, "day": 7}
    freq   = {"month": "MS", "quarter": "QS", "week": "W", ...}

but `_dimension_granularity_label` only knew year/quarter/month/day and raised
`ValueError` for anything else, which the widget path swallowed into an empty
result. So the feature was half-present: advertised by one function, missing in
the one that draws the axis.
"""
import pandas as pd
import pytest

from app.services.widget_data import _dimension_granularity_label

#: A Monday, the Wednesday after it, and the following Monday. The first two
#: belong to one week and the third does not — which is the whole assertion.
_MON = pd.Timestamp("2026-02-09 08:00")
_WED = pd.Timestamp("2026-02-11 23:30")
_NEXT_MON = pd.Timestamp("2026-02-16 00:15")


def test_week_labels_group_days_of_the_same_week_together():
    labels = _dimension_granularity_label(pd.Series([_MON, _WED]), "week")
    assert labels.iloc[0] == labels.iloc[1]


def test_week_labels_separate_consecutive_weeks():
    labels = _dimension_granularity_label(pd.Series([_WED, _NEXT_MON]), "week")
    assert labels.iloc[0] != labels.iloc[1]


def test_week_labels_sort_chronologically_as_text():
    """Chart axes sort these as strings, so the label must be sortable as one.
    An ISO year-week ("2026-W07") is; "week 7 of 2026" is not."""
    labels = _dimension_granularity_label(pd.Series([_NEXT_MON, _MON]), "week")
    assert sorted(labels.tolist()) == [labels.iloc[1], labels.iloc[0]]


def test_week_label_carries_the_year():
    """Without the year, week 1 of 2025 and week 1 of 2026 collapse into one bar."""
    same_week_number_different_years = pd.Series(
        [pd.Timestamp("2025-02-10"), pd.Timestamp("2026-02-09")])
    labels = _dimension_granularity_label(same_week_number_different_years, "week")
    assert labels.iloc[0] != labels.iloc[1]


def test_an_unknown_granularity_still_raises():
    """The guard stays: a typo must not silently become an empty chart."""
    with pytest.raises(ValueError):
        _dimension_granularity_label(pd.Series([_MON]), "fortnight")


@pytest.mark.parametrize("granularity", ["year", "quarter", "month", "day", "week"])
def test_every_offered_granularity_produces_a_label(granularity):
    """The pin. The forecast path offers exactly these; each must draw an axis."""
    labels = _dimension_granularity_label(pd.Series([_MON]), granularity)
    assert labels.notna().all()
