"""Guided setup v2: the Demand -- what the person wants, checked on the rows."""
import pandas as pd

from app.services.guided_setup import demand


class FakeClient:
    enabled = True

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append(messages)
        return self.replies.pop(0) if self.replies else None


def parcels(n=200):
    kinds = ["Standard", "Express", "Same Day", "International"]
    return pd.DataFrame({
        "service_type": [kinds[i % 4] for i in range(n)],
        "city": ["Cairo" if i % 2 else "Giza " for i in range(n)],
        "fee": [50.0 + i for i in range(n)],
        "created_at": pd.date_range("2024-01-01", periods=n, freq="D"),
    })


class TestResolveScope:
    def test_a_named_value_is_found_whatever_its_case(self):
        got = demand.resolve_scope(parcels(), {"said": "express", "column": "service_type", "op": "in",
                                               "values": ["EXPRESS"]})
        assert got["status"] == "in_dashboard" and got["values"] == ["Express"]
        assert (got["matched_rows"], got["of_rows"]) == (50, 200)

    def test_a_dataset_that_holds_only_the_subject_needs_no_filter(self):
        df = parcels()
        only = df[df["service_type"] == "Express"]
        got = demand.resolve_scope(only, {"said": "Express", "column": "service_type", "op": "in",
                                          "values": ["Express"]})
        assert got["status"] == "in_data"

    def test_the_wrong_column_is_corrected_from_the_values(self):
        got = demand.resolve_scope(parcels(), {"said": "Same Day", "column": "city", "op": "in", "values": []})
        assert got["column"] == "service_type" and got["values"] == ["Same Day"]

    def test_a_subject_the_data_does_not_hold_is_unmatched_and_offers_what_it_holds(self):
        got = demand.resolve_scope(parcels(), {"said": "drone deliveries", "column": "", "op": "in", "values": []})
        assert got["status"] == "unmatched" and got["matched_rows"] == 0
        assert {c["column"] for c in got["candidates"]} == {"service_type", "city"}

    def test_a_place_does_not_pick_a_longer_name_in_another_column(self):
        df = parcels()
        df["branch"] = ["Giza East Hub" if i % 2 else "Cairo Hub" for i in range(len(df))]
        got = demand.resolve_scope(df.drop(columns=["city"]), {"said": "to Giza", "column": "", "op": "in",
                                                               "values": []})
        assert got["status"] == "unmatched"

    def test_a_number_and_a_date_range(self):
        over = demand.resolve_scope(parcels(), {"said": "over 200", "column": "fee", "op": "gt", "values": ["200"]})
        assert over["status"] == "in_dashboard" and over["matched_rows"] == 49 and over["values"] == [200.0]
        since = demand.resolve_scope(parcels(), {"said": "since March", "column": "created_at", "op": "gte",
                                                 "values": ["2024-03-01"]})
        assert since["status"] == "in_dashboard" and since["values"] == ["2024-03-01"]
        assert since["matched_rows"] == 140


class TestFilters:
    def test_only_what_the_dashboard_must_narrow_becomes_a_filter(self):
        dem = {"scope": [
            {"dataset_id": 7, "column": "service_type", "op": "in", "values": ["Express"], "status": "in_dashboard"},
            {"dataset_id": 7, "column": "city", "op": "in", "values": ["Cairo"], "status": "in_data"},
            {"dataset_id": 7, "column": "fee", "op": "gt", "values": [200.0], "status": "in_dashboard"},
            {"dataset_id": 7, "column": None, "op": "in", "values": [], "status": "unmatched", "said": "x"},
            {"dataset_id": 8, "column": "city", "op": "in", "values": ["Giza"], "status": "in_dashboard"}]}
        assert demand.filters_for(dem, 7) == [
            {"column": "service_type", "op": "in", "value": ["Express"]},
            {"column": "fee", "op": "gt", "value": 200.0}]
        assert demand.scope_words(dem, 7) == ["service type: Express", "city: Cairo", "fee > 200"]

    def test_a_dataset_made_for_the_subject_is_already_narrowed(self):
        sql = "SELECT tracking_no FROM shipments WHERE service_type = 'Express' AND is_late"
        assert demand.made_for(sql, {"said": "Express shipments", "values": []}) == ["Express"]
        assert demand.made_for(sql, {"said": "returns", "values": []}) == []


class TestWrite:
    async def test_the_models_scope_is_checked_on_the_rows(self):
        client = FakeClient({"sentence": "Express parcels: fees by city", "who": "ops manager",
                             "subject": "Express parcels", "exclude": [],
                             "questions": [{"text": "What does Express cost?", "asked": True},
                                           {"text": "Where is it dearest?", "asked": False}],
                             "scope": [{"dataset": "Parcels", "said": "Express", "column": "service_type",
                                        "op": "in", "values": ["express"]}]})
        got = await demand.write({"focus": "Express only"},
                                 [{"id": 3, "name": "Parcels", "frame": parcels(), "proposal": None}], [], "en", client)
        assert got["source"] == "ai" and got["questions"] == [
            {"id": "q1", "text": "What does Express cost?", "asked": True},
            {"id": "q2", "text": "Where is it dearest?", "asked": False}]
        assert got["scope"][0]["status"] == "in_dashboard" and got["scope"][0]["dataset_id"] == 3
        assert got["scope"][0]["values"] == ["Express"]

    async def test_a_dataset_filtered_in_its_query_is_not_reported_missing(self):
        df = parcels().drop(columns=["service_type"])
        client = FakeClient({"sentence": "Express parcels", "who": "", "subject": "Express", "questions": [],
                             "exclude": [], "scope": [{"dataset": "Parcels", "said": "Express parcels",
                                                       "column": "", "op": "in", "values": []}]})
        proposal = {"sql": "SELECT city, fee FROM parcels WHERE service_type = 'Express'"}
        got = await demand.write(None, [{"id": 3, "name": "Parcels", "frame": df, "proposal": proposal}],
                                 [], "en", client)
        assert got["scope"][0]["status"] == "in_data" and got["scope"][0]["values"] == ["Express"]

    async def test_without_a_model_the_persons_own_words_are_kept_and_searched(self):
        got = await demand.write({"focus": "I need International parcels", "questions": "what do they cost? where to?"},
                                 [{"id": 3, "name": "Parcels", "frame": parcels(), "proposal": None}], [], "en", None)
        assert got["source"] == "plain" and got["sentence"] == "I need International parcels"
        assert [q["text"] for q in got["questions"]] == ["what do they cost", "where to"]
        assert got["scope"][0]["column"] == "service_type" and got["scope"][0]["values"] == ["International"]

    async def test_a_correction_reaches_the_model_and_wins(self):
        client = FakeClient({"sentence": "Giza parcels", "who": "", "subject": "", "questions": [],
                             "exclude": [], "scope": []})
        await demand.write({"focus": "Cairo"}, [{"id": 3, "name": "Parcels", "frame": parcels(), "proposal": None}],
                           ["I meant Giza"], "en", client)
        assert "I meant Giza" in client.calls[0][1]["content"]
        assert "corrections win" in client.calls[0][1]["content"]


class TestOutcomesAreNotScopes:
    async def test_what_happened_to_a_row_is_never_narrowed_to(self):
        df = parcels()
        df["has_complaint"] = [i % 10 == 0 for i in range(len(df))]
        client = FakeClient({"sentence": "Complaints by city", "who": "", "subject": "complaints", "exclude": [],
                             "questions": [], "not_in_data": [],
                             "scope": [{"dataset": "Parcels", "said": "with a complaint", "column": "has_complaint",
                                        "op": "in", "values": ["True"]},
                                       {"dataset": "Parcels", "said": "Express", "column": "service_type",
                                        "op": "in", "values": ["Express"]}]})
        got = await demand.write(None, [{"id": 3, "name": "Parcels", "frame": df, "proposal": None}], [], "en", client)
        assert [s["column"] for s in got["scope"]] == ["service_type"]
