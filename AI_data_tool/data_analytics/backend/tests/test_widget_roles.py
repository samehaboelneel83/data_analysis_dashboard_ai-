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
