"""Guided setup v2, step 4: pages designed for what the person asked -- designed
once and kept, changed in place, and made into ONE dashboard."""
import pytest

from app.models.models import DataSource, Dataset, Report

DEMAND = {"sentence": "Express parcels: how many are late", "who": "ops manager", "subject": "Express parcels",
          "questions": [{"id": "q1", "text": "How many are late?"}], "exclude": [], "scope": [], "source": "ai"}


class TestRoutes:
    @pytest.fixture
    async def setup(self, client, db_session, two_orgs, auth_headers, monkeypatch):
        from app.routers import guided_setup
        from app.services.guided_setup import answer

        async def run_now(db, user, tag, job, on_error=None):
            await job(db_session)
        monkeypatch.setattr(guided_setup, "_background", run_now)
        calls = []

        async def fake_demand(db, f, user, lang, edits, earlier=None):
            calls.append(("demand", list(edits)))
            return {**DEMAND, "sentence": edits[-1] if edits else DEMAND["sentence"]}
        monkeypatch.setattr(guided_setup, "build_demand", fake_demand)

        def page(title):
            return {"title": title, "rationale": "r", "answer": "17% are late.", "unanswered": [], "answers": ["q1"],
                    "widgets": [{"widget_type": "kpi", "title": "Late share", "config": {}, "question": "q1"}]}

        async def fake_design(db, user, ds, dem, entry, lang, count, client, **kw):
            calls.append(("design", dem.get("sentence"), count))
            n = sum(1 for c in calls if c[0] == "design")
            return {"proposals": [page(f"Page {n}.{i}") for i in range(count)], "reason": ""}

        async def fake_change(db, user, ds, dem, entry, current, message, lang, client, **kw):
            calls.append(("change", current["title"], message))
            return page(current["title"] + " (changed)")
        monkeypatch.setattr(answer, "design", fake_design)
        monkeypatch.setattr(answer, "change", fake_change)
        org = two_orgs["a"]["org"].id
        src = DataSource(name="Nile Express", type="postgresql", config={}, org_id=org, sync_status="ok")
        ds = Dataset(name="Parcels", org_id=org, row_count=10)
        db_session.add_all([src, ds])
        await db_session.commit()
        await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
        await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"],
                           json={"dataset_ids": [ds.id], "brief": {"work": "ops manager"}})
        return src, ds, calls

    async def test_designed_once_for_what_was_asked_and_kept(self, client, auth_headers, setup):
        src, ds, calls = setup
        first = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        again = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        assert [d["proposal"]["title"] for d in again["designs"]["items"]] == ["Page 1.0", "Page 1.1", "Page 1.2"]
        # The request is written down first, and the design is made FOR it -- once.
        assert calls == [("demand", []), ("design", DEMAND["sentence"], 3)]
        assert first["has_data"] is True and again["demand"]["sentence"] == DEMAND["sentence"]

    async def test_a_change_touches_only_that_page(self, client, auth_headers, setup):
        src, ds, calls = setup
        body = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        did = body["designs"]["items"][1]["id"]
        await client.post(f"/api/v1/setup/{src.id}/dashboard/{did}/refine", headers=auth_headers["a"],
                          json={"message": "add a chart by month"})
        items = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()["designs"]["items"]
        assert [d["proposal"]["title"] for d in items] == ["Page 1.0", "Page 1.1 (changed)", "Page 1.2"]
        assert items[1]["id"] == did and items[1]["history"] == [{"role": "user", "text": "add a chart by month"}]
        assert calls[-1] == ("change", "Page 1.1", "add a chart by month")

    async def test_correcting_what_was_understood_designs_again_for_it(self, client, auth_headers, setup):
        src, ds, calls = setup
        await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])
        changed = (await client.post(f"/api/v1/setup/{src.id}/demand/change", headers=auth_headers["a"],
                                     json={"message": "Same Day parcels only"})).json()
        assert changed["demand"]["sentence"] == "Same Day parcels only"
        assert changed["demand"]["edits"] == ["Same Day parcels only"]
        body = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        assert calls[-1] == ("design", "Same Day parcels only", 3)
        assert [d["proposal"]["title"] for d in body["designs"]["items"]] == ["Page 2.0", "Page 2.1", "Page 2.2"]

    async def test_the_pages_chosen_make_one_dashboard_and_finish_the_analysis(
            self, client, db_session, two_orgs, auth_headers, setup):
        src, ds, calls = setup
        body = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        ids = [d["id"] for d in body["designs"]["items"]]
        report = Report(name="Express parcels", org_id=two_orgs["a"]["org"].id, dataset_id=ds.id)
        db_session.add(report)
        await db_session.commit()
        done = (await client.post(f"/api/v1/setup/{src.id}/dashboard/used", headers=auth_headers["a"],
                                  json={"report_id": report.id, "design_ids": ids[:2]})).json()
        assert done["step"] == "done" and done["report_id"] == report.id
        # Adding the third later goes to the SAME dashboard.
        await client.post(f"/api/v1/setup/{src.id}/dashboard/used", headers=auth_headers["a"],
                          json={"report_id": report.id, "design_ids": ids[2:]})
        body = (await client.get(f"/api/v1/setup/{src.id}/dashboard", headers=auth_headers["a"])).json()
        assert body["designs"]["used"] == ids and body["designs"]["report_id"] == report.id

    async def test_another_orgs_dashboard_cannot_be_claimed(self, client, db_session, two_orgs, auth_headers, setup):
        src, ds, calls = setup
        other = Report(name="theirs", org_id=two_orgs["b"]["org"].id)
        db_session.add(other)
        await db_session.commit()
        resp = await client.post(f"/api/v1/setup/{src.id}/dashboard/used", headers=auth_headers["a"],
                                 json={"report_id": other.id, "design_ids": []})
        assert resp.status_code == 404

    async def test_without_datasets_nothing_is_designed(self, client, db_session, two_orgs, auth_headers, setup):
        src2 = DataSource(name="empty", type="postgresql", config={}, org_id=two_orgs["a"]["org"].id)
        db_session.add(src2)
        await db_session.commit()
        body = (await client.get(f"/api/v1/setup/{src2.id}/dashboard", headers=auth_headers["a"])).json()
        assert body["has_data"] is False and body["designs"]["asked"] is False
