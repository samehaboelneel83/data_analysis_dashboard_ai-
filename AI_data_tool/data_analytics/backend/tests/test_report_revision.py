"""Report revision counter, the basis of concurrent-edit detection.

Every mutation in this app persists immediately — there is no explicit save. That
makes two people editing one report silently last-write-wins: neither is told the
other exists. A monotonic per-report revision, bumped by any nested mutation, lets
a client notice the report moved underneath it and offer a reload.

The counter must bump for *nested* changes too (pages, widgets, bookmarks), not
just report-level fields, because that is where almost all editing happens.
"""
import pandas as pd

from app.models.models import Dataset, Report


async def _report(db_session, org_id, tmp_path):
    path = tmp_path / "r.csv"
    pd.DataFrame([{"region": "East", "sales": 1}]).to_csv(path, index=False)
    ds = Dataset(name="ds", filename=str(path), org_id=org_id, row_count=1, col_count=2)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    r = Report(name="R", dataset_id=ds.id, org_id=org_id)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def _revision(client, headers, report_id):
    resp = await client.get(f"/api/v1/reports/{report_id}/revision", headers=headers)
    assert resp.status_code == 200
    return resp.json()["revision"]


async def test_a_new_report_starts_at_revision_zero(db_session, two_orgs, auth_headers, client, tmp_path):
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)

    assert await _revision(client, auth_headers["a"], r.id) == 0


async def test_report_body_is_included_in_the_get_response(db_session, two_orgs, auth_headers, client, tmp_path):
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)

    body = (await client.get(f"/api/v1/reports/{r.id}", headers=auth_headers["a"])).json()

    assert body["revision"] == 0


async def test_patching_the_report_bumps_the_revision(db_session, two_orgs, auth_headers, client, tmp_path):
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)

    await client.patch(f"/api/v1/reports/{r.id}", json={"theme": "ocean"}, headers=auth_headers["a"])

    assert await _revision(client, auth_headers["a"], r.id) == 1


async def test_adding_a_page_bumps_the_revision(db_session, two_orgs, auth_headers, client, tmp_path):
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)

    await client.post(f"/api/v1/reports/{r.id}/pages", json={"name": "P", "position": 0}, headers=auth_headers["a"])

    assert await _revision(client, auth_headers["a"], r.id) == 1


async def test_widget_edits_bump_the_revision_since_that_is_where_editing_happens(
    db_session, two_orgs, auth_headers, client, tmp_path,
):
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)
    page = (await client.post(f"/api/v1/reports/{r.id}/pages",
                              json={"name": "P", "position": 0}, headers=auth_headers["a"])).json()
    after_page = await _revision(client, auth_headers["a"], r.id)

    widget = (await client.post(
        f"/api/v1/reports/{r.id}/pages/{page['id']}/widgets",
        json={"widget_type": "bar", "title": "W", "config": {}, "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
        headers=auth_headers["a"],
    )).json()
    after_add = await _revision(client, auth_headers["a"], r.id)

    await client.patch(
        f"/api/v1/reports/{r.id}/pages/{page['id']}/widgets/{widget['id']}",
        json={"title": "W2"}, headers=auth_headers["a"],
    )
    after_update = await _revision(client, auth_headers["a"], r.id)

    await client.delete(
        f"/api/v1/reports/{r.id}/pages/{page['id']}/widgets/{widget['id']}", headers=auth_headers["a"],
    )
    after_delete = await _revision(client, auth_headers["a"], r.id)

    assert after_add == after_page + 1
    assert after_update == after_add + 1
    assert after_delete == after_update + 1


async def test_the_revision_only_ever_increases(db_session, two_orgs, auth_headers, client, tmp_path):
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)
    seen = [await _revision(client, auth_headers["a"], r.id)]

    for theme in ("ocean", "sunset", "forest"):
        await client.patch(f"/api/v1/reports/{r.id}", json={"theme": theme}, headers=auth_headers["a"])
        seen.append(await _revision(client, auth_headers["a"], r.id))

    assert seen == sorted(seen)
    assert len(set(seen)) == len(seen)


async def test_reading_the_revision_does_not_change_it(db_session, two_orgs, auth_headers, client, tmp_path):
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)

    first = await _revision(client, auth_headers["a"], r.id)
    second = await _revision(client, auth_headers["a"], r.id)

    assert first == second


async def test_another_orgs_report_revision_is_not_readable(db_session, two_orgs, auth_headers, client, tmp_path):
    other = await _report(db_session, two_orgs["b"]["org"].id, tmp_path)

    resp = await client.get(f"/api/v1/reports/{other.id}/revision", headers=auth_headers["a"])

    assert resp.status_code == 404

async def test_deleting_a_widget_prunes_the_actions_aimed_at_it(
    db_session, two_orgs, auth_headers, client, tmp_path,
):
    """A per-pair action on a deleted widget is a permanent, silent no-op.

    `config.interaction.actions` holds target WIDGET IDS. Deleting the target
    removed the row and left every edge aimed at it in place, where it does
    nothing for ever: `actionReaches` walks to an id nothing matches and
    returns false. Nothing errors and nothing logs, and in the builder the
    author sees only that one of their targets is gone -- not that the
    remaining wiring now routes selections to a hole.

    Pruning belongs on the server: the copilot, the composer and the API all
    delete widgets without going near the builder's state.
    """
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)
    page = (await client.post(f"/api/v1/reports/{r.id}/pages",
                              json={"name": "P", "position": 0}, headers=auth_headers["a"])).json()

    def _mk(title, config):
        return client.post(
            f"/api/v1/reports/{r.id}/pages/{page['id']}/widgets",
            json={"widget_type": "bar", "title": title, "config": config,
                  "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            headers=auth_headers["a"])

    target = (await _mk("Target", {})).json()
    keeper = (await _mk("Keeper", {})).json()
    source = (await _mk("Source", {"dimension": "region", "interaction": {
        "broadcasts": True, "receives": True,
        "actions": [{"targetId": target["id"], "mode": "filter"},
                    {"targetId": keeper["id"], "mode": "highlight"}]}})).json()

    await client.delete(
        f"/api/v1/reports/{r.id}/pages/{page['id']}/widgets/{target['id']}",
        headers=auth_headers["a"])

    body = (await client.get(f"/api/v1/reports/{r.id}", headers=auth_headers["a"])).json()
    after = next(w for w in body["pages"][0]["widgets"] if w["id"] == source["id"])
    actions = after["config"]["interaction"]["actions"]

    # The dead edge is gone and the live one is untouched -- pruning must not
    # be an excuse to rewrite the author's other choices.
    assert [a["targetId"] for a in actions] == [keeper["id"]]
    assert actions[0]["mode"] == "highlight"
    assert after["config"]["interaction"]["broadcasts"] is True


async def test_pruning_leaves_a_widget_with_no_actions_alone(
    db_session, two_orgs, auth_headers, client, tmp_path,
):
    """An author who never opened the Actions pane has nothing to prune.

    Writing `actions: []` onto every sibling would turn "this widget reaches
    everything" into "this widget reaches only the listed targets, of which
    there are none" -- silencing it completely. The empty list is not a
    neutral value here."""
    r = await _report(db_session, two_orgs["a"]["org"].id, tmp_path)
    page = (await client.post(f"/api/v1/reports/{r.id}/pages",
                              json={"name": "P", "position": 0}, headers=auth_headers["a"])).json()

    async def _mk(title, config):
        return (await client.post(
            f"/api/v1/reports/{r.id}/pages/{page['id']}/widgets",
            json={"widget_type": "bar", "title": title, "config": config,
                  "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            headers=auth_headers["a"])).json()

    target = await _mk("Target", {})
    plain = await _mk("Plain", {"dimension": "region"})

    await client.delete(
        f"/api/v1/reports/{r.id}/pages/{page['id']}/widgets/{target['id']}",
        headers=auth_headers["a"])

    body = (await client.get(f"/api/v1/reports/{r.id}", headers=auth_headers["a"])).json()
    after = next(w for w in body["pages"][0]["widgets"] if w["id"] == plain["id"])
    assert "interaction" not in after["config"]
    assert after["config"] == {"dimension": "region"}
