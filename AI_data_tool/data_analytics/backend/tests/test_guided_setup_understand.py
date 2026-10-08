"""Guided setup 1a: Understand -- what the database holds, in plain words.

Facts always (no model), the model's words when the connection allows it,
the model's text checked against the catalog, and a human's words winning.
"""
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnStats, DataSource, Role, SourceColumn, SourceObject,
                               SourceRelationship, User)
from app.services.guided_setup import understand


class FakeClient:
    enabled = True
    last_error = None

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append(messages)
        return self.reply


@pytest.fixture
async def cars(db_session, two_orgs):
    """A small cars database: listings (the business table), a lookup and a log."""
    org = two_orgs["a"]["org"].id
    src = DataSource(name="Cars DB", type="postgresql", config={}, org_id=org,
                     allow_llm_sampling=True, sync_status="ok")
    db_session.add(src)
    await db_session.flush()
    listings = SourceObject(data_source_id=src.id, org_id=org, name="cars_hatla2ee",
                            schema_name="public", kind="table", row_count_estimate=14269)
    makes = SourceObject(data_source_id=src.id, org_id=org, name="makes",
                         schema_name="public", kind="table", row_count_estimate=118)
    log = SourceObject(data_source_id=src.id, org_id=org, name="import_log",
                       schema_name="public", kind="table", row_count_estimate=90000)
    db_session.add_all([listings, makes, log])
    await db_session.flush()
    price = SourceColumn(source_object_id=listings.id, name="price_egp", position=1, dtype="numeric")
    listed = SourceColumn(source_object_id=listings.id, name="listed_date", position=2, dtype="datetime")
    make = SourceColumn(source_object_id=listings.id, name="make", position=3, dtype="text")
    lid = SourceColumn(source_object_id=listings.id, name="listing_id", position=0, dtype="integer",
                       is_primary_key=True)
    mk_name = SourceColumn(source_object_id=makes.id, name="name", position=1, dtype="text")
    log_at = SourceColumn(source_object_id=log.id, name="at", position=1, dtype="datetime")
    year = SourceColumn(source_object_id=listings.id, name="model_year", position=4, dtype="integer")
    db_session.add_all([price, listed, make, lid, mk_name, log_at, year])
    await db_session.flush()
    db_session.add_all([
        ColumnStats(source_column_id=listed.id, min_value="2025-04-29", max_value="2026-06-18", exact=False),
        ColumnStats(source_column_id=make.id, top_k=[{"value": "Toyota", "count": 900, "ratio": .06}],
                    null_ratio=0.0, exact=False),
        SourceRelationship(data_source_id=src.id, org_id=org,
                           from_object_id=listings.id, from_column="make", to_object_id=makes.id,
                           to_column="name", confidence=0.9, source="inferred"),
    ])
    await db_session.commit()
    return src, listings, makes, log


class TestFacts:
    async def test_business_table_ranks_first_and_plumbing_last(self, db_session, cars):
        src, *_ = cars
        facts = await understand.load_facts(db_session, src)
        names = [t["name"] for t in facts]
        assert names[0] == "cars_hatla2ee"
        assert names[-1] == "import_log"
        by = {t["name"]: t for t in facts}
        assert by["cars_hatla2ee"]["measures"] == ["price_egp"]   # neither the id nor the year
        assert by["cars_hatla2ee"]["dates_exact"] is False          # from the sync's sample
        assert by["cars_hatla2ee"]["date_from"] == "2025-04-29"
        assert by["cars_hatla2ee"]["group"] == "main"
        assert by["makes"]["group"] == "supporting"
        assert by["import_log"]["group"] == "technical"
        assert by["makes"]["related"] == ["cars_hatla2ee"]

    async def test_totals_leave_plumbing_out_of_the_period(self, db_session, cars):
        src, *_ = cars
        t = understand.totals(await understand.load_facts(db_session, src))
        assert t["tables"] == 3 and t["rows"] == 14269 + 118 + 90000
        assert (t["date_from"], t["date_to"]) == ("2025-04-29", "2026-06-18")


class TestWords:
    async def test_prompt_asks_for_the_readers_language_and_carries_values(self, db_session, cars):
        src, *_ = cars
        facts = await understand.load_facts(db_session, src)
        msgs = understand.build_prompt(src, facts, "ar", {"cars_hatla2ee": [{"make": "Toyota"}]})
        assert "Arabic" in msgs[0]["content"]
        assert "e.g. Toyota" in msgs[1]["content"]
        assert "Sample row" in msgs[1]["content"]

    async def test_invented_tables_are_dropped_and_plumbing_stays_technical(self, db_session, cars):
        src, *_ = cars
        facts = await understand.load_facts(db_session, src)
        merged = understand.merge_words(facts, {
            "overview": "Used-car listings in Egypt.",
            "tables": [{"name": "ghost_table", "title": "Ghost", "what": "x"},
                       {"name": "import_log", "title": "Log", "what": "x", "group": "main"},
                       {"name": "makes", "title": "Car makes", "what": "One row per brand."}],
            "order": ["makes", "ghost_table", "cars_hatla2ee"],
            "questions": ["Which brands hold their value?", " "],
        })
        names = [t["name"] for t in merged["tables"]]
        assert "ghost_table" not in names
        assert names[:2] == ["makes", "cars_hatla2ee"]        # the model's order, then the facts'
        log = next(t for t in merged["tables"] if t["name"] == "import_log")
        assert log["group"] == "technical"
        assert merged["questions"] == ["Which brands hold their value?"]

    async def test_a_human_description_beats_the_model(self, db_session, cars):
        src, listings, *_ = cars
        listings.description, listings.description_source = "Our listings feed", "confirmed"
        await db_session.commit()
        facts = await understand.load_facts(db_session, src)
        merged = understand.merge_words(facts, {"overview": "o", "order": [], "tables": [
            {"name": "cars_hatla2ee", "title": "Listings", "what": "model text"}]})
        t = next(t for t in merged["tables"] if t["name"] == "cars_hatla2ee")
        assert t["what"] == "Our listings feed" and t["what_source"] == "you"

    async def test_no_model_call_when_the_connection_does_not_allow_it(self, db_session, cars):
        src, *_ = cars
        src.allow_llm_sampling = False
        client = FakeClient({"overview": "x", "tables": [], "order": []})
        words, reason = await understand.describe(src, [], "en", {}, client)
        assert (words, reason) == (None, "off") and client.calls == []


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


class TestRoutes:
    @pytest.fixture
    def model(self, monkeypatch):
        client = FakeClient({"overview": "Used-car listings across Egypt, 2025-2026.",
                             "tables": [{"name": "cars_hatla2ee", "title": "Car listings",
                                         "what": "One row per car for sale.",
                                         "useful_for": "Prices by brand, age and city."}],
                             "order": ["cars_hatla2ee"], "questions": ["Which brands hold value?"]})
        monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: client)
        monkeypatch.setattr("app.services.connections.preview_table",
                            lambda cfg, t, q, limit: {"columns": ["make"], "rows": [["Toyota"]], "total": 1})
        return client

    @pytest.fixture(autouse=True)
    def inline_writing(self, monkeypatch, db_session):
        """Write the words inside the request, on the test's session, so a
        test can read them on its next call (production runs them detached)."""
        from app.routers import guided_setup

        async def inline(db, user, journey_id, lang, attempt):
            await guided_setup.write_words(db_session, journey_id, lang, attempt)
        monkeypatch.setattr(guided_setup, "_start_writing", inline)

        async def run_now(db, user, tag, job, on_error=None):
            await job(db_session)
        monkeypatch.setattr(guided_setup, "_background", run_now)

    async def test_summary_reads_plainly_and_is_kept_for_the_next_visit(
            self, client, auth_headers, cars, model):
        src, *_ = cars
        await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
        first = await client.get(f"/api/v1/setup/{src.id}/summary?lang=en", headers=auth_headers["a"])
        assert first.status_code == 200
        # The facts answer at once; the words are still being written.
        assert first.json()["ai"]["pending"] is True
        assert first.json()["tables"][0]["name"] == "cars_hatla2ee"
        resp = await client.get(f"/api/v1/setup/{src.id}/summary?lang=en", headers=auth_headers["a"])
        body = resp.json()
        assert body["status"] == "ready" and body["ai"]["used"] is True
        assert body["overview"].startswith("Used-car listings")
        assert body["tables"][0]["title"] == "Car listings"
        assert body["can_edit"] is True
        # The second visit is served from the journey: no second model call.
        await client.get(f"/api/v1/setup/{src.id}/summary?lang=en", headers=auth_headers["a"])
        assert len(model.calls) == 1
        # Another language is another summary.
        await client.get(f"/api/v1/setup/{src.id}/summary?lang=ar", headers=auth_headers["a"])
        assert len(model.calls) == 2

    async def test_a_correction_wins_without_asking_the_ai_again(
            self, client, auth_headers, cars, model):
        src, listings, *_ = cars
        await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
        await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])
        r = await client.patch(f"/api/v1/setup/{src.id}/tables/{listings.id}", headers=auth_headers["a"],
                               json={"text": "Every car listed on Hatla2ee"})
        assert r.status_code == 200
        r = await client.patch(f"/api/v1/setup/{src.id}/overview", headers=auth_headers["a"],
                               json={"text": "Car market data for our pricing team"})
        assert r.status_code == 200
        body = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        assert len(model.calls) == 1
        assert body["overview"] == "Car market data for our pricing team"
        assert body["overview_source"] == "you"
        t = next(t for t in body["tables"] if t["id"] == listings.id)
        assert t["what"] == "Every car listed on Hatla2ee"
        # The AI's other words are still there.
        assert t["title"] == "Car listings"

    async def test_asked_once_per_language_across_visits_and_resyncs(
            self, client, db_session, auth_headers, cars, model):
        from datetime import datetime
        src, *_ = cars
        for lang in ("en", "ar", "en", "ar", "en"):
            await client.get(f"/api/v1/setup/{src.id}/summary?lang={lang}", headers=auth_headers["a"])
        assert len(model.calls) == 2
        src.last_synced_at = datetime(2026, 10, 8)
        await db_session.commit()
        await client.get(f"/api/v1/setup/{src.id}/summary?lang=en", headers=auth_headers["a"])
        assert len(model.calls) == 2

    async def test_ask_again_keeps_the_earlier_words_if_the_ai_fails(
            self, client, auth_headers, cars, model):
        src, *_ = cars
        await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])
        model.reply = None
        await client.post(f"/api/v1/setup/{src.id}/summary/refresh", headers=auth_headers["a"])
        body = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        assert len(model.calls) == 2
        assert body["overview"].startswith("Used-car listings")
        assert body["ai"] == {"used": True, "pending": False, "reason": "failed"}

    async def test_words_kept_in_the_old_shape_are_still_read(
            self, client, db_session, auth_headers, cars, model):
        from app.models.models import SetupJourney
        from sqlalchemy import select
        src, *_ = cars
        await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
        j = (await db_session.execute(select(SetupJourney))).scalar_one()
        j.summary = {"key": "en|2026-10-07", "words": {"overview": "Kept.", "tables": [], "order": []}}
        await db_session.commit()
        body = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        assert body["overview"] == "Kept." and model.calls == []

    async def test_member_who_does_not_own_it_cannot_edit(self, client, db_session, two_orgs, cars, model):
        src, listings, *_ = cars
        role = Role(org_id=src.org_id, name="Member", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        member = User(org_id=src.org_id, role_id=role.id, email="m@example.com", password_hash=hash_password("pw"))
        db_session.add(member)
        await db_session.commit()
        # Unowned connection: visible to members, editable by admins only.
        assert (await client.get(f"/api/v1/setup/{src.id}/summary", headers=_h(member))).json()["can_edit"] is False
        r = await client.patch(f"/api/v1/setup/{src.id}/overview", headers=_h(member), json={"text": "x"})
        assert r.status_code == 403

    async def test_without_the_model_the_facts_still_answer(self, client, auth_headers, cars, model):
        src, *_ = cars
        src.allow_llm_sampling = False
        body = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        assert body["status"] == "ready"
        assert body["ai"] == {"used": False, "pending": False, "reason": "off"}
        assert body["tables"][0]["name"] == "cars_hatla2ee"
        assert model.calls == []

    async def test_a_source_not_yet_synced_says_so(self, client, db_session, two_orgs, auth_headers):
        src = DataSource(name="new", type="postgresql", config={}, org_id=two_orgs["a"]["org"].id,
                         sync_status="running")
        db_session.add(src)
        await db_session.commit()
        body = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        assert body["status"] == "syncing"

    async def test_sample_of_a_table_from_another_connection_is_404(
            self, client, db_session, auth_headers, cars, model):
        src, listings, *_ = cars
        other = DataSource(name="other", type="postgresql", config={}, org_id=src.org_id)
        db_session.add(other)
        await db_session.commit()
        r = await client.get(f"/api/v1/setup/{other.id}/tables/{listings.id}/sample", headers=auth_headers["a"])
        assert r.status_code == 404
        ok = await client.get(f"/api/v1/setup/{src.id}/tables/{listings.id}/sample", headers=auth_headers["a"])
        assert ok.status_code == 200 and ok.json()["rows"] == [{"make": "Toyota"}]


    async def test_a_model_that_is_down_is_reported_and_not_asked_on_every_visit(
            self, client, auth_headers, cars, model):
        src, *_ = cars
        model.reply = None
        for _ in range(3):
            body = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        assert body["ai"]["reason"] == "failed" and body["ai"]["pending"] is False
        assert len(model.calls) == 1
        model.reply = {"overview": "Back.", "tables": [], "order": []}
        await client.post(f"/api/v1/setup/{src.id}/summary/refresh", headers=auth_headers["a"])
        body = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        assert body["overview"] == "Back." and len(model.calls) == 2


class TestExactRanges:
    async def test_measured_dates_replace_the_sampled_ones(self, client, db_session, auth_headers, cars, monkeypatch):
        from app.routers import guided_setup

        async def run_now(db, user, tag, job, on_error=None):
            await job(db_session)
        monkeypatch.setattr(guided_setup, "_background", run_now)
        seen = []

        def fake_preview(cfg, table, query, limit):
            seen.append(query)
            return {"columns": ["lo", "hi"], "rows": [["2000-01-02", "2023-12-12"]], "total": 1}
        monkeypatch.setattr("app.services.connections.preview_table", fake_preview)
        src, *_ = cars
        src.allow_llm_sampling = False
        await db_session.commit()
        first = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        body = (await client.get(f"/api/v1/setup/{src.id}/summary", headers=auth_headers["a"])).json()
        t = next(t for t in body["tables"] if t["name"] == "cars_hatla2ee")
        assert (t["date_from"], t["date_to"], t["dates_exact"]) == ("2000-01-02", "2023-12-12", True)
        assert body["ranges_pending"] is False
        assert any("MIN(" in q.upper() for q in seen)

    def test_the_model_is_told_not_to_guess_periods(self):
        from app.models.models import DataSource
        msgs = understand.build_prompt(DataSource(name="x"), [], "en", {})
        assert "never guess a period" in msgs[0]["content"]
