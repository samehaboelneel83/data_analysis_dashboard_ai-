"""Stage 5 — semantic types, roles, deprecation, and the LLM description pass.

The rule these tests exist to protect: this stage PROPOSES. A human's existing
choice always wins, and the LLM pass is optional in both directions — off by
default, and a no-op when the endpoint is down.
"""
import pytest

from app.services.metadata import infer_semantic


class TestSemanticType:
    def test_values_outrank_the_column_name(self):
        """A column called `amount` holding email addresses is an email column
        that someone named badly. Calling it currency would tell the agent
        something false and mask nothing."""
        got = infer_semantic.classify_semantic_type(
            "amount", ["a@x.com", "b@x.com", "c@x.com"]
        )
        assert got == "email"

    def test_currency_is_recognised_from_the_name(self):
        """No regex over values can see that 42.50 is money."""
        assert infer_semantic.classify_semantic_type("unit_price", [1.0, 2.0, 3.0]) == "currency"

    def test_percentage_from_the_name(self):
        assert infer_semantic.classify_semantic_type("discount_pct", [1, 2, 3]) == "percentage"

    def test_ordinary_column_has_no_semantic_type(self):
        assert infer_semantic.classify_semantic_type("city", ["Cairo", "Giza", "Luxor"]) is None


class TestRole:
    def test_datetime_is_a_timestamp(self):
        assert infer_semantic.classify_role("created_at", "timestamp", {}) == "timestamp"

    def test_near_unique_column_is_an_identifier(self):
        """This is also how an undeclared primary key announces itself."""
        got = infer_semantic.classify_role(
            "order_ref", "text", {"distinct_count": 1000, "row_count": 1000}
        )
        assert got == "identifier"

    def test_id_named_column_is_an_identifier_without_statistics(self):
        assert infer_semantic.classify_role("customer_id", "integer", {}) == "identifier"

    def test_high_cardinality_numeric_is_a_measure(self):
        got = infer_semantic.classify_role(
            "total", "numeric", {"distinct_count": 5000, "row_count": 10000}
        )
        assert got == "measure"

    def test_low_cardinality_numeric_is_a_dimension(self):
        """A numeric column with six distinct values is a category wearing an
        integer, and grouping by it is usually what a user means."""
        got = infer_semantic.classify_role(
            "star_rating", "integer", {"distinct_count": 5, "row_count": 10000}
        )
        assert got == "dimension"

    def test_text_defaults_to_dimension(self):
        got = infer_semantic.classify_role(
            "city", "text", {"distinct_count": 20, "row_count": 10000}
        )
        assert got == "dimension"


class TestDeprecation:
    @pytest.mark.parametrize("name", [
        "orders_old", "orders_bak", "tmp_orders", "temp_orders",
        "orders_deprecated", "zz_orders", "orders_backup",
    ])
    def test_names_that_signal_abandonment(self, name):
        flagged, reason = infer_semantic.detect_deprecation(name, row_count=100)
        assert flagged is True
        assert reason

    def test_an_empty_table_is_flagged(self):
        flagged, reason = infer_semantic.detect_deprecation("orders", row_count=0)
        assert flagged is True
        assert "empty" in reason

    def test_a_normal_populated_table_is_not(self):
        flagged, reason = infer_semantic.detect_deprecation("orders", row_count=1000)
        assert flagged is False and reason is None

    def test_the_reason_is_returned_for_review(self):
        """'This looks deprecated' invites an argument. 'Named _old' ends one."""
        _, reason = infer_semantic.detect_deprecation("orders_old", row_count=5)
        assert "_old" in reason


class TestAuthorOverridesWin:
    COLUMNS = [
        {"name": "status", "dtype": "text", "sample_values": ["a", "b"],
         "stats": {"distinct_count": 2, "row_count": 100}},
    ]

    def test_inference_fills_an_empty_field(self):
        got = infer_semantic.apply_column_inference(self.COLUMNS, {})
        assert got["status"]["role"] == "dimension"

    def test_an_author_set_role_is_never_overwritten(self):
        """Without this, a nightly sync quietly reverts every correction made
        during the day, and the corrections look like they never saved."""
        got = infer_semantic.apply_column_inference(
            self.COLUMNS, {"status": {"role": "measure"}}
        )
        assert "role" not in got.get("status", {})

    def test_an_author_set_semantic_type_is_never_overwritten(self):
        columns = [{"name": "contact", "dtype": "text",
                    "sample_values": ["a@x.com", "b@x.com", "c@x.com"], "stats": {}}]
        got = infer_semantic.apply_column_inference(
            columns, {"contact": {"semantic_type": "national_id"}}
        )
        assert "semantic_type" not in got.get("contact", {})

    def test_unrelated_columns_are_unaffected_by_an_override(self):
        columns = self.COLUMNS + [
            {"name": "total", "dtype": "numeric",
             "stats": {"distinct_count": 900, "row_count": 1000}}
        ]
        got = infer_semantic.apply_column_inference(columns, {"status": {"role": "measure"}})
        assert got["total"]["role"] == "measure"


class TestDescriptionPrompt:
    def test_includes_top_k_values(self):
        """The whole reason the descriptions are worth having: a model told that
        st_cd holds 1, 2 and 3 can say something useful about it."""
        messages = infer_semantic.build_description_prompt("orders", [
            {"name": "st_cd", "dtype": "integer",
             "top_k": [{"value": "1"}, {"value": "2"}, {"value": "3"}]},
        ])
        assert "st_cd" in messages[1]["content"]
        assert "1, 2, 3" in messages[1]["content"]

    def test_asks_for_json_only(self):
        messages = infer_semantic.build_description_prompt("orders", [{"name": "x"}])
        assert "JSON" in messages[0]["content"]


class FakeClient:
    def __init__(self, result=None, error=None):
        self._result = result
        self.last_error = error
        self.calls = 0

    async def complete_json(self, messages, schema, **kw):
        self.calls += 1
        return self._result


class TestDescribeWithLlm:
    COLUMNS = [{"name": "total", "dtype": "numeric"}, {"name": "st_cd", "dtype": "integer"}]

    async def test_returns_descriptions_for_requested_columns(self):
        client = FakeClient({"descriptions": {"total": "The order total.",
                                              "st_cd": "A status code."}})
        got = await infer_semantic.describe_with_llm(
            "orders", self.COLUMNS, client, allow=True
        )
        assert got["total"] == "The order total."

    async def test_consent_off_makes_no_call_at_all(self):
        """Per-source consent, default off. Not an error — a choice."""
        client = FakeClient({"descriptions": {"total": "x"}})
        got = await infer_semantic.describe_with_llm(
            "orders", self.COLUMNS, client, allow=False
        )
        assert got == {}
        assert client.calls == 0

    async def test_unreachable_endpoint_degrades_to_empty(self):
        """A sync that failed because a sentence could not be written would be a
        worse product than one without descriptions."""
        client = FakeClient(None, error="ConnectError")
        got = await infer_semantic.describe_with_llm(
            "orders", self.COLUMNS, client, allow=True
        )
        assert got == {}

    async def test_no_client_degrades_to_empty(self):
        assert await infer_semantic.describe_with_llm(
            "orders", self.COLUMNS, None, allow=True
        ) == {}

    async def test_invented_column_names_are_discarded(self):
        """Models occasionally return a plausible extra column. Inventing
        catalog entries is precisely what this layer must not do."""
        client = FakeClient({"descriptions": {
            "total": "The order total.",
            "shipping_address": "Where it goes.",   # never asked about
        }})
        got = await infer_semantic.describe_with_llm(
            "orders", self.COLUMNS, client, allow=True
        )
        assert set(got) == {"total"}

    async def test_blank_descriptions_are_dropped(self):
        client = FakeClient({"descriptions": {"total": "   ", "st_cd": "A code."}})
        got = await infer_semantic.describe_with_llm(
            "orders", self.COLUMNS, client, allow=True
        )
        assert set(got) == {"st_cd"}


class TestDraftEnumLabels:
    """T2: what a coded column's VALUE means, not just what values exist.
    top_k already knows st_cd holds 1, 2, 3 -- this fills in 3 = cancelled."""

    COLUMNS = [{"name": "st_cd", "dtype": "integer", "description": None,
               "top_k": [{"value": "1", "count": 5}, {"value": "2", "count": 3},
                         {"value": "3", "count": 1}]}]

    async def test_returns_labels_for_requested_values(self):
        client = FakeClient({"labels": {"st_cd": {"1": "new", "2": "paid", "3": "cancelled"}}})
        got = await infer_semantic.draft_enum_labels("orders", self.COLUMNS, client, allow=True)
        assert got == {"st_cd": {"1": "new", "2": "paid", "3": "cancelled"}}

    async def test_consent_off_makes_no_call_at_all(self):
        client = FakeClient({"labels": {"st_cd": {"1": "new"}}})
        got = await infer_semantic.draft_enum_labels("orders", self.COLUMNS, client, allow=False)
        assert got == {}
        assert client.calls == 0

    async def test_unreachable_endpoint_degrades_to_empty(self):
        client = FakeClient(None, error="ConnectError")
        got = await infer_semantic.draft_enum_labels("orders", self.COLUMNS, client, allow=True)
        assert got == {}

    async def test_no_columns_makes_no_call(self):
        client = FakeClient({"labels": {}})
        got = await infer_semantic.draft_enum_labels("orders", [], client, allow=True)
        assert got == {}
        assert client.calls == 0

    async def test_invented_column_is_discarded(self):
        client = FakeClient({"labels": {
            "st_cd": {"1": "new"}, "ghost_col": {"1": "x"}}})
        got = await infer_semantic.draft_enum_labels("orders", self.COLUMNS, client, allow=True)
        assert set(got) == {"st_cd"}

    async def test_invented_value_is_discarded(self):
        """A model returning a label for a value never listed would be
        inventing a catalog entry -- exactly what this layer must not do."""
        client = FakeClient({"labels": {"st_cd": {"1": "new", "99": "made up"}}})
        got = await infer_semantic.draft_enum_labels("orders", self.COLUMNS, client, allow=True)
        assert got == {"st_cd": {"1": "new"}}

    async def test_blank_label_is_dropped(self):
        client = FakeClient({"labels": {"st_cd": {"1": "new", "2": "   "}}})
        got = await infer_semantic.draft_enum_labels("orders", self.COLUMNS, client, allow=True)
        assert got == {"st_cd": {"1": "new"}}



class TestDraftEntities:
    """Task R3 / spec section 5 (E2): named business objects and their
    grain, drafted with the same enrichment-never-requirement contract as
    describe_with_llm/draft_enum_labels."""

    TABLES = [
        {"name": "customers", "kind": "table", "row_count": 40,
         "columns": ["id", "email", "city"]},
        {"name": "orders", "kind": "table", "row_count": 120,
         "columns": ["id", "customer_id", "status", "total"]},
    ]

    async def test_returns_proposed_entities(self):
        client = FakeClient({"entities": [
            {"name": "customer", "business_name": "Customer",
             "grain": "One row per customer.",
             "description": "A person who placed orders.",
             "primary_object": "customers"},
        ]})
        got = await infer_semantic.draft_entities("shop", self.TABLES, client, allow=True)
        assert got == [{
            "name": "customer", "business_name": "Customer",
            "grain": "One row per customer.",
            "description": "A person who placed orders.",
            "primary_object": "customers",
        }]

    async def test_consent_off_makes_no_call_at_all(self):
        client = FakeClient({"entities": [{"name": "customer"}]})
        got = await infer_semantic.draft_entities("shop", self.TABLES, client, allow=False)
        assert got == []
        assert client.calls == 0

    async def test_unreachable_endpoint_degrades_to_empty(self):
        client = FakeClient(None, error="ConnectError")
        got = await infer_semantic.draft_entities("shop", self.TABLES, client, allow=True)
        assert got == []

    async def test_no_client_degrades_to_empty(self):
        got = await infer_semantic.draft_entities("shop", self.TABLES, None, allow=True)
        assert got == []

    async def test_no_tables_makes_no_call(self):
        client = FakeClient({"entities": []})
        got = await infer_semantic.draft_entities("shop", [], client, allow=True)
        assert got == []
        assert client.calls == 0

    async def test_a_nameless_entity_is_dropped(self):
        client = FakeClient({"entities": [{"name": "  "}, {"name": "order"}]})
        got = await infer_semantic.draft_entities("shop", self.TABLES, client, allow=True)
        assert [e["name"] for e in got] == ["order"]

    async def test_a_primary_object_not_in_the_tables_given_is_dropped(self):
        """A model naming a table that was never listed would be inventing a
        catalog cross-reference -- the same discipline describe_with_llm
        applies to invented columns."""
        client = FakeClient({"entities": [
            {"name": "shipment", "primary_object": "shipments"},
        ]})
        got = await infer_semantic.draft_entities("shop", self.TABLES, client, allow=True)
        assert got == [{
            "name": "shipment", "business_name": None, "grain": None,
            "description": None, "primary_object": None,
        }]

    async def test_entities_beyond_the_cap_are_dropped(self):
        many = [{"name": f"e{i}"} for i in range(infer_semantic.MAX_ENTITIES + 5)]
        client = FakeClient({"entities": many})
        got = await infer_semantic.draft_entities("shop", self.TABLES, client, allow=True)
        assert len(got) == infer_semantic.MAX_ENTITIES

    async def test_overlong_name_and_business_name_are_clamped(self):
        """`Entity.name`/`Entity.business_name` are String(255) (models.py).
        SQLite (this test suite's db) enforces no such limit, so an
        over-length LLM reply would insert fine here and only be rejected
        by Postgres in production -- draft_entities must clamp before that
        gap matters."""
        long_name = "n" * 400
        long_business_name = "b" * 400
        client = FakeClient({"entities": [
            {"name": long_name, "business_name": long_business_name},
        ]})
        got = await infer_semantic.draft_entities("shop", self.TABLES, client, allow=True)
        assert len(got) == 1
        assert len(got[0]["name"]) == infer_semantic.ENTITY_NAME_MAX_LEN
        assert len(got[0]["business_name"]) == infer_semantic.ENTITY_NAME_MAX_LEN
        assert got[0]["name"] == long_name[:infer_semantic.ENTITY_NAME_MAX_LEN]

    async def test_prompt_carries_table_names_and_columns(self):
        messages = infer_semantic.build_entity_prompt("shop", self.TABLES)
        body = messages[1]["content"]
        assert "customers" in body and "email" in body
        assert "orders" in body and "customer_id" in body

    def test_a_wide_column_list_is_capped_per_table(self):
        """Mirrors build_source_prompt's key_columns[:6] cap -- a table's
        column list must not grow the prompt without bound."""
        wide = [{"name": "wide_table", "kind": "table", "row_count": 10,
                "columns": [f"col_{i}" for i in range(40)]}]
        body = infer_semantic.build_entity_prompt("shop", wide)[1]["content"]
        shown = sum(1 for i in range(40) if f"col_{i}" in body)
        assert shown == infer_semantic.MAX_ENTITY_PROMPT_COLUMNS
        assert "+34 more" in body

    def test_a_wide_catalog_stays_within_the_context_window(self):
        """The measured failure this whole cap exists to prevent: an
        82-table/1,354-column source built a prompt that silently 400'd
        (TestOneHugeValueCannotCostATableItsDescription). 80 tables of 20
        columns each is that shape -- capped per-table, the WHOLE prompt
        must still stay well inside a 32,768-token window, the same
        conservative chars-per-token ceiling
        test_a_wide_geometry_table_stays_within_the_context_window applies
        to build_description_prompt."""
        wide_catalog = [
            {"name": f"table_{t}", "kind": "table", "row_count": 1000,
             "columns": [f"col_{t}_{i}" for i in range(20)]}
            for t in range(80)
        ]
        body = infer_semantic.build_entity_prompt("shop", wide_catalog)[1]["content"]
        assert len(body) < 30_000, (
            f"{len(body)} characters of prompt for an 80-table catalog"
        )


class TestOneHugeValueCannotCostATableItsDescription:
    """A single column's example values must not be able to blow the context
    window and take the whole table's description with them.

    This is a real failure, found on the live source, not a hypothetical. A
    PostGIS geometry stringifies to a multi-kilobyte WKB hex blob; five of those
    across a few geometry columns built a 31,869-token prompt against a
    32,768-token window. The endpoint returned 400, `complete_json` turned it
    into None exactly as designed, and the table went undescribed.

    The quiet part is what makes it worth a test: SEVEN of 82 objects were
    silently skipped and the sync still reported `ok`. The degradation was
    graceful, invisible, and hit precisely the widest, least self-explanatory
    views -- the ones most in need of a description.
    """

    def _prompt_text(self, columns):
        from app.services.metadata.infer_semantic import build_description_prompt
        return "".join(m["content"]
                       for m in build_description_prompt("geo_table", columns))

    def test_a_giant_value_is_truncated(self):
        blob = "0106000020E6100000" + "A" * 40_000
        text = self._prompt_text([
            {"name": "cluster_bbox", "dtype": "geometry",
             "sample_values": [blob, blob, blob, blob, blob]},
        ])
        assert len(text) < 4_000, (
            f"the prompt is {len(text)} characters; one geometry column is "
            "still able to exhaust the context window"
        )

    def test_the_truncation_is_visible(self):
        """A model shown a fragment must be able to tell it is a fragment, or it
        will describe the fragment as though it were the whole value."""
        text = self._prompt_text([
            {"name": "cluster_bbox", "dtype": "geometry",
             "sample_values": ["0106000020E6100000" + "A" * 5_000]},
        ])
        assert "…" in text

    def test_short_values_are_left_exactly_as_they_are(self):
        """Truncation must not touch ordinary data. Most example values are
        short, and they are the ones carrying the meaning."""
        text = self._prompt_text([
            {"name": "city", "dtype": "text",
             "sample_values": ["Cairo", "Giza", "Luxor"]},
        ])
        for value in ("Cairo", "Giza", "Luxor"):
            assert value in text
        assert "…" not in text

    def test_a_wide_geometry_table_stays_within_the_context_window(self):
        """The live case: many geometry columns on one view. Asserted in
        characters against a conservative chars-per-token ratio, because the
        thing that actually broke was total prompt size, not any one value."""
        blob = "0106000020E6100000" + "A" * 20_000
        columns = [{"name": f"geom_{i}", "dtype": "geometry",
                    "sample_values": [blob] * 5} for i in range(52)]
        text = self._prompt_text(columns)
        # 32,768-token window, ~2 chars/token for hex -- keep well clear.
        assert len(text) < 30_000, (
            f"{len(text)} characters of prompt for one wide geometry view"
        )

    def test_top_k_values_are_truncated_too(self):
        """`top_k` takes 8 values where samples take 5, so it is the LARGER
        exposure of the two -- and it is the branch that actually runs for any
        profiled column."""
        blob = "0106000020E6100000" + "A" * 20_000
        text = self._prompt_text([
            {"name": "cluster_bbox", "dtype": "geometry",
             "top_k": [{"value": blob, "count": 3} for _ in range(8)]},
        ])
        assert len(text) < 4_000, (
            f"the prompt is {len(text)} characters; top_k values are not truncated"
        )



class TestAWideTableIsStillDescribable:
    """The response grows with the column count; the prompt does not.

    That asymmetry is what made this fail invisibly. A fixed `max_tokens=900`
    is generous for a five-column table and short for a fifty-column one, and
    the short case does not error -- the JSON is simply cut off mid-object, the
    contract fails, and `complete_json` returns None as designed. On the live
    source that cost the six ~50-column geometry cluster views their
    descriptions while the sync still reported `ok`.
    """

    class Recorder:
        """A client that records what it was asked, and answers correctly."""

        def __init__(self, fail_chunks=()):
            self.calls = []
            self.fail_chunks = set(fail_chunks)
            self.last_error = "recorded failure"

        async def complete_json(self, messages, schema, *, max_tokens, temperature,
                                background=False):
            index = len(self.calls)
            body = messages[-1]["content"]
            names = [line.split()[1] for line in body.splitlines()
                     if line.startswith("- ")]
            self.calls.append({"names": names, "max_tokens": max_tokens})
            if index in self.fail_chunks:
                return None
            return {"table": f"A table, per chunk {index}.",
                    "descriptions": {n: f"The {n} column." for n in names}}

    def _columns(self, n):
        return [{"name": f"col_{i:03}", "dtype": "text"} for i in range(n)]

    async def test_every_column_of_a_fifty_column_table_is_described(self):
        from app.services.metadata.infer_semantic import describe_with_llm

        client = self.Recorder()
        out = await describe_with_llm("wide", self._columns(50), client, allow=True)

        described = {k for k in out if not k.startswith("__")}
        assert described == {c["name"] for c in self._columns(50)}, (
            f"{50 - len(described)} columns of a 50-column table went undescribed"
        )

    async def test_a_wide_table_is_asked_about_in_chunks(self):
        from app.services.metadata.infer_semantic import (
            COLUMNS_PER_DESCRIBE_CALL, describe_with_llm)

        client = self.Recorder()
        await describe_with_llm("wide", self._columns(50), client, allow=True)

        assert len(client.calls) == 2
        assert all(len(c["names"]) <= COLUMNS_PER_DESCRIBE_CALL
                   for c in client.calls)
        # Chunks partition the columns: none repeated, none dropped.
        seen = [n for c in client.calls for n in c["names"]]
        assert len(seen) == len(set(seen)) == 50

    async def test_an_ordinary_table_still_costs_exactly_one_call(self):
        """Chunking must not tax the common case. Most tables are well under
        the threshold, and turning one request into two for all of them would
        trade one bug for a slower sync."""
        from app.services.metadata.infer_semantic import describe_with_llm

        client = self.Recorder()
        await describe_with_llm("narrow", self._columns(12), client, allow=True)
        assert len(client.calls) == 1

    async def test_the_token_budget_grows_with_what_was_asked(self):
        from app.services.metadata.infer_semantic import describe_with_llm

        narrow, wide = self.Recorder(), self.Recorder()
        await describe_with_llm("narrow", self._columns(5), narrow, allow=True)
        await describe_with_llm("wide", self._columns(40), wide, allow=True)

        assert wide.calls[0]["max_tokens"] > narrow.calls[0]["max_tokens"], (
            "a 40-column table was given the same output budget as a 5-column "
            "one, which is the defect this fixes"
        )

    async def test_one_failed_chunk_does_not_cost_the_whole_table(self):
        """A partly described 50-column view beats an undescribed one, and the
        columns that missed out are simply proposed again on the next sync."""
        from app.services.metadata.infer_semantic import describe_with_llm

        client = self.Recorder(fail_chunks={0})
        out = await describe_with_llm("wide", self._columns(50), client, allow=True)

        described = {k for k in out if not k.startswith("__")}
        assert described, "a single failed chunk wiped the entire table"
        assert len(described) == 10, described

    async def test_the_table_sentence_survives_chunking(self):
        """It rides along on the column call to avoid a request per table. That
        must keep working when there is more than one call."""
        from app.services.metadata.infer_semantic import (
            _TABLE_DESCRIPTION_KEY, describe_with_llm)

        client = self.Recorder()
        out = await describe_with_llm("wide", self._columns(50), client, allow=True)
        assert out.get(_TABLE_DESCRIPTION_KEY)

    async def test_the_table_sentence_is_not_rewritten_by_later_chunks(self):
        from app.services.metadata.infer_semantic import (
            _TABLE_DESCRIPTION_KEY, describe_with_llm)

        client = self.Recorder()
        out = await describe_with_llm("wide", self._columns(50), client, allow=True)
        assert out[_TABLE_DESCRIPTION_KEY] == "A table, per chunk 0."



class TestAViewIsNotDescribedAsATable:
    """A view was being described as "This TABLE stores normalized cluster
    solution data..." -- and the model had no way to know better, because the
    kind was never passed and the system message asserted "table" outright.

    48 of the 82 objects on the live source are views, so the majority of the
    catalog was mislabelled. It matters beyond wording: "stores" is false about
    where the rows live and implies the object can be written to. What a reader
    needs from a view is what question it answers and what it derives from.
    """

    def _text(self, columns, kind):
        from app.services.metadata.infer_semantic import build_description_prompt
        return "".join(m["content"]
                       for m in build_description_prompt("v_thing", columns, kind))

    COLUMNS = [{"name": "cluster_id", "dtype": "integer"},
               {"name": "state_code", "dtype": "text"}]

    def test_a_view_is_called_a_view(self):
        text = self._text(self.COLUMNS, "view")
        assert "VIEW" in text
        assert "View: v_thing" in text

    def test_a_view_prompt_says_what_a_view_is(self):
        """The word alone was not enough to displace the behaviour. The prompt
        states the property that makes the difference -- rows are derived when
        read, not stored."""
        text = self._text(self.COLUMNS, "view").lower()
        assert "saved query" in text
        assert "derived" in text

    def test_a_view_is_told_not_to_claim_it_stores_anything(self):
        assert '"stores"' in self._text(self.COLUMNS, "view")

    def test_a_table_is_still_described_as_a_table(self):
        text = self._text(self.COLUMNS, "table")
        assert "TABLE" in text
        assert "Table: v_thing" in text
        assert "saved query" not in text.lower()

    def test_the_default_is_a_table(self):
        """Every caller that has not been updated keeps its old behaviour
        rather than silently describing tables as views."""
        from app.services.metadata.infer_semantic import build_description_prompt
        text = "".join(m["content"]
                       for m in build_description_prompt("t", self.COLUMNS))
        assert "Table: t" in text

    def test_a_materialized_view_is_treated_as_a_view(self):
        """Its rows ARE stored, which makes it the awkward case -- but it is
        still defined as a query over other objects, and that is the part a
        reader needs told. Calling it a table would hide where its data comes
        from."""
        for kind in ("materialized view", "MATERIALIZED VIEW", "m_view"):
            assert "VIEW" in self._text(self.COLUMNS, kind), kind

    async def test_the_kind_reaches_the_prompt_from_describe_with_llm(self):
        """The wiring, not just the wording: a correct prompt builder is worth
        nothing if the caller never passes the kind -- which is exactly the
        defect being fixed."""
        from app.services.metadata.infer_semantic import describe_with_llm

        seen = {}

        class Client:
            last_error = None

            async def complete_json(self, messages, schema, *, max_tokens,
                                    temperature, background=False):
                seen["text"] = "".join(m["content"] for m in messages)
                return {"table": "x", "descriptions": {}}

        await describe_with_llm("v_thing", self.COLUMNS, Client(),
                                allow=True, kind="view")
        assert "View: v_thing" in seen["text"]


class TestTheOverviewSeparatesTablesFromViews:
    """The database-level prompt listed every object under one "Tables:"
    heading, flattening the same distinction. On a source where views outnumber
    tables 48 to 34, that invites an overview describing half the database as
    storage it is not."""

    OBJECTS = [
        {"name": "students", "kind": "table",
         "columns": [{"name": "id", "role": "identifier"}]},
        {"name": "v_student_scores", "kind": "view",
         "columns": [{"name": "score", "semantic_type": "measure"}]},
    ]

    def _text(self):
        from app.services.metadata.infer_semantic import build_source_prompt
        return "".join(m["content"]
                       for m in build_source_prompt("maps", self.OBJECTS))

    def test_views_are_listed_under_their_own_heading(self):
        text = self._text()
        assert "Views" in text
        tables_at = text.index("Tables")
        views_at = text.index("Views")
        assert text.index("students") > tables_at
        assert text.index("v_student_scores") > views_at

    def test_the_overview_is_told_what_the_split_means(self):
        text = self._text().lower()
        assert "saved queries" in text
        assert "stored data" in text

    def test_a_database_with_no_views_gets_no_views_heading(self):
        """An empty section is noise, and noise in a prompt is cost."""
        from app.services.metadata.infer_semantic import build_source_prompt
        text = "".join(m["content"] for m in build_source_prompt(
            "maps", [self.OBJECTS[0]]))
        assert "Views (" not in text

    def test_an_object_with_no_kind_is_treated_as_a_table(self):
        from app.services.metadata.infer_semantic import build_source_prompt
        text = "".join(m["content"] for m in build_source_prompt(
            "maps", [{"name": "legacy", "columns": []}]))
        assert "Tables" in text
        assert "Views (" not in text
