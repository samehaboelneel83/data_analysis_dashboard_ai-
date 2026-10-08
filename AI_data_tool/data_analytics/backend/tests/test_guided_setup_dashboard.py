"""Guided setup 4a: the Dashboard step -- one designer, told who the person is
and what the check found; designed once and kept; changed by asking."""
import pytest

from app.models.models import DataSource, Dataset
from app.routers.guided_setup import GOAL_MAX, design_goal


class TestGoal:
    def test_brief_and_findings_reach_the_designer(self):
        goal = design_goal({"work": "used-car dealer", "exclude": "real estate"}, {
            "health": [{"tone": "warning", "what": "27% of mileage is empty."},
                       {"tone": "good", "what": "fine"}],
            "insights": [{"what": "Coupes average 5.7M."}]})
        assert "Who they are: used-car dealer" in goal and "Leave out: real estate" in goal
        assert "- 27% of mileage is empty." in goal and "fine" not in goal
        assert "- Coupes average 5.7M." in goal
        assert "never call it the person's own" in goal

    def test_nothing_to_say_leaves_the_statistics_engine(self):
        assert design_goal({}, None) is None

    def test_capped_to_what_the_designer_accepts(self):
        goal = design_goal({"work": "x" * 900, "focus": "y" * 900, "questions": "z" * 900}, None)
        assert len(goal) <= GOAL_MAX


class TestRoutes:
    @pytest.fixture
    async def setup(self, client, db_session, two_orgs, auth_headers, monkeypatch):
        from app.routers import guided_setup

        async def run_now(db, user, tag, job, on_error=None):
            await job(db_session)
        monkeypatch.setattr(guided_setup, "_background", run_now)
        calls = []

        async def fake_design(db, user, ds, goal, count):
            calls.append((ds.id, goal, count))
            n = len(calls)
            return {"proposals": [{"title": f"Dash {n}.{i}", "rationale": "r",
                                   "widgets": [{"widget_type": "kpi", "title": "Median price", "config": {}}]}
                                  for i in range(count)], "derived": {"measures": [], "calculated_columns": []}}
        monkeypatch.setattr(guided_setup, "_design_for", fake_design)
        org = two_orgs["a"]["org"].id
        src = DataSource(name="Cars DB", type="postgresql", config={}, org_id=org, sync_status="ok")
        ds = Dataset(name="Cars", org_id=org, row_count=10)
        db_session.add_all([src, ds])
        await db_session.commit()
        await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
        await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"],
                           json={"dataset_ids": [ds.id], "brief": {"work": "dealer"}})
        return src, ds, calls

    async def test_designed_once_and_kept(self, client, auth_headers, setup):
        src, ds, calls = setup
        first = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        again = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        assert [d["proposal"]["title"] for d in again["designs"]["items"]] == ["Dash 1.0", "Dash 1.1", "Dash 1.2"]
        assert len(calls) == 1 and "Who they are: dealer" in calls[0][1]
        assert first["has_data"] is True

    async def test_a_change_replaces_only_that_dashboard(self, client, auth_headers, setup):
        src, ds, calls = setup
        body = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        did = body["designs"]["items"][1]["id"]
        await client.post(f"/api/v1/setup/{src.id}/dashboard/{did}/refine", headers=auth_headers["a"],
                          json={"message": "add a map of governorates"})
        items = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()["designs"]["items"]
        assert [d["proposal"]["title"] for d in items] == ["Dash 1.0", "Dash 2.0", "Dash 1.2"]
        assert items[1]["id"] == did and items[1]["history"] == [{"role": "user", "text": "add a map of governorates"}]
        assert "add a map of governorates" in calls[1][1] and calls[1][2] == 1

    async def test_without_datasets_nothing_is_designed(self, client, db_session, two_orgs, auth_headers, setup):
        src2 = DataSource(name="empty", type="postgresql", config={}, org_id=two_orgs["a"]["org"].id)
        db_session.add(src2)
        await db_session.commit()
        body = (await client.get(f"/api/v1/setup/{src2.id}/dashboard", headers=auth_headers["a"])).json()
        assert body["has_data"] is False and body["designs"]["asked"] is False
