"""What was expected, what fell outside it, where the level changed
(docs/discovery/PLAN.md, phase 3)."""
import numpy as np

from app.services.analysis.timeline import anomalies, change_point, expected_band, season_of


def noise(n=80, level=100.0, sd=3.0, seed=1):
    return list(level + np.random.default_rng(seed).normal(0, sd, n))


class TestTheExpectedRange:
    def test_a_planted_spike_is_the_only_period_outside_it(self):
        y = noise()
        y[60] = 160.0
        found = anomalies(y, expected_band(y))
        assert [a["index"] for a in found] == [60] and found[0]["side"] == "above" and found[0]["deviations"] > 3

    def test_plain_noise_has_almost_nothing_outside(self):
        flagged = sum(len(anomalies(y, expected_band(y))) for y in (noise(seed=s) for s in range(20)))
        assert flagged <= 6                                     # of ~1,480 judged periods

    def test_a_series_that_simply_grows_is_not_unusual(self):
        rng = np.random.default_rng(3)
        y = list(50 + 4.0 * np.arange(80) + rng.normal(0, 2, 80))
        assert anomalies(y, expected_band(y)) == []

    def test_a_weekly_rhythm_is_judged_against_the_same_weekday(self):
        rng = np.random.default_rng(4)
        y = [(300.0 if d % 7 in (5, 6) else 100.0) + rng.normal(0, 3) for d in range(98)]
        assert season_of("day", len(y)) == 7
        assert anomalies(y, expected_band(y, season=7)) == []     # the weekend peak is expected
        y[60] = 300.0                                             # a weekday at weekend level
        assert [a["index"] for a in anomalies(y, expected_band(y, season=7))] == [60]

    def test_a_period_is_never_judged_without_history_or_against_itself(self):
        y = noise(n=30)
        band = expected_band(y)
        assert band[:6] == [None] * 6 and band[6] is not None
        again = expected_band(y[:20] + [10_000.0] + y[21:])
        assert again[20] == band[20]                              # its own value does not move its range

    def test_one_earlier_spike_does_not_excuse_the_next(self):
        y = noise()
        y[50], y[56] = 170.0, 165.0
        assert [a["index"] for a in anomalies(y, expected_band(y))] == [50, 56]

    def test_gaps_and_short_series_never_raise(self):
        assert expected_band([]) == [] and anomalies([1.0, None, 2.0], expected_band([1.0, None, 2.0])) == []
        assert season_of("day", 20) is None and season_of("week", 500) is None


class TestAChangeOfLevel:
    def test_a_planted_shift_is_found_where_it_is(self):
        y = noise(n=40, level=100) + noise(n=40, level=130, seed=2)
        got = change_point(y)
        assert got and 38 <= got["index"] <= 42 and 25 < got["shift_pct"] < 35 and got["p_value"] <= 0.01

    def test_noise_and_a_steady_series_have_none(self):
        assert all(change_point(noise(seed=s)) is None for s in range(15))
        assert change_point([5.0] * 30) is None

    def test_a_shift_too_small_to_matter_is_not_reported(self):
        y = noise(n=40, level=100, sd=0.2) + noise(n=40, level=103, sd=0.2, seed=2)
        assert change_point(y) is None                            # real, and 3%: below what is worth a line

    def test_it_is_the_same_answer_every_time(self):
        y = noise(n=40, level=100) + noise(n=40, level=70, seed=2)
        assert change_point(y) == change_point(y) and change_point(y)["shift"] < 0

    def test_too_few_periods_is_no_answer(self):
        assert change_point([1.0, 2.0, 30.0, 31.0]) is None


class TestALineThatIsRead:
    def frame(self, spike=True, shift=False):
        import pandas as pd
        rng = np.random.default_rng(7)
        days = pd.date_range("2024-01-01", periods=120, freq="D")
        rows = []
        for i, d in enumerate(days):
            level = 100.0 + (40.0 if shift and i >= 70 else 0.0)
            rows.append((d, level + rng.normal(0, 3)))
        df = pd.DataFrame(rows, columns=["when", "v"])
        if spike:
            df.loc[90, "v"] = 190.0
        return df

    def draw(self, df, **extra):
        from app.services.widget_data import get_widget_data_from_df
        return get_widget_data_from_df(df, {"dimension": "when", "dimension_granularity": "day", "measure": "v",
                                            "aggregation": "sum", **extra}, "line")

    def test_the_chart_carries_its_range_and_marks_what_is_outside(self):
        got = self.draw(self.frame(), anomaly_band=True)
        marked = [r for r in got["rows"] if r.get("anomaly")]
        assert len(marked) == 1 and marked[0]["anomaly"] == "above" and marked[0]["value"] == 190.0
        assert got["anomalies"][0]["period"] == marked[0]["name"] and marked[0]["lo"] < marked[0]["hi"] < 190
        assert sum("lo" in r for r in got["rows"]) == got["band"]["judged"] and got["band"]["season"] == 7

    def test_the_place_the_level_changed_is_named(self):
        got = self.draw(self.frame(spike=False, shift=True), change_point=True)
        cp = got["change_point"]
        assert cp and 35 < cp["shift_pct"] < 45 and cp["period"] == got["rows"][cp["index"]]["name"]
        assert 68 <= cp["index"] <= 72

    def test_a_plain_line_is_exactly_as_before(self):
        got = self.draw(self.frame())
        assert "anomalies" not in got and "change_point" not in got and all("lo" not in r for r in got["rows"])

    def test_a_split_chart_is_not_read(self):
        df = self.frame().assign(g=lambda d: np.where(d.index % 2, "a", "b"))
        got = self.draw(df, anomaly_band=True, dimension2="g")
        assert "anomalies" not in got


class TestTheInsightScan:
    def months(self, spike=None, shift=None, seed=5):
        import pandas as pd
        rng = np.random.default_rng(seed)
        days = pd.date_range("2022-01-01", "2024-12-31", freq="D")
        rows = []
        for d in days:
            k = (d.year - 2022) * 12 + d.month - 1
            level = 100.0 * (1.5 if shift is not None and k >= shift else 1.0) * (2.2 if k == spike else 1.0)
            rows += [(d, level + rng.normal(0, 4)) for _ in range(6)]
        return pd.DataFrame(rows, columns=["when", "amount"])

    TYPES = {"when": "datetime", "amount": "numeric"}
    META = {"amount": {"number": "amount"}}

    def scan(self, df):
        from app.services.insights import generate_insights
        return generate_insights(df, self.TYPES, self.META)["findings"]

    def test_a_month_far_outside_its_range_is_a_finding_and_a_read_line(self):
        from app.services.insights import suggest_widgets_from_findings
        df = self.months(spike=20)
        found = [f for f in self.scan(df) if f["kind"] == "anomaly"]
        assert found and found[0]["figures"]["period"] == "2023-09" and "far above its usual range" in found[0]["title"]
        sug = suggest_widgets_from_findings(found, self.TYPES, None, column_meta=self.META, frame=df)
        chart = next(s for s in sug if s["title"] == found[0]["title"])
        assert chart["widget_type"] == "line" and chart["config"]["anomaly_band"] is True

    def test_a_change_of_level_is_a_finding_with_its_month(self):
        found = [f for f in self.scan(self.months(shift=18)) if f["kind"] == "change_point"]
        assert found and found[0]["figures"]["period"] in ("2023-06", "2023-07", "2023-08")
        assert "higher since" in found[0]["title"] and 40 < found[0]["figures"]["shift_pct"] < 60

    def test_a_steady_measure_gets_neither(self):
        kinds = {f["kind"] for f in self.scan(self.months())}
        assert not kinds & {"anomaly", "change_point"}


def test_a_series_of_raw_rows_is_not_judged_as_a_timeline():
    """Un-grouped timestamps (one point per record) are not periods."""
    from app.services import widget_data
    rows = [{"name": str(i), "value": float(i % 7)} for i in range(widget_data.TIMELINE_MAX_POINTS + 1)]
    result = {"rows": rows}
    widget_data.read_timeline(result, {"anomaly_band": True, "change_point": True})
    assert result["timeline_skipped"] == "too_many_points"
    assert "anomalies" not in result and "change_point" not in result and "lo" not in rows[50]


def test_a_read_line_carries_a_few_notes_pinned_to_their_periods():
    """The shift and the periods furthest outside, in time order, numbered; what and when, never why."""
    from app.services import widget_data
    values = [100.0] * 12 + [101, 99, 100, 300, 100, 101] + [160.0] * 14
    rows = [{"name": f"2024-W{i + 1:02d}", "value": v} for i, v in enumerate(values)]
    result = {"rows": rows}
    widget_data.read_timeline(result, {"anomaly_band": True, "change_point": True, "dimension_granularity": "week"})
    notes = result["notes"]
    assert 1 <= len(notes) <= widget_data.TIMELINE_NOTES and [n["n"] for n in notes] == list(range(1, len(notes) + 1))
    assert [n["period"] for n in notes] == sorted(n["period"] for n in notes)
    spike = next(n for n in notes if n["kind"] == "above")
    assert spike["period"] == "2024-W16" and "300" in spike["text"] and "at most" in spike["text"]
    shift = next(n for n in notes if n["kind"] == "shift")
    assert "rose" in shift["text"] and "since" in shift["text"]
    assert not any(w in " ".join(n["text"] for n in notes).lower() for w in ("because", "due to", "caused"))


def test_a_line_with_nothing_to_say_has_no_notes():
    from app.services import widget_data
    result = {"rows": [{"name": f"p{i:02d}", "value": 100.0 + (i % 3)} for i in range(30)]}
    widget_data.read_timeline(result, {"anomaly_band": True, "change_point": True})
    assert "notes" not in result
