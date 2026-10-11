"""The Meaning map: every count read against its base (docs/meaning-map/PLAN.md)."""
from types import SimpleNamespace as NS

from app.services.guided_setup import answer, meaning


def table(name, columns, group="main", rows=1000):
    cols = [NS(id=i, name=c, dtype=d) for i, (c, d) in enumerate(columns)]
    return {"id": hash(name) % 9999, "name": name, "schema": None, "group": group, "rows": rows,
            "_columns": cols, "_stats": {}, "description": None}


class TestLinks:
    def test_few_events_on_many_rows_happen_to_them(self):
        # 2,343 complaints on 64,420 shipments, one each
        assert meaning.classify_link(2343, 2343, 64420) == "events"

    def test_many_rows_per_parent_simply_belong_to_it(self):
        # 64,420 shipments of 1,800 customers
        assert meaning.classify_link(64420, 1650, 1800) == "belongs"

    def test_a_shared_id_column_links_tables_with_no_declared_join(self):
        facts = [table("shipments", [("shipment_id", "integer"), ("customer_id", "integer")]),
                 table("complaints", [("complaint_id", "integer"), ("shipment_id", "integer")]),
                 table("app_log", [("shipment_id", "integer")], group="technical")]
        got = meaning.candidate_links(facts, declared=[])
        assert got == [("shipments", "shipment_id", "complaints", "shipment_id", False)]

    def test_a_declared_join_is_not_measured_twice(self):
        facts = [table("shipments", [("customer_id", "integer")]), table("customers", [("customer_id", "integer")])]
        got = meaning.candidate_links(facts, declared=[("shipments", "customer_id", "customers", "customer_id")])
        assert got == [("shipments", "customer_id", "customers", "customer_id", True)]


class TestMap:
    def the_map(self):
        m = meaning.Map()
        m.grains = {"shipments": {"row_is": "one parcel", "kind": "activity"},
                    "complaints": {"row_is": "one complaint", "kind": "event"}}
        m.bases = [{"events": "complaints", "base": "shipments", "via": ["shipment_id", "shipment_id"],
                    "coverage": 0.036, "per_base": 0.0364, "per": 1000}]
        m.outcomes = [{"table": "shipments", "column": "is_late", "boolean": True,
                       "values": [{"value": "False", "share": 0.82}, {"value": "True", "share": 0.18}]}]
        m.numbers = {("shipments", "delivery_fee_egp"): {"kind": "amount", "unit": "EGP", "direction": "neither"},
                     ("shipments", "customer_rating"): {"kind": "score", "unit": "", "direction": "higher_better"},
                     ("shipments", "delivery_days"): {"kind": "duration", "unit": "days", "direction": "higher_worse"}}
        return m

    def test_events_without_their_base_can_only_be_counted(self):
        m = self.the_map()
        assert m.events_without_base(["complaints", "branches"]) == m.bases
        assert m.events_without_base(["complaints", "shipments"]) == []
        assert m.events_without_base(["shipments"]) == []

    def test_a_person_reads_it_in_plain_sentences(self):
        lines = meaning.sentences(self.the_map(), "en", {"complaints": "Customer complaints"})
        texts = [x["text"] for x in lines]
        assert "Customer complaints are counted against Shipments: about 36 for every 1,000 shipments." in texts
        assert "Shipments: is late — 18%" in texts
        assert "Add up: delivery fee egp (EGP)." in texts
        assert any("customer rating — higher is better" in t and "delivery days (days) — lower is better" in t
                   for t in texts)
        arabic = meaning.sentences(self.the_map(), "ar")
        assert any("لكل 1,000" in x["text"] for x in arabic)

    def test_the_model_is_told_what_is_counted_against_what(self):
        text = meaning.prompt_text(self.the_map())
        assert "`complaints` happen to `shipments`" in text and "36 per 1,000 shipments" in text
        assert "`shipments.customer_rating` is score, higher is BETTER" in text
        assert "`shipments.delivery_days` is duration in days, higher is WORSE" in text
        # Narrowed to the tables a dataset was made from.
        assert "customer_rating" not in meaning.prompt_text(self.the_map(), ["complaints"])

    def test_a_number_is_found_by_its_column(self):
        m = self.the_map()
        assert m.number("customer_rating")["kind"] == "score"
        assert m.number("nothing") is None

    def test_without_a_model_a_number_is_read_from_its_name(self):
        assert meaning.plain_number("customer_id")["kind"] == "code"
        assert meaning.plain_number("delivery_days")["kind"] == "duration"
        assert meaning.plain_number("customer_rating") == {"kind": "score", "unit": "", "direction": "higher_better"}
        assert meaning.plain_number("delivery_fee_egp")["kind"] == "amount"


class TestSizeCheck:
    def test_a_count_that_follows_size_is_not_a_finding(self):
        sizes = {"Cairo": 17000, "Giza": 11000, "Alexandria": 7000, "Aswan": 600}
        complaints = {"Cairo": 630, "Giza": 380, "Alexandria": 250, "Aswan": 40}
        assert answer.follows(complaints, sizes) is True

    def test_a_count_that_goes_against_size_is(self):
        sizes = {"Cairo": 17000, "Giza": 11000, "Alexandria": 7000, "Aswan": 600}
        complaints = {"Cairo": 40, "Giza": 250, "Alexandria": 380, "Aswan": 630}
        assert answer.follows(complaints, sizes) is False

    def test_groups_of_the_same_size_cannot_mislead(self):
        sizes = {"a": 1000, "b": 1100, "c": 1050}
        assert answer.follows({"a": 10, "b": 30, "c": 20}, sizes) is False


class TestLinkConsistency:
    """Phase 2 #20 (docs/discovery/PLAN.md): a row that points at nothing drops
    out of every joined figure without a word."""
    LINK = {"child": "lines", "child_column": "head_id", "parent": "heads", "parent_column": "id", "link": "belongs",
            "declared": True, "child_rows": 1000, "parent_rows": 200, "coverage": 0.9, "per_base": 5.0}

    def test_every_value_found_is_consistent(self):
        from app.services.guided_setup.meaning import link_check
        got = link_check(self.LINK, 1000, 1000)
        assert got["verdict"] == "consistent" and got["orphans"] == 0 and got["says"] == "Every lines.head_id exists in heads.id."
        assert got["parents_with_children_pct"] == 90.0

    def test_orphans_are_counted_and_said_in_plain_words(self):
        from app.services.guided_setup.meaning import link_check
        few = link_check(self.LINK, 1000, 995)
        assert few["verdict"] == "few_orphans" and few["orphans"] == 5 and few["orphan_pct"] == 0.5
        many = link_check(self.LINK, 1000, 700)
        assert many["verdict"] == "many_orphans" and "300 rows of lines (30.0%) hold a value of head_id" in many["says"]
        assert "left out of anything that joins the two" in many["says"]
        one = link_check({**self.LINK, "child_rows": 100000}, 100000, 99999)
        assert one["says"].startswith("1 row of lines (under 0.1%)") and "it is left out" in one["says"]

    def test_a_row_with_no_value_is_not_an_orphan(self):
        from app.services.guided_setup.meaning import link_check
        got = link_check(self.LINK, 800, 800)                    # 200 rows never claimed a parent
        assert got["verdict"] == "consistent" and got["without_value"] == 200 and got["without_value_pct"] == 20.0

    def test_what_could_not_be_counted_is_said_so(self):
        from app.services.guided_setup.meaning import link_check
        assert link_check(self.LINK, None, 10)["verdict"] == "unknown"
        assert link_check(self.LINK, 0, 0)["verdict"] == "empty"
