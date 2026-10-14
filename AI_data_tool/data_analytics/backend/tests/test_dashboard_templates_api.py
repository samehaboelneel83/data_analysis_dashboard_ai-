"""The template gallery over HTTP (routers/dashboard_templates.py): who sees
what, mapping checked before anything is made, a dashboard made in one go, a
dashboard saved as a template, versions, favourites, and the dashboard style."""
import pytest
from sqlalchemy import select

from app.models.models import (DashboardTemplate, Dataset, DatasetColumn, Report, ReportPage, ReportWidget)

T = "/api/v1/templates"


@pytest.fixture
async def data(db_session, two_orgs):
    """A dataset with a date, two numbers and two categories, in org A."""
    org = two_orgs["a"]["org"]
    ds = Dataset(name="rows", filename="rows.csv", org_id=org.id,
                 column_meta={"amount": {"number": "amount", "unit": "kg"}, "planned": {"number": "amount", "unit": "kg"},
                              "ref": {"number": "code"}})
    db_session.add(ds)
    await db_session.flush()
    for name, dtype in [("ref", "numeric"), ("day", "datetime"), ("amount", "numeric"), ("planned", "numeric"),
                        ("team", "categorical"), ("kind", "categorical")]:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype))
    await db_session.commit()
    return ds


async def _dashboard(db_session, two_orgs, ds):
    report = Report(name="Mine", org_id=two_orgs["a"]["org"].id, dataset_id=ds.id,
                    created_by=two_orgs["a"]["user"].id, style={"font_family": "serif"})
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Main", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add_all([
        ReportWidget(page_id=page.id, widget_type="kpi", title="Total amount",
                     config={"measure": "amount", "aggregation": "sum",
                             "filters": [{"column": "team", "op": "eq", "value": "x"}]},
                     layout={"x": 0, "y": 0, "w": 3, "h": 3}),
        ReportWidget(page_id=page.id, widget_type="bar", title="amount by team",
                     config={"dimension": "team", "measure": "amount", "aggregation": "sum"},
                     layout={"x": 3, "y": 0, "w": 9, "h": 6})])
    await db_session.commit()
    return report


class TestTheGallery:
    async def test_the_platforms_templates_are_listed_with_what_they_need(self, client, auth_headers):
        got = (await client.get(T, headers=auth_headers["a"])).json()
        refs = {c["ref"] for c in got["templates"]}
        assert {"builtin:overview", "builtin:target", "builtin:stages"} <= refs
        card = next(c for c in got["templates"] if c["ref"] == "builtin:target")
        assert card["source"] == "builtin" and not card["can_change"] and card["preview"]
        assert {s["id"] for s in card["slots"] if s["required"]} == {"actual", "target"}

    async def test_with_a_dataset_each_template_says_how_it_suits_it_best_first(self, client, auth_headers, data):
        got = (await client.get(T, params={"dataset_id": data.id}, headers=auth_headers["a"])).json()
        scores = [c["fit"]["score"] for c in got["templates"]]
        assert scores == sorted(scores, reverse=True)
        by = {c["ref"]: c["fit"] for c in got["templates"]}
        # No place column in this data: the map template is not usable, and says what is missing.
        assert not by["builtin:geography"]["usable"] and "place" in by["builtin:geography"]["missing"]
        assert by["builtin:target"]["usable"]

    async def test_another_organisations_dataset_is_not_found(self, client, auth_headers, data):
        assert (await client.get(T, params={"dataset_id": data.id}, headers=auth_headers["b"])).status_code == 404

    async def test_a_template_draws_on_its_own_sample_rows(self, client, auth_headers):
        got = (await client.get(f"{T}/builtin:overview/preview", headers=auth_headers["a"])).json()
        widgets = got["pages"][0]["widgets"]
        assert got["rows"] > 0 and len(widgets) == 8
        assert all(w["data"].get("type") not in ("error", "empty") for w in widgets)

    async def test_a_favourite_is_ones_own(self, client, auth_headers):
        r = await client.put(f"{T}/builtin:trend/favorite", json={"on": True}, headers=auth_headers["a"])
        assert r.status_code == 200
        mine = (await client.get(T, headers=auth_headers["a"])).json()["templates"]
        theirs = (await client.get(T, headers=auth_headers["b"])).json()["templates"]
        assert next(c for c in mine if c["ref"] == "builtin:trend")["favorite"]
        assert not next(c for c in theirs if c["ref"] == "builtin:trend")["favorite"]


class TestUsingATemplate:
    async def test_the_mapping_is_suggested_checked_and_previewed_before_anything_exists(
            self, client, auth_headers, data, db_session):
        r = await client.post(f"{T}/builtin:target/match", json={"dataset_id": data.id}, headers=auth_headers["a"])
        got = r.json()
        assert r.status_code == 200, r.text
        assert {got["suggested"]["actual"][0], got["suggested"]["target"][0]} == {"amount", "planned"}
        assert "ref" not in got["candidates"]["actual"]                    # an identifier is never a number to total
        assert got["check"]["ok"] and got["preview"]["measures"]
        bad = (await client.post(f"{T}/builtin:target/match",
                                 json={"dataset_id": data.id, "mapping": {"actual": "team"}},
                                 headers=auth_headers["a"])).json()
        assert not bad["check"]["ok"] and bad["preview"] is None
        assert (await db_session.execute(select(Report))).scalars().all() == []

    async def test_a_dashboard_is_made_with_its_measures_filters_links_and_style(
            self, client, auth_headers, data, db_session):
        r = await client.post(f"{T}/builtin:target/use", json={"dataset_id": data.id, "name": "Made"},
                              headers=auth_headers["a"])
        assert r.status_code == 201, r.text
        got = r.json()
        report = await db_session.get(Report, got["report_id"])
        assert report.name == "Made" and report.origin == "template" and report.style["font_family"] == "condensed"
        widgets = (await db_session.execute(select(ReportWidget).join(ReportPage).where(
            ReportPage.report_id == report.id).order_by(ReportWidget.id))).scalars().all()
        kinds = [w.widget_type for w in widgets]
        assert kinds.count("slicer") == 2 and "gauge" in kinds
        # The charts sit below the row of filter controls.
        assert min(w.layout["y"] for w in widgets if w.widget_type != "slicer") >= 2
        await db_session.refresh(data)
        names = {m["name"] for m in data.measures}
        assert len(names) == 2 and next(w for w in widgets if w.widget_type == "gauge").config["measure"] in names
        # Used a second time: the same measures are used, not defined again.
        again = await client.post(f"{T}/builtin:target/use", json={"dataset_id": data.id}, headers=auth_headers["a"])
        await db_session.refresh(data)
        assert again.status_code == 201 and again.json()["measures"] == [] and len(data.measures) == 2

    async def test_a_mapping_that_cannot_work_makes_nothing(self, client, auth_headers, data, db_session):
        r = await client.post(f"{T}/builtin:target/use", json={"dataset_id": data.id, "mapping": {"actual": "amount"}},
                              headers=auth_headers["a"])
        assert r.status_code == 400
        assert (await db_session.execute(select(Report))).scalars().all() == []


class TestSavingATemplate:
    async def test_a_dashboard_becomes_a_personal_template_others_do_not_see(
            self, client, auth_headers, data, db_session, two_orgs):
        report = await _dashboard(db_session, two_orgs, data)
        r = await client.post(T, json={"report_id": report.id, "name": "Saved", "category": "comparison"},
                              headers=auth_headers["a"])
        assert r.status_code == 201, r.text
        card = r.json()
        assert card["source"] == "personal" and card["mine"] and card["left_out"]["filters"] == 1
        assert card["style"] == {"font_family": "serif"}
        assert {s["id"]: s["kind"] for s in card["slots"]} == {"amount": "measure", "team": "category"}
        assert (await client.get(f"{T}/{card['ref']}", headers=auth_headers["b"])).status_code == 404
        # The dashboard it came from is untouched.
        assert len((await db_session.execute(select(ReportWidget))).scalars().all()) == 2

    async def test_changing_its_content_keeps_the_version_before_and_restoring_makes_a_new_one(
            self, client, auth_headers, data, db_session, two_orgs):
        report = await _dashboard(db_session, two_orgs, data)
        card = (await client.post(T, json={"report_id": report.id, "name": "Saved"}, headers=auth_headers["a"])).json()
        tid = int(card["ref"][2:])
        r = await client.put(f"{T}/{tid}", json={"style": {"radius": 2}, "note": "square corners"},
                             headers=auth_headers["a"])
        assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["style"] == {"radius": 2}
        # A change of details alone is not a new version.
        assert (await client.put(f"{T}/{tid}", json={"name": "Renamed"}, headers=auth_headers["a"])).json()["version"] == 2
        got = (await client.get(f"{T}/{tid}/versions", headers=auth_headers["a"])).json()
        assert got["current"] == 2 and [v["version"] for v in got["versions"]] == [1]
        back = await client.post(f"{T}/{tid}/versions/{got['versions'][0]['id']}/restore", headers=auth_headers["a"])
        assert back.json() == {"version": 3, "restored": 1}
        row = await db_session.get(DashboardTemplate, tid)
        await db_session.refresh(row)
        assert row.spec["style"] == {"font_family": "serif"} and row.name == "Renamed"

    async def test_a_copy_of_a_builtin_is_ones_own_to_change_and_the_builtin_cannot_be(
            self, client, auth_headers):
        r = await client.post(T, json={"copy_of": "builtin:stages", "name": "My stages", "category": "stages"},
                              headers=auth_headers["a"])
        assert r.status_code == 201 and r.json()["can_change"] and r.json()["widgets"] == 7
        tid = int(r.json()["ref"][2:])
        assert (await client.delete(f"{T}/{tid}", headers=auth_headers["b"])).status_code == 404
        assert (await client.delete(f"{T}/{tid}", headers=auth_headers["a"])).status_code == 204


class TestTheDashboardStyle:
    async def test_it_is_saved_cleaned_and_returned(self, client, auth_headers, data, db_session, two_orgs):
        report = await _dashboard(db_session, two_orgs, data)
        r = await client.patch(f"/api/v1/reports/{report.id}",
                               json={"style": {"font_family": "mono", "border_style": "dotted", "radius": 500,
                                               "page_background": "javascript:1", "title_size": 20}},
                               headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["style"] == {"font_family": "mono", "title_size": 20, "border_style": "dotted"}
        assert (await client.get(f"/api/v1/reports/{report.id}", headers=auth_headers["a"])).json()["style"][
            "border_style"] == "dotted"


class TestLinksAreWiredToRealPages:
    async def test_a_saved_dashboards_button_and_drill_through_open_the_new_dashboards_own_pages(
            self, client, auth_headers, data, db_session, two_orgs):
        report = Report(name="Linked", org_id=two_orgs["a"]["org"].id, dataset_id=data.id,
                        created_by=two_orgs["a"]["user"].id)
        db_session.add(report)
        await db_session.flush()
        main = ReportPage(report_id=report.id, name="Main", position=0)
        detail = ReportPage(report_id=report.id, name="One team", position=1, page_type="drillthrough",
                            prompt_column="team")
        db_session.add_all([main, detail])
        await db_session.flush()
        db_session.add_all([
            ReportWidget(page_id=main.id, widget_type="bar", title="amount by team",
                         config={"dimension": "team", "measure": "amount", "aggregation": "sum",
                                 "drillthroughPageId": detail.id}, layout={"x": 0, "y": 0, "w": 8, "h": 5}),
            ReportWidget(page_id=main.id, widget_type="button", title="Details",
                         config={"label": "Details", "action": "navigate", "actionPageId": detail.id},
                         layout={"x": 8, "y": 0, "w": 4, "h": 2}),
            ReportWidget(page_id=detail.id, widget_type="line", title="amount over time",
                         config={"dimension": "day", "measure": "amount", "aggregation": "sum"},
                         layout={"x": 0, "y": 0, "w": 12, "h": 6})])
        await db_session.commit()
        card = (await client.post(T, json={"report_id": report.id, "name": "Linked"}, headers=auth_headers["a"])).json()
        made = await client.post(f"{T}/{card['ref']}/use", json={"dataset_id": data.id}, headers=auth_headers["a"])
        assert made.status_code == 201, made.text
        pages = (await db_session.execute(select(ReportPage).where(
            ReportPage.report_id == made.json()["report_id"]).order_by(ReportPage.position))).scalars().all()
        assert [p.name for p in pages] == ["Main", "One team"] and pages[1].prompt_column in ("team", "kind")
        widgets = (await db_session.execute(select(ReportWidget).where(ReportWidget.page_id == pages[0].id))).scalars().all()
        bar = next(w for w in widgets if w.widget_type == "bar")
        button = next(w for w in widgets if w.widget_type == "button")
        # The new dashboard's own page, not the page of the dashboard the template came from.
        assert bar.config["drillthroughPageId"] == pages[1].id != detail.id
        assert button.config["actionPageId"] == pages[1].id
        assert "drill_page" not in bar.config and "actionPageTitle" not in button.config


class TestATemplateOverTwoDatasets:
    async def _second(self, db_session, two_orgs, name="other"):
        ds = Dataset(name=name, filename=f"{name}.csv", org_id=two_orgs["a"]["org"].id, column_meta={})
        db_session.add(ds)
        await db_session.flush()
        for col, dtype in [("when", "datetime"), ("cost", "numeric"), ("unit", "categorical")]:
            db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype=dtype))
        await db_session.commit()
        return ds

    async def test_a_dashboard_of_two_datasets_is_saved_and_used_on_two_others(
            self, client, auth_headers, data, db_session, two_orgs):
        second = await self._second(db_session, two_orgs)
        report = Report(name="Two", org_id=two_orgs["a"]["org"].id, dataset_id=data.id,
                        additional_dataset_ids=[second.id], created_by=two_orgs["a"]["user"].id)
        db_session.add(report)
        await db_session.flush()
        page = ReportPage(report_id=report.id, name="Main", position=0)
        db_session.add(page)
        await db_session.flush()
        db_session.add_all([
            ReportWidget(page_id=page.id, widget_type="bar", title="amount by team",
                         config={"dimension": "team", "measure": "amount", "aggregation": "sum"},
                         layout={"x": 0, "y": 0, "w": 6, "h": 5}),
            ReportWidget(page_id=page.id, widget_type="bar", title="cost by unit",
                         config={"dimension": "unit", "measure": "cost", "aggregation": "sum", "dataset_id": second.id},
                         layout={"x": 6, "y": 0, "w": 6, "h": 5})])
        await db_session.commit()
        card = (await client.post(T, json={"report_id": report.id, "name": "Two"}, headers=auth_headers["a"])).json()
        assert card["datasets"] == [{"key": "d2", "label": "other"}]
        assert {s["id"] for s in card["slots"]} == {"team", "amount", "unit", "cost"}

        # Without the second dataset: its chart is left out, and nothing of it is required.
        alone = (await client.post(f"{T}/{card['ref']}/match", json={"dataset_id": data.id},
                                   headers=auth_headers["a"])).json()
        assert alone["check"]["ok"] and alone["check"]["widgets"] == {"kept": 1, "total": 2}
        assert alone["candidates"]["cost"] == []

        third = await self._second(db_session, two_orgs, "third")
        both = (await client.post(f"{T}/{card['ref']}/match",
                                  json={"dataset_id": data.id, "datasets": {"d2": third.id}},
                                  headers=auth_headers["a"])).json()
        assert both["check"]["widgets"] == {"kept": 2, "total": 2} and both["candidates"]["cost"] == ["cost"]
        assert both["datasets"] == [{"key": "d2", "label": "other", "dataset_id": third.id}]

        made = await client.post(f"{T}/{card['ref']}/use", json={"dataset_id": data.id, "datasets": {"d2": third.id}},
                                 headers=auth_headers["a"])
        assert made.status_code == 201, made.text
        new = await db_session.get(Report, made.json()["report_id"])
        assert new.additional_dataset_ids == [third.id]
        widgets = (await db_session.execute(select(ReportWidget).join(ReportPage).where(
            ReportPage.report_id == new.id).order_by(ReportWidget.id))).scalars().all()
        assert [w.config.get("dataset_id") for w in widgets] == [None, third.id]

    async def test_a_dataset_of_another_organisation_cannot_be_given(self, client, auth_headers, data, db_session, two_orgs):
        theirs = Dataset(name="theirs", filename="t.csv", org_id=two_orgs["b"]["org"].id)
        db_session.add(theirs)
        await db_session.commit()
        row = DashboardTemplate(org_id=two_orgs["a"]["org"].id, name="x", category="overview", visibility="org",
                                created_by=two_orgs["a"]["user"].id, version=1, uses=0,
                                spec={"schema": "datalytics.dashboard-template/1", "name": "x", "category": "overview",
                                      "datasets": [{"key": "d2", "label": "o"}],
                                      "slots": [{"id": "a", "kind": "measure", "required": True},
                                                {"id": "b", "kind": "measure", "dataset": "d2"}],
                                      "pages": [{"name": "P", "widgets": [
                                          {"widget_type": "kpi", "title": "a", "config": {"measure": "$a", "aggregation": "sum"}}]}]})
        db_session.add(row)
        await db_session.commit()
        r = await client.post(f"{T}/t:{row.id}/match", json={"dataset_id": data.id, "datasets": {"d2": theirs.id}},
                              headers=auth_headers["a"])
        assert r.status_code == 404
