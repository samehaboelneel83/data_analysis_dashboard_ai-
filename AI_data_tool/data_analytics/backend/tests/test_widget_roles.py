"""What each widget type must be given before it can draw.

The frontend has always known this — `ROLE_SPECS` in `types/report.ts` marks
each role `required` and the config panel refuses to save without them. The
server knew nothing about it: `get_widget_data` accepts any config, and a widget
missing a required role falls through to a shaper that returns `{"type":
"empty"}`. On screen that is a tile reading "No data", with no way to tell it
apart from a filter that excluded every row.

That gap was survivable while every widget was built by a person in the panel.
It stops being survivable the moment a model proposes widgets: an LLM handed a
menu of 64 widget types will confidently bind a bubble chart to one measure, and
the first a user hears of it is a blank rectangle.

So the requirement moves server-side, and a parity test keeps the two copies
honest — the frontend file is the source of truth and this test re-derives from
it, the same way the architecture doc test re-derives its counts.
"""
import re
from pathlib import Path

import pytest

from app.services.widget_roles import (
    REQUIRED_ROLES, config_key_for_role, missing_roles,
)

SPEC_FILE = (Path(__file__).resolve().parents[2]
             / "frontend" / "src" / "types" / "report.ts")


def frontend_required() -> dict[str, set[str]]:
    """The required roles per widget type, read out of the TypeScript source."""
    text = SPEC_FILE.read_text(encoding="utf-8")
    block = re.search(r"export const ROLE_SPECS[^=]*=\s*\{(.*?)\n\}", text, re.S)
    assert block, "ROLE_SPECS not found in report.ts"
    out: dict[str, set[str]] = {}
    # Each entry is `name: [ {...}, {...} ],` — possibly across several lines. The
    # sentinel gives the LAST entry something to look ahead to; without it the
    # final widget type is silently skipped, and a parity test that cannot see a
    # widget type cannot report it missing.
    spec_body = block.group(1) + "\n  __sentinel__:"
    for m in re.finditer(r"(\w+):\s*\[(.*?)\],?\s*(?=\n\s*(?:\w+:|//|/\*))",
                         spec_body, re.S):
        name, body = m.group(1), m.group(2)
        roles = set()
        for entry in re.finditer(r"\{([^}]*)\}", body):
            piece = entry.group(1)
            role = re.search(r"role:\s*'([^']+)'", piece)
            if role and re.search(r"required:\s*true", piece):
                roles.add(role.group(1))
        out[name] = roles
    return out


class TestParityWithTheFrontend:
    def test_the_spec_file_was_actually_read(self):
        """A parser that quietly returns nothing would make every test below
        pass. The catalogue is 65 types and the doc tests already pin that."""
        assert len(frontend_required()) == 74, sorted(frontend_required())

    def test_every_widget_type_is_covered(self):
        missing = set(frontend_required()) - set(REQUIRED_ROLES)
        assert not missing, f"no server-side requirement for: {sorted(missing)}"

    def test_no_widget_type_is_invented(self):
        extra = set(REQUIRED_ROLES) - set(frontend_required())
        assert not extra, f"not a real widget type: {sorted(extra)}"

    @pytest.mark.parametrize("widget", sorted(frontend_required()))
    def test_the_required_roles_agree(self, widget):
        assert set(REQUIRED_ROLES[widget]) == frontend_required()[widget]


class TestMissingRoles:
    def test_a_complete_config_is_accepted(self):
        assert missing_roles("bar", {"dimension": "dept", "measure": "cost"}) == []

    def test_a_bubble_with_one_measure_is_refused(self):
        """The exact mistake that produced a blank tile on a hospital dashboard."""
        got = missing_roles("bubble", {"dimension": "payer", "measure": "net_egp"})
        assert set(got) == {"measure2", "size"}

    def test_a_ribbon_without_its_second_dimension_is_refused(self):
        got = missing_roles("ribbon", {"dimension": "arrived_at", "measure": "id"})
        assert got == ["dimension2"]

    def test_a_map_line_needs_both_ends(self):
        got = missing_roles("map_lines", {"lat": "a", "lon": "b"})
        assert set(got) == {"lat2", "lon2"}

    def test_it_reports_config_keys_not_role_names(self):
        """Callers write configs, so the answer has to name what to add."""
        assert missing_roles("sankey", {"dimension": "a", "measure": "m"}) == ["dimension2"]

    def test_an_unknown_widget_type_requires_nothing(self):
        """Unknown types already render through the fallback shaper; refusing
        them here would break a widget the rest of the system accepts."""
        assert missing_roles("something_new", {}) == []

    def test_the_roles_dict_form_is_understood_too(self):
        assert missing_roles("bubble", {"roles": {
            "category": "payer", "measure": "x", "measure2": "y", "size": "s"}}) == []


class TestConfigKeyForRole:
    @pytest.mark.parametrize("role,key", [
        ("category", "dimension"), ("category2", "dimension2"),
        ("measure", "measure"), ("measure2", "measure2"), ("size", "size"),
        ("lat2", "lat2"), ("direction", "direction"), ("measures", "measures"),
    ])
    def test_it_matches_the_panel(self, role, key):
        assert config_key_for_role(role) == key


# ── E03 slice 1: the server knows what a widget is ────────────────────────────

class TestValidateWidgetPayload:
    """Saving used to accept any widget type and any config. Each case below
    stored fine and then failed far from its cause -- an empty tile, a SUM
    where a median was asked for, a filter nobody applied."""

    @pytest.mark.parametrize("wtype,cfg,field", [
        ("barchart", {}, "widget type"),
        ("bar", {"aggregation": "medain"}, "aggregation"),
        ("bar", {"aggregation2": 7}, "aggregation2"),
        ("bar", {"filters": "region = North"}, "filters"),
        ("bar", {"filters": ["region"]}, "filters[0]"),
        ("bar", {"filters": [{"column": 3, "op": "eq"}]}, "filters[0].column"),
        ("bar", {"measures": "revenue"}, "measures"),
        ("bar", {"roles": ["dimension"]}, "roles"),
    ])
    def test_refused_with_the_field_named(self, wtype, cfg, field):
        from app.services.widget_roles import InvalidWidget, validate_widget_payload
        with pytest.raises(InvalidWidget, match=re.escape(field)):
            validate_widget_payload(wtype, cfg)

    @pytest.mark.parametrize("cfg", [
        {},
        {"dimension": "region", "measure": "revenue", "aggregation": "SUM"},
        {"aggregation": "", "aggregation2": None},
        {"filters": [], "measures": [], "roles": {}},
        {"filters": [{"column": "region", "op": "eq", "value": "N"}, {"op": "and"}]},
        # Unknown extra keys are renderer options -- allowed in this slice.
        {"bar_mode": "stacked", "some_future_option": {"a": 1}},
    ])
    def test_shapes_the_live_data_uses_still_pass(self, cfg):
        from app.services.widget_roles import validate_widget_payload
        validate_widget_payload("bar", cfg)

    def test_every_frontend_type_is_accepted(self):
        from app.services.widget_roles import validate_widget_payload
        for wtype in REQUIRED_ROLES:
            validate_widget_payload(wtype, {})


class TestEveryAggregationNameMeansOneThing:
    """Both pandas paths fall back to SUM for a name they do not know. The
    scalar path (a KPI) knew `standard_error`, `coefficient_of_variation`,
    `t_statistic`... and the grouped path (a bar chart) did not -- so the same
    config showed the statistic on one widget and a sum on the other."""

    def test_the_scalar_and_grouped_paths_agree_on_every_name(self):
        import math
        import pandas as pd
        from app.services.widget_data import AGGREGATION_NAMES, _agg_series, _pandas_agg_fn
        s = pd.Series([2.0, 3.0, 5.0, 7.0, 11.0, 13.0])
        df = pd.DataFrame({"g": ["a"] * len(s), "v": s})
        for name in sorted(AGGREGATION_NAMES):
            scalar = _agg_series(s, name)
            grouped = df.groupby("g")["v"].agg(_pandas_agg_fn(name)).iloc[0]
            assert math.isclose(float(scalar), float(grouped), rel_tol=1e-9), (name, scalar, grouped)

    def test_the_long_names_are_not_summed(self):
        import pandas as pd
        from app.services.widget_data import _pandas_agg_fn
        df = pd.DataFrame({"g": ["a"] * 4, "v": [1.0, 2.0, 3.0, 10.0]})
        total = df["v"].sum()
        for name in ("standard_error", "coefficient_of_variation", "t_statistic", "p_value",
                     "uncorrected_sum_of_squares", "corrected_sum_of_squares"):
            got = df.groupby("g")["v"].agg(_pandas_agg_fn(name)).iloc[0]
            assert got != total, name


class TestSavingValidates:
    async def _page(self, client, headers):
        rep = (await client.post("/api/v1/reports", json={"name": "V"}, headers=headers)).json()
        return rep, rep["pages"][0]["id"]

    async def test_add_widget_refuses_an_unknown_type_and_a_bad_aggregation(
            self, client, auth_headers):
        rep, page = await self._page(client, auth_headers["a"])
        url = f"/api/v1/reports/{rep['id']}/pages/{page}/widgets"
        for body in ({"widget_type": "piechart", "config": {}},
                     {"widget_type": "bar", "config": {"aggregation": "averge"}}):
            r = await client.post(url, json={**body, "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
                                  headers=auth_headers["a"])
            assert r.status_code == 400, r.text

    async def test_a_patch_is_judged_on_what_it_changes(self, client, auth_headers):
        rep, page = await self._page(client, auth_headers["a"])
        w = (await client.post(f"/api/v1/reports/{rep['id']}/pages/{page}/widgets",
                               json={"widget_type": "bar", "config": {"aggregation": "sum"},
                                     "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
                               headers=auth_headers["a"])).json()
        url = f"/api/v1/reports/{rep['id']}/pages/{page}/widgets/{w['id']}"
        moved = await client.patch(url, json={"layout": {"x": 1, "y": 0, "w": 6, "h": 4}},
                                   headers=auth_headers["a"])
        assert moved.status_code == 200, moved.text
        bad = await client.patch(url, json={"config": {"filters": "x"}}, headers=auth_headers["a"])
        assert bad.status_code == 400


# ── E03 slice 2: options a widget type cannot honour ──────────────────────────

CAPS_FILE = SPEC_FILE.parent.parent / "components" / "report" / "widgetCapabilities.ts"


def frontend_capabilities() -> dict[str, set[str]]:
    """CAPABILITIES in widgetCapabilities.ts, spreads resolved."""
    text = CAPS_FILE.read_text(encoding="utf-8")
    consts = {name: set(re.findall(r"'(\w+)'", body)) for name, body in re.findall(
        r"const (\w+): FormattingCapability\[\] = \[([^\]]*)\]", text)}
    block = re.search(r"const CAPABILITIES[^=]*=\s*\{(.*?)\n\}", text, re.S)
    assert block, "CAPABILITIES not found in widgetCapabilities.ts"
    out: dict[str, set[str]] = {}
    for name, value in re.findall(r"^\s*(\w+):\s*(.+?),?\s*$", block.group(1), re.M):
        caps: set[str] = set()
        for spread in re.findall(r"\.\.\.(\w+)", value):
            caps |= consts[spread]
        caps |= set(re.findall(r"'(\w+)'", value))
        if value.strip().rstrip(",") in consts:          # `bubble: FULL_WITH_LEGEND`
            caps |= consts[value.strip().rstrip(",")]
        out[name] = caps
    return out


class TestCapabilityParityWithTheFrontend:
    def test_the_capability_file_was_actually_read(self):
        caps = frontend_capabilities()
        assert len(caps) >= 25 and "bar" in caps and "table" in caps

    def test_every_type_grants_the_same_options_on_both_sides(self):
        from app.services.widget_roles import FORMATTING_CAPABILITIES
        fe = frontend_capabilities()
        assert set(fe) == set(FORMATTING_CAPABILITIES), (
            "widget types differ: add or remove them in widget_roles.FORMATTING_CAPABILITIES")
        for wtype, caps in fe.items():
            assert FORMATTING_CAPABILITIES[wtype] == caps, wtype

    def test_every_capability_has_its_keys(self):
        from app.services.widget_roles import CAPABILITY_KEYS
        used = set().union(*frontend_capabilities().values())
        assert used <= set(CAPABILITY_KEYS), used - set(CAPABILITY_KEYS)


class TestUnsupportedOptionsAreRefused:
    @pytest.mark.parametrize("wtype,cfg,key", [
        ("pie", {"y_scale": "log"}, "y_scale"),
        ("dual_axis_bar", {"y_min": 0}, "y_min"),           # would clip the wrong axis
        ("word_cloud", {"grid": True}, "grid"),
        ("box_plot", {"x_axis_angle": 0}, "x_axis_angle"),   # seen live, from a model
        ("kpi", {"data_labels": True}, "data_labels"),
        ("bar", {"show_totals": True}, "show_totals"),
    ])
    def test_named_in_the_refusal(self, wtype, cfg, key):
        from app.services.widget_roles import InvalidWidget, validate_widget_payload
        with pytest.raises(InvalidWidget, match=f"{key} has no effect on a {wtype}"):
            validate_widget_payload(wtype, cfg)

    @pytest.mark.parametrize("wtype,cfg", [
        ("bar", {"y_scale": "log", "x_axis_angle": -45, "series_patterns": True, "overview_axis": True}),
        ("donut", {"legend": False, "data_labels": True, "series_patterns": True}),
        ("table", {"show_totals": True, "totals_position": "before", "show_subtotals": False}),
        ("pie", {"y_scale": None, "grid": ""}),                # unset values are not options
    ])
    def test_granted_or_unset_options_pass(self, wtype, cfg):
        from app.services.widget_roles import validate_widget_payload
        validate_widget_payload(wtype, cfg)

    def test_the_suggestion_generator_drops_them_instead_of_proposing_them(self):
        from app.services.suggest_dataset_dashboard import polish_widget
        out = polish_widget({"widget_type": "box_plot", "title": "Spread",
                             "config": {"measure": "tat", "x_axis_angle": 0}},
                            {"columns": [], "structure": {}})
        assert "x_axis_angle" not in out["config"]
        assert out["config"]["measure"] == "tat"


class TestATypeSwitchIsJudgedAsTheWidgetItBecomes:
    async def test_switching_to_a_type_that_ignores_an_option_is_refused(
            self, client, auth_headers):
        h = auth_headers["a"]
        rep = (await client.post("/api/v1/reports", json={"name": "S"}, headers=h)).json()
        page = rep["pages"][0]["id"]
        w = (await client.post(f"/api/v1/reports/{rep['id']}/pages/{page}/widgets",
                               json={"widget_type": "bar", "config": {"y_scale": "log"},
                                     "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
                               headers=h)).json()
        url = f"/api/v1/reports/{rep['id']}/pages/{page}/widgets/{w['id']}"
        r = await client.patch(url, json={"widget_type": "pie"}, headers=h)
        assert r.status_code == 400 and "y_scale" in r.text
        # ...and the same switch with the config the builder would send passes.
        r = await client.patch(url, json={"widget_type": "pie", "config": {}}, headers=h)
        assert r.status_code == 200, r.text


class TestAKpiNeedsOnlyAMeasure:
    """REQUIRED_ROLES["kpi"] became ("measure",) to mirror ROLE_SPECS. That
    makes the dimension OPTIONAL, not forbidden: a KPI saved with a dimension
    before the change must still validate, save and load."""

    def test_the_measure_is_the_only_requirement(self):
        assert missing_roles("kpi", {"measure": "sales"}) == []
        assert missing_roles("kpi", {"dimension": "region", "measure": "sales"}) == []
        assert missing_roles("kpi", {"dimension": "region"}) == ["measure"]

    def test_a_kpi_with_a_dimension_still_validates(self):
        from app.services.widget_roles import validate_widget_payload
        validate_widget_payload("kpi", {"dimension": "region", "measure": "sales", "aggregation": "sum"})
        validate_widget_payload("kpi", {"measure": "sales", "aggregation": "sum"})

    async def test_both_shapes_save_and_load(self, client, auth_headers):
        h = auth_headers["a"]
        rep = (await client.post("/api/v1/reports", json={"name": "K"}, headers=h)).json()
        page = rep["pages"][0]["id"]
        url = f"/api/v1/reports/{rep['id']}/pages/{page}/widgets"
        ids = []
        for cfg in ({"measure": "sales", "aggregation": "sum"},
                    {"dimension": "region", "measure": "sales", "aggregation": "sum"}):
            r = await client.post(url, json={"widget_type": "kpi", "config": cfg,
                                             "layout": {"x": 0, "y": 0, "w": 3, "h": 3}}, headers=h)
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
        # ...and an existing one with a dimension can be edited and re-saved.
        r = await client.patch(f"{url}/{ids[1]}", json={"config": {
            "dimension": "region", "measure": "sales", "aggregation": "avg"}}, headers=h)
        assert r.status_code == 200, r.text
        loaded = (await client.get(f"/api/v1/reports/{rep['id']}", headers=h)).json()
        kpis = {w["id"]: w["config"] for p in loaded["pages"] for w in p["widgets"]}
        assert kpis[ids[1]]["dimension"] == "region" and kpis[ids[1]]["aggregation"] == "avg"
        assert "dimension" not in kpis[ids[0]]
