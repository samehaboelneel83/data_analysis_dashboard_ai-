"""The HTTP surface for "suggest dashboards for this dataset".

A service that works and an endpoint that reaches it are different things, and
this repository has shipped three features whose service layer was correct while
the endpoint still refused the case. So: the guard, the shape of the answer, and
the fact that the person's own words reach the model.

The model itself is replaced here. What is being tested is that the endpoint
assembles the right inputs, respects the same security every other dataset route
does, and returns something the UI can render.
"""
import pandas as pd
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import (
    ColumnSecurityRule, Dataset, DatasetColumn, Entity, Role, User,
)


@pytest.fixture
def clinic_csv(tmp_path):
    p = tmp_path / "clinic.csv"
    pd.DataFrame({
        "visit_id": range(1, 31),
        "department": ["Cardiology", "ENT", "Oncology"] * 10,
        "wait_minutes": [20, 40, 60] * 10,
        "cost": [100.0, 250.0, 700.0] * 10,
        "salary": [1.0] * 30,
    }).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org, path, *, deny=None):
    ds = Dataset(name="Clinic", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("visit_id", "numeric"), ("department", "categorical"),
                 ("wait_minutes", "numeric"), ("cost", "numeric"),
                 ("salary", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    role = Role(org_id=org.id, name="analyst", is_org_admin=False)
    db.add(role)
    await db.flush()
    if deny:
        db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=deny))
    user = User(org_id=org.id, role_id=role.id, email="analyst@example.com",
                password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    # OWNED, deliberately. `readable_dataset_ids` treats a dataset with no
    # `created_by` as readable by the whole org -- that is the rule for legacy
    # rows, and a dataset left unowned in a fixture would make every
    # readability assertion below pass for the wrong reason.
    ds.created_by = user.id
    await db.commit()
    return ds, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


class FakeClient:
    """The model, replaced. Records what it was asked."""

    def __init__(self, reply=None):
        self.reply = reply if reply is not None else {
            "proposals": [{
                "title": "Clinic overview",
                "rationale": "for the clinic manager",
                "widgets": [{
                    "widget_type": "bar", "title": "Average wait by department",
                    "why": "where the queue builds",
                    "config": {"dimension": "department", "measure": "wait_minutes",
                               "aggregation": "avg"},
                }],
            }]
        }
        self.seen = []

    async def complete_json(self, messages, schema, **kw):
        self.seen.append(messages)
        return self.reply


@pytest.fixture
def fake_model(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: client)
    return client


@pytest.mark.asyncio
class TestTheAnswer:
    async def test_it_returns_the_proposals(self, client, db_session, two_orgs,
                                            clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "I run the clinic"}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["proposals"][0]["title"] == "Clinic overview"

    async def test_every_widget_was_actually_executed(self, client, db_session,
                                                      two_orgs, clinic_csv, fake_model):
        """A proposal is only returned once its widgets have drawn, so each one
        carries the number of rows it produced."""
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "I run the clinic"}, headers=headers)
        widget = r.json()["proposals"][0]["widgets"][0]
        assert widget["row_count"] == 3          # three departments

    async def test_the_persons_words_reach_the_model(self, client, db_session,
                                                     two_orgs, clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                          json={"goal": "I am a ward sister on nights"}, headers=headers)
        blob = " ".join(m["content"] for m in fake_model.seen[0])
        assert "ward sister on nights" in blob

    async def test_it_returns_what_it_understood(self, client, db_session, two_orgs,
                                                 clinic_csv, fake_model):
        """Shown above the proposals. A user who can see that the tool read their
        data correctly can judge whether to trust what it suggests."""
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": ""}, headers=headers)
        profile = r.json()["profile"]
        assert profile["row_count"] == 30
        names = [c["name"] for c in profile["columns"]]
        assert "department" in names

    async def test_no_goal_is_allowed(self, client, db_session, two_orgs,
                                      clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={}, headers=headers)
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
class TestAnEmptyGoalUsesNoModel:
    """Nothing to tailor to means nothing to ask a model.

    With no description of the person, a model produces a generic answer for 25
    seconds and a network round trip. The statistics engine produces one
    instantly, deterministically, and with the finding's own numbers in every
    caption. So an empty box changes the engine, not just the prompt.
    """

    async def test_no_model_is_contacted(self, client, db_session, two_orgs,
                                         clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": ""}, headers=headers)
        assert r.status_code == 200, r.text
        assert fake_model.seen == [], "the model was asked despite an empty goal"

    async def test_whitespace_counts_as_empty(self, client, db_session, two_orgs,
                                              clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                          json={"goal": "  \n  \t "}, headers=headers)
        assert fake_model.seen == []

    async def test_an_omitted_goal_counts_as_empty(self, client, db_session, two_orgs,
                                                   clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                          json={}, headers=headers)
        assert fake_model.seen == []

    async def test_it_says_which_engine_answered(self, client, db_session, two_orgs,
                                                 clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": ""}, headers=headers)
        assert r.json()["source"] == "insights"

    async def test_a_goal_still_reaches_the_model(self, client, db_session, two_orgs,
                                                  clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "I run the clinic"}, headers=headers)
        assert fake_model.seen, "a stated goal must still be tailored to"
        assert r.json()["source"] == "model"


@pytest.mark.asyncio
class TestSecurity:
    async def test_another_org_cannot_ask(self, client, db_session, two_orgs,
                                          clinic_csv, fake_model):
        ds, _ = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        other = two_orgs["b"]["user"]
        headers = {"Authorization":
                   f"Bearer {create_access_token(other.id, other.org_id)}"}
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "x"}, headers=headers)
        assert r.status_code in (403, 404)

    async def test_it_needs_a_login(self, client, db_session, two_orgs, clinic_csv):
        ds, _ = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "x"})
        assert r.status_code in (401, 403)

    async def test_a_dataset_this_user_cannot_read_is_not_profiled(self, client,
                                                                   db_session, two_orgs,
                                                                   clinic_csv, fake_model):
        """Belonging to the same org is not permission to read.

        `check_org` only proves the dataset is in the caller's tenant. Without
        the readability gate every member could profile any dataset id in the
        org -- and this endpoint does not merely read it, it sends a profile
        carrying SAMPLE VALUES to a model. `GET /datasets/{id}` and
        `widget-data` both 404 for this case; so must this.
        """
        ds, _ = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        # A second user in the SAME org, with their own role and no grant.
        stranger_role = Role(org_id=two_orgs["a"]["org"].id, name="other",
                             is_org_admin=False)
        db_session.add(stranger_role)
        await db_session.flush()
        stranger = User(org_id=two_orgs["a"]["org"].id, role_id=stranger_role.id,
                        email="stranger@example.com",
                        password_hash=hash_password("pw"))
        db_session.add(stranger)
        await db_session.commit()
        headers = {"Authorization":
                   f"Bearer {create_access_token(stranger.id, two_orgs['a']['org'].id)}"}

        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "x"}, headers=headers)
        assert r.status_code == 404, r.text
        assert not fake_model.seen, "the data reached the model anyway"

    async def test_a_denied_column_is_never_offered(self, client, db_session, two_orgs,
                                                    clinic_csv, fake_model):
        """The profile is sent to a third-party model. A column this role may not
        see must not appear in it, and must not be proposable."""
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv,
                                     deny=["salary"])
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "x"}, headers=headers)
        assert r.status_code == 200, r.text
        assert "salary" not in str(r.json()["profile"])
        assert "salary" not in " ".join(m["content"] for m in fake_model.seen[0])


@pytest.mark.asyncio
class TestWhenItCannotHelp:
    async def test_a_missing_dataset_is_a_404(self, client, db_session, two_orgs,
                                              fake_model):
        org = two_orgs["a"]["org"]
        user = two_orgs["a"]["user"]
        headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}
        r = await client.post("/api/v1/datasets/999999/suggest-dashboards",
                              json={"goal": "x"}, headers=headers)
        assert r.status_code == 404

    async def test_an_unusable_answer_comes_back_as_a_reason(self, client, db_session,
                                                             two_orgs, clinic_csv,
                                                             monkeypatch):
        broken = FakeClient({"proposals": [{
            "title": "t", "rationale": "r",
            "widgets": [{"widget_type": "bar", "title": "Invented",
                         "config": {"dimension": "ward", "measure": "cost",
                                    "aggregation": "sum"}}]}]})
        monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: broken)
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "x"}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["proposals"] == []
        assert body["reason"]


@pytest.mark.asyncio
class TestWhatTheModelIsToldItMeans:
    """The complaint this closes: the designer chose charts from column SHAPES,
    because the sentences describing those columns lived in `source_columns` and
    nothing on the dataset side could reach them.

    Tested at the HTTP endpoint. The resolver being right is not the same as the
    endpoint calling it -- this repository has shipped that gap three times.
    """

    async def _described(self, db, org, path):
        """A clinic dataset imported from a connection whose catalog describes
        its columns, with provenance already recorded."""
        from app.models.models import DataSource, SourceColumn, SourceObject
        from app.services import knowledge

        src = DataSource(name="clinic db", type="postgresql", config={}, org_id=org.id)
        db.add(src)
        await db.flush()
        obj = SourceObject(data_source_id=src.id, org_id=org.id, name="visits",
                           kind="table", description="Every outpatient visit.",
                           description_source="inferred", is_canonical=True)
        db.add(obj)
        await db.flush()
        db.add_all([
            SourceColumn(source_object_id=obj.id, name="visit_id", dtype="integer"),
            SourceColumn(source_object_id=obj.id, name="department", dtype="text",
                         description="Clinical department that owned the visit."),
            SourceColumn(source_object_id=obj.id, name="wait_minutes", dtype="integer",
                         description="Minutes from arrival to first clinician."),
            SourceColumn(source_object_id=obj.id, name="cost", dtype="float"),
            SourceColumn(source_object_id=obj.id, name="salary", dtype="float"),
        ])
        await db.flush()

        ds, headers = await _dataset(db, org, path)
        ds.data_source_id = src.id
        ds.source_table = "visits"
        await db.flush()
        await knowledge.link_columns(db, ds)
        db.add(Entity(org_id=org.id, data_source_id=src.id, name="visit",
                      business_name="Visit", grain="One row per outpatient visit.",
                      primary_object="visits", source="confirmed"))
        await db.commit()
        return ds, headers

    async def test_the_catalogs_sentences_reach_the_model(
            self, client, db_session, two_orgs, clinic_csv, fake_model):
        ds, headers = await self._described(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "I run the clinic"}, headers=headers)
        assert r.status_code == 200, r.text
        blob = " ".join(m["content"] for m in fake_model.seen[0])
        assert "Clinical department that owned the visit." in blob
        assert "Minutes from arrival to first clinician." in blob

    async def test_what_one_row_is_reaches_the_model(
            self, client, db_session, two_orgs, clinic_csv, fake_model):
        ds, headers = await self._described(db_session, two_orgs["a"]["org"], clinic_csv)
        await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                          json={"goal": "I run the clinic"}, headers=headers)
        blob = " ".join(m["content"] for m in fake_model.seen[0])
        assert "One row per outpatient visit" in blob
        assert "source of truth" in blob

    async def test_a_denied_columns_description_never_reaches_the_model(
            self, client, db_session, two_orgs, clinic_csv, fake_model):
        """Column security decides the model never SEES the column. A resolver
        that helpfully described it anyway would hand back exactly what the rule
        exists to withhold."""
        from app.models.models import DataSource, SourceColumn, SourceObject
        from app.services import knowledge

        org = two_orgs["a"]["org"]
        src = DataSource(name="clinic db", type="postgresql", config={}, org_id=org.id)
        db_session.add(src)
        await db_session.flush()
        obj = SourceObject(data_source_id=src.id, org_id=org.id, name="visits",
                           kind="table")
        db_session.add(obj)
        await db_session.flush()
        db_session.add_all([
            SourceColumn(source_object_id=obj.id, name="department", dtype="text"),
            SourceColumn(source_object_id=obj.id, name="salary", dtype="float",
                         description="What the clinician is paid each month."),
        ])
        await db_session.flush()

        ds, headers = await _dataset(db_session, org, clinic_csv, deny=["salary"])
        ds.data_source_id = src.id
        ds.source_table = "visits"
        await db_session.flush()
        await knowledge.link_columns(db_session, ds)
        await db_session.commit()

        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "I run the clinic"}, headers=headers)
        assert r.status_code == 200, r.text
        blob = " ".join(m["content"] for m in fake_model.seen[0])
        assert "What the clinician is paid each month." not in blob
        assert "salary" not in blob


@pytest.mark.asyncio
class TestWhenNothingCanBeDesigned:
    """A reason is a dead end: the person is left rereading their own sentence
    wondering which part of it was wrong. The agent solved this for questions
    (D4.3, "ask, do not guess"); this is the same shape for dashboards."""

    async def test_a_refusal_comes_back_with_a_question(
            self, client, db_session, two_orgs, clinic_csv, monkeypatch):
        class NoProposals:
            async def complete_json(self, messages, schema, **kw):
                return {"proposals": []}

            async def complete(self, messages, **kw):
                return "Do you mean waiting time per department, or per clinician?"

        monkeypatch.setattr("app.services.llm.get_client",
                            lambda *a, **k: NoProposals())
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "show me the waiting"}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["proposals"] == []
        assert "per department" in r.json()["question"]

    async def test_a_successful_design_asks_nothing(
            self, client, db_session, two_orgs, clinic_csv, fake_model):
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "I run the clinic"}, headers=headers)
        assert r.json()["question"] is None

    async def test_no_model_means_no_invented_question(
            self, client, db_session, two_orgs, clinic_csv, monkeypatch):
        """"The model endpoint is not configured" cannot be clarified by asking
        the model. A question invented here would be worse than the plain
        refusal it replaced."""
        monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: None)
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "anything"}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["question"] is None

    async def test_a_model_that_cannot_answer_does_not_turn_a_no_into_a_500(
            self, client, db_session, two_orgs, clinic_csv, monkeypatch):
        class Broken:
            async def complete_json(self, messages, schema, **kw):
                return {"proposals": []}

            async def complete(self, messages, **kw):
                raise RuntimeError("the endpoint is down")

        monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: Broken())
        ds, headers = await _dataset(db_session, two_orgs["a"]["org"], clinic_csv)
        r = await client.post(f"/api/v1/datasets/{ds.id}/suggest-dashboards",
                              json={"goal": "anything"}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["question"] is None
