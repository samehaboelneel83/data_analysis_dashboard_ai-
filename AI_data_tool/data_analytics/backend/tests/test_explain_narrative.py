"""A sentence to go with the automated explanation.

`explain_response` ranks what moves a column and returns a relationship plot.
SAS's version of this speaks: it produces a generated narrative alongside the
factors. Ours returned numbers and left the reader to phrase the finding for
themselves — and the machinery to say it was already here, guarded, with a
caller: `narrate_one`, which the Dynamic Pin card uses.

The interesting properties are all about what happens when the model is NOT
available, because that is the common case in an air-gapped install and the one
a demo never shows:

  * The explanation still returns. Narration is an addition to the answer, not
    a precondition for it.
  * A missing sentence is `null`, not an empty string — "the model said
    nothing" and "there is no model" must not both render as a blank line.
  * The sentence is FLAGGED as generated. A reader deciding something on the
    strength of a line has a right to know a model wrote it.

The digit guard inside `narrate_one` does the rest: a sentence stating a number
the evidence does not contain is discarded there, and the caller keeps the
figures.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.security import hash_password
from app.models.models import Dataset, DatasetColumn, User


@pytest.fixture
def salesfile(tmp_path):
    """Spend genuinely moves revenue, so there is a top factor to talk about."""
    rng = np.random.default_rng(0)
    n = 200
    spend = rng.normal(100, 20, n)
    p = tmp_path / "s.csv"
    pd.DataFrame({
        "spend": spend.round(2),
        "revenue": (spend * 3 + rng.normal(0, 5, n)).round(2),
        "region": rng.choice(["N", "S"], n),
    }).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org, path):
    ds = Dataset(name="S", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("spend", "numeric"), ("revenue", "numeric"), ("region", "categorical")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    await db.refresh(ds)
    return ds


@pytest.mark.asyncio
async def test_the_explanation_carries_a_generated_sentence(
        client, auth_headers, db_session, two_orgs, salesfile, monkeypatch):
    ds = await _dataset(db_session, two_orgs["a"]["org"], salesfile)

    async def _fake(finding):
        # The finding must carry enough for a sentence to be about something.
        assert finding.get("title")
        assert "revenue" in (finding.get("title", "") + finding.get("detail", ""))
        return "Spend is the strongest driver of revenue."

    monkeypatch.setattr("app.services.insights.narrate_one", _fake)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/explain",
                             params={"column": "revenue"}, headers=auth_headers["a"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["narrative"] == "Spend is the strongest driver of revenue."
    # Flagged, because a reader acting on the line deserves to know what wrote it.
    assert body["narrative_source"] == "model"
    # And the numbers are still the answer.
    assert body["factors"]


@pytest.mark.asyncio
async def test_an_explanation_survives_a_silent_model(
        client, auth_headers, db_session, two_orgs, salesfile, monkeypatch):
    """The air-gapped case, and the breaker case, and the timeout case.

    `narrate_one` returns None for all three. The explanation is the factors;
    the sentence is a courtesy."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], salesfile)

    async def _silent(_finding):
        return None

    monkeypatch.setattr("app.services.insights.narrate_one", _silent)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/explain",
                             params={"column": "revenue"}, headers=auth_headers["a"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["factors"], "the explanation itself must not depend on the model"
    # null, not "" -- a blank string renders as an empty line that looks like a
    # sentence failed to load rather than one that was never offered.
    assert body["narrative"] is None
    assert body["narrative_source"] is None


@pytest.mark.asyncio
async def test_a_narration_failure_never_fails_the_request(
        client, auth_headers, db_session, two_orgs, salesfile, monkeypatch):
    """A model that raises is the same as a model that is down.

    Letting it propagate would turn "we could not phrase this" into "we could
    not explain this", losing an answer that was already computed."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], salesfile)

    async def _explodes(_finding):
        raise RuntimeError("vLLM unreachable")

    monkeypatch.setattr("app.services.insights.narrate_one", _explodes)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/explain",
                             params={"column": "revenue"}, headers=auth_headers["a"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["factors"]
    assert resp.json()["narrative"] is None


@pytest.mark.asyncio
async def test_nothing_to_explain_is_not_narrated(
        client, auth_headers, db_session, two_orgs, tmp_path, monkeypatch):
    """No factor means no finding, and a sentence about nothing is worse than
    silence -- it reads as a conclusion."""
    p = tmp_path / "flat.csv"
    pd.DataFrame({"a": [1.0] * 80, "b": [2.0] * 80}).to_csv(p, index=False)
    ds = Dataset(name="Flat", filename=str(p), org_id=two_orgs["a"]["org"].id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    for c in ("a", "b"):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="numeric"))
    await db_session.commit()
    await db_session.refresh(ds)

    called = {"n": 0}

    async def _count(_finding):
        called["n"] += 1
        return "something"

    monkeypatch.setattr("app.services.insights.narrate_one", _count)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/explain",
                             params={"column": "a"}, headers=auth_headers["a"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["narrative"] is None
    assert called["n"] == 0, "asked a model to phrase a finding that does not exist"


@pytest.mark.asyncio
async def test_explain_this_is_scoped_to_the_widgets_rows(client, auth_headers, db_session, two_orgs, salesfile, monkeypatch):
    """The reader's "Explain this" explains what the widget shows: its filters apply."""
    ds = await _dataset(db_session, two_orgs["a"]["org"], salesfile)

    async def _none(finding):
        return None
    monkeypatch.setattr("app.services.insights.narrate_one", _none)
    whole = (await client.post(f"/api/v1/datasets/{ds.id}/explain", params={"column": "revenue"},
                               headers=auth_headers["a"])).json()
    north = (await client.post(f"/api/v1/datasets/{ds.id}/explain", params={"column": "revenue"},
                               json={"filters": [{"column": "region", "op": "eq", "value": "N"}]},
                               headers=auth_headers["a"])).json()
    assert north["rows"] < whole["rows"] == whole["rows_before_filters"]
    assert north["rows_before_filters"] == whole["rows"]
    assert north["factors"][0]["column"] == "spend"
