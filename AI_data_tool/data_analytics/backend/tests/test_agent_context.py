"""What the agent knows about a source — and what it must NOT know.

The catalog (Layer 1) is the v1 implementation of Layer 3 (spec F6). The
critical property is F1: inferred relationships are PROPOSALS and never enter
the join whitelist. 105 of the live source's 133 relationships are inferred;
an agent that joined on them would return plausible wrong numbers.
"""
import pytest

from app.models.models import (ColumnStats, DataSource, Entity, GlossaryTerm,
                               Organization, SourceColumn, SourceObject,
                               SourceRelationship)
from app.services.agent.context import (EntityInfo, JoinInfo, ObjectInfo,
                                        SchemaContext, load_context)


@pytest.fixture
async def catalog(db_session):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    ds = DataSource(name="shop", type="postgresql", org_id=org.id, config={})
    db_session.add(ds)
    await db_session.flush()

    objs = {}
    for name, kind, cols in [
        ("customers", "table", [("id", "integer"), ("city", "text")]),
        ("orders", "table", [("id", "integer"), ("customer_id", "integer"),
                             ("total", "numeric")]),
        ("v_sales", "view", [("city", "text"), ("revenue", "numeric")]),
    ]:
        o = SourceObject(data_source_id=ds.id, org_id=org.id, name=name,
                         kind=kind, description=f"About {name}.")
        db_session.add(o)
        await db_session.flush()
        objs[name] = o
        for cname, dtype in cols:
            db_session.add(SourceColumn(source_object_id=o.id, name=cname,
                                        dtype=dtype))

    db_session.add(SourceRelationship(
        data_source_id=ds.id, org_id=org.id,
        from_object_id=objs["orders"].id, from_column="customer_id",
        to_object_id=objs["customers"].id, to_column="id",
        source="declared", confidence=1.0))
    db_session.add(SourceRelationship(
        data_source_id=ds.id, org_id=org.id,
        from_object_id=objs["v_sales"].id, from_column="city",
        to_object_id=objs["customers"].id, to_column="city",
        source="inferred", confidence=0.9))
    await db_session.commit()
    return {"org": org, "ds": ds}


class TestWhatTheAgentKnows:
    async def test_every_object_and_column_is_visible(self, db_session, catalog):
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        assert ctx.has_table("orders")
        assert ctx.has_column("orders", "customer_id")
        assert not ctx.has_table("ghost")
        assert not ctx.has_column("orders", "ghost")

    async def test_the_render_carries_descriptions_and_kinds(self, db_session, catalog):
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        text = ctx.render()
        assert "About orders." in text
        assert "view" in text.lower()   # v_sales is labelled as what it is


class TestTheProvenanceRule:
    async def test_a_declared_join_is_allowed(self, db_session, catalog):
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        assert ctx.join_allowed("orders", "customer_id", "customers", "id")
        # Order-insensitive: a JOIN may be written either way round.
        assert ctx.join_allowed("customers", "id", "orders", "customer_id")

    async def test_an_inferred_join_is_not_in_the_whitelist(self, db_session, catalog):
        """THE most important assertion in the layer (spec F1). An inferred
        edge is a proposal for a human, not a fact for the agent."""
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        assert not ctx.join_allowed("v_sales", "city", "customers", "city")

    async def test_the_render_never_offers_an_inferred_join(self, db_session, catalog):
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        assert "v_sales.city" not in ctx.render().split("Joins")[-1]


class TestCanonicalAndEnumLabels:
    """T1 (canonical-source flags) and T2 (enum value labels) — the two Layer-3
    semantics gaps identified as the agent's accuracy ceiling. Both are advisory
    text in the prompt, never enforced by V3, so what matters here is that
    render() actually carries them."""

    @pytest.fixture
    async def source_with_flags(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        ds = DataSource(name="shop", type="postgresql", org_id=org.id, config={})
        db_session.add(ds)
        await db_session.flush()

        summary = SourceObject(
            data_source_id=ds.id, org_id=org.id, name="daily_revenue_summary",
            kind="table", description="Pre-aggregated daily revenue.",
            is_canonical=True,
        )
        orders = SourceObject(
            data_source_id=ds.id, org_id=org.id, name="orders", kind="table",
            description="Raw order rows.",
        )
        db_session.add_all([summary, orders])
        await db_session.flush()

        db_session.add(SourceColumn(
            source_object_id=orders.id, name="st_cd", dtype="integer",
            enum_labels={"1": "new", "2": "paid", "3": "cancelled"},
        ))
        db_session.add(SourceColumn(
            source_object_id=orders.id, name="total", dtype="numeric",
        ))
        await db_session.commit()
        return {"org": org, "ds": ds}

    async def test_a_canonical_object_is_marked_in_the_render(
        self, db_session, source_with_flags
    ):
        ctx = await load_context(db_session, source_with_flags["ds"].id,
                                 source_with_flags["org"].id)
        text = ctx.render()
        assert "daily_revenue_summary" in text
        assert "[CANONICAL" in text
        # A non-canonical object gets no such marker.
        orders_line = next(l for l in text.splitlines() if l.startswith("- orders"))
        assert "[CANONICAL" not in orders_line

    async def test_object_info_carries_is_canonical(self, db_session, source_with_flags):
        ctx = await load_context(db_session, source_with_flags["ds"].id,
                                 source_with_flags["org"].id)
        assert ctx.objects["daily_revenue_summary"].is_canonical is True
        assert ctx.objects["orders"].is_canonical is False

    async def test_a_labelled_column_renders_compactly(self, db_session, source_with_flags):
        ctx = await load_context(db_session, source_with_flags["ds"].id,
                                 source_with_flags["org"].id)
        text = ctx.render()
        assert "st_cd integer (1=new, 2=paid, 3=cancelled)" in text

    async def test_an_unlabelled_column_renders_plainly(self, db_session, source_with_flags):
        ctx = await load_context(db_session, source_with_flags["ds"].id,
                                 source_with_flags["org"].id)
        text = ctx.render()
        assert "total numeric" in text
        assert "total numeric (" not in text


class TestHighNullColumns:
    """The measured trap: the agent picked `maps_states.students_count` for a
    submissions question -- a column literally named what was asked, but
    100% NULL. The catalog already knows via ColumnStats.null_ratio; this
    makes load_context/render surface it so the model never picks a column
    that structurally cannot answer the question."""

    @pytest.fixture
    async def source_with_stats(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        ds = DataSource(name="shop", type="postgresql", org_id=org.id, config={})
        db_session.add(ds)
        await db_session.flush()

        maps_states = SourceObject(
            data_source_id=ds.id, org_id=org.id, name="maps_states",
            kind="table", description="State-level rollups.",
        )
        db_session.add(maps_states)
        await db_session.flush()

        all_null = SourceColumn(source_object_id=maps_states.id,
                                name="students_count", dtype="integer")
        half_null = SourceColumn(source_object_id=maps_states.id,
                                 name="half_null_col", dtype="integer")
        no_stats = SourceColumn(source_object_id=maps_states.id,
                                name="no_stats_col", dtype="integer")
        db_session.add_all([all_null, half_null, no_stats])
        await db_session.flush()

        db_session.add(ColumnStats(source_column_id=all_null.id, null_ratio=1.0))
        db_session.add(ColumnStats(source_column_id=half_null.id, null_ratio=0.5))
        # no_stats_col intentionally has no ColumnStats row at all.
        await db_session.commit()
        return {"org": org, "ds": ds}

    async def test_all_null_column_is_marked_in_the_enriched_render(
        self, db_session, source_with_stats
    ):
        ctx = await load_context(db_session, source_with_stats["ds"].id,
                                 source_with_stats["org"].id)
        text = ctx.render()
        assert ("students_count integer (ALL NULL — contains no data, "
               "never use it)") in text

    async def test_a_half_null_column_carries_no_marker(
        self, db_session, source_with_stats
    ):
        ctx = await load_context(db_session, source_with_stats["ds"].id,
                                 source_with_stats["org"].id)
        text = ctx.render()
        segment = next(s for s in text.split(", ") if "half_null_col" in s)
        assert "ALL NULL" not in segment

    async def test_a_column_with_no_stats_row_carries_no_marker(
        self, db_session, source_with_stats
    ):
        ctx = await load_context(db_session, source_with_stats["ds"].id,
                                 source_with_stats["org"].id)
        text = ctx.render()
        segment = next(s for s in text.split(", ") if "no_stats_col" in s)
        assert "ALL NULL" not in segment

    async def test_the_skeleton_line_never_carries_the_marker(self):
        """Pass 1 stays lean -- the marker is pass-2-only enrichment."""
        from app.services.agent.context import _skeleton_object_line
        o = ObjectInfo("maps_states", "table", "desc",
                       {"students_count": "integer"},
                       high_null={"students_count"})
        assert "ALL NULL" not in _skeleton_object_line(o, None)

    def test_the_skeleton_line_omits_high_null_columns_entirely(self):
        """Live catalog check: a bare column name with no marker is pure
        bait -- the model picked students_count again because the skeleton
        (the tier that actually survived the 24k-char budget on the real
        82-object catalog) listed the name with no signal it was empty.
        Dropping it from the skeleton removes the bait AND saves budget;
        V2 validation (has_column) reads o.columns, never the render, so a
        user who explicitly names the column is unaffected."""
        from app.services.agent.context import _skeleton_object_line
        o = ObjectInfo("maps_states", "table", "desc",
                       {"students_count": "integer", "state": "text"},
                       high_null={"students_count"})
        line = _skeleton_object_line(o, None)
        assert "students_count" not in line
        assert "state" in line

    def test_the_enriched_line_still_carries_name_and_marker(self):
        """The enriched line is the one place a specifically-asked-about
        column still gets explained, rather than mysteriously absent."""
        from app.services.agent.context import _full_object_line
        o = ObjectInfo("maps_states", "table", "desc",
                       {"students_count": "integer", "state": "text"},
                       high_null={"students_count"})
        line = _full_object_line(o)
        assert ("students_count integer (ALL NULL — contains no data, "
               "never use it)") in line


class TestSkeletonDescription:
    """Measured trap #2, same family as high-null: `maps_state_student_solution`
    and `maps_state_student_solution_details` were BOTH skeleton-tier on the
    live catalog. Skeletons carried no description, so nothing told the model
    which table was placements vs. which was the detailed coordinate/symbol
    data for student solutions -- it picked the parent table and counted
    wrong, deterministically, twice. A hard-truncated description at
    skeleton tier is the disambiguator."""

    def test_skeleton_line_carries_a_truncated_description_with_ellipsis(self):
        from app.services.agent.context import (MAX_SKELETON_DESC_CHARS,
                                                 _skeleton_object_line)
        long_desc = ("Detailed coordinate data for student solutions, "
                    "including every symbol placed and its screen position "
                    "on the canvas during the exercise.")
        assert len(long_desc) > MAX_SKELETON_DESC_CHARS
        o = ObjectInfo("maps_state_student_solution_details", "table",
                       long_desc, {"id": "integer"})
        line = _skeleton_object_line(o, None)
        assert "…" in line
        # The rendered description fragment itself must respect the cap.
        desc_fragment = line.split(" -- ")[1].split(": ")[0]
        assert len(desc_fragment) <= MAX_SKELETON_DESC_CHARS
        assert long_desc[:40] in line  # the disambiguating prefix survives

    def test_a_short_description_is_not_truncated(self):
        from app.services.agent.context import _skeleton_object_line
        o = ObjectInfo("orders", "table", "Raw order rows.", {"id": "integer"})
        line = _skeleton_object_line(o, None)
        assert "Raw order rows." in line
        assert "…" not in line

    def test_at_a_tight_budget_columns_degrade_to_zero_before_the_description(self):
        """The ladder's whole point: for table SELECTION, what a table IS
        beats what it contains -- a tight budget must sacrifice column
        detail long before it sacrifices the disambiguating description."""
        long_desc = ("Detailed coordinate data for student solutions, "
                    "including every symbol placed on the canvas.")
        ctx = SchemaContext(source_id=1, family="postgresql")
        ctx.objects["maps_state_student_solution_details"] = ObjectInfo(
            "maps_state_student_solution_details", "table", long_desc,
            {f"col_{i}": "varchar" for i in range(30)})
        # Budget far too small for a full column list, generous enough for
        # name + short description + a degraded column summary.
        text = ctx.render(max_chars=200)
        assert "maps_state_student_solution_details" in text
        assert "Detailed coordinate data" in text
        assert "col_29" not in text  # columns collapsed well before this

    def test_the_every_name_guarantee_still_holds_with_descriptions_added(self):
        """Adding a description to every skeleton line grows the render;
        confirm the H7 guarantee (every object NAME survives the default
        budget) still holds rather than silently regressing."""
        ctx = TestLargeCatalogRenderBudget._big_ctx()
        text = ctx.render()
        for name in ctx.objects:
            assert f"- {name} (" in text, f"{name} missing from the default render"

    def test_the_enriched_line_is_unaffected_by_the_skeleton_change(self):
        """render()'s full-description behaviour (pre-existing) is untouched
        -- only the skeleton line gained a (truncated) description."""
        long_desc = ("Detailed coordinate data for student solutions, "
                    "including every symbol placed on the canvas during "
                    "the exercise, well past ninety characters long.")
        ctx = SchemaContext(source_id=1, family="postgresql")
        ctx.objects["maps_state_student_solution_details"] = ObjectInfo(
            "maps_state_student_solution_details", "table", long_desc,
            {"id": "integer"})
        text = ctx.render()  # tiny catalog -- fully enriched
        assert long_desc in text
        assert "…" not in text


class TestOrgScoping:
    async def test_another_orgs_source_yields_nothing(self, db_session, catalog):
        other = Organization(name="Rival")
        db_session.add(other)
        await db_session.commit()
        ctx = await load_context(db_session, catalog["ds"].id, other.id)
        assert ctx.objects == {}


class TestGlossary:
    """T3 — 'إجمالي المبيعات' and 'GMV' must resolve to the same metric
    (spec L3 gap #3). Matching is a plain casefold substring check, which is
    unicode-correct and therefore works for Arabic (no case distinction to
    get wrong) without any special-casing."""

    @pytest.fixture
    async def glossary_source(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        ds = DataSource(name="shop", type="postgresql", org_id=org.id, config={})
        db_session.add(ds)
        await db_session.flush()

        db_session.add(GlossaryTerm(
            org_id=org.id, data_source_id=ds.id, term="GMV",
            definition="Gross merchandise value.",
            synonyms=["إجمالي المبيعات", "gross sales"],
            maps_to_object="orders", maps_to_column="total",
        ))
        db_session.add(GlossaryTerm(
            org_id=org.id, data_source_id=ds.id, term="churn rate",
            definition="Fraction of customers who cancelled.",
        ))
        # Org-wide: no data_source_id at all.
        db_session.add(GlossaryTerm(
            org_id=org.id, data_source_id=None, term="ARR",
            definition="Annual recurring revenue.",
        ))
        # Live bug fixture: canonical (hamza) spelling is the STORED value;
        # the synonym is the hamza-less spelling a question actually used.
        db_session.add(GlossaryTerm(
            org_id=org.id, data_source_id=ds.id, term="إتجاه هجوم العدو",
            definition="Attack-direction symbol.",
            synonyms=["اتجاه هجوم العدو"],
            maps_to_object="v_student_solution_correction",
            maps_to_column="symbol_name",
        ))
        await db_session.commit()
        return {"org": org, "ds": ds}

    async def test_arabic_synonym_matches_the_question(
        self, db_session, glossary_source
    ):
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        matched = ctx.glossary_for("ما هو إجمالي المبيعات هذا الشهر؟")
        assert [g.term for g in matched] == ["GMV"]

    async def test_english_synonym_and_term_both_match(
        self, db_session, glossary_source
    ):
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        assert [g.term for g in ctx.glossary_for("what is our GMV")] == ["GMV"]
        assert [g.term for g in
               ctx.glossary_for("what were gross sales last week")] == ["GMV"]

    async def test_unmatched_terms_are_not_matched(self, db_session, glossary_source):
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        matched = ctx.glossary_for("what is our GMV")
        assert "churn rate" not in [g.term for g in matched]
        assert "ARR" not in [g.term for g in matched]

    async def test_org_wide_null_source_term_loads_for_any_source(
        self, db_session, glossary_source
    ):
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        assert "ARR" in [g.term for g in ctx.glossary]

    async def test_render_with_question_surfaces_matched_terms_and_maps_to(
        self, db_session, glossary_source
    ):
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        text = ctx.render(question="what is our GMV")
        assert "Glossary (matched from the question):" in text
        assert "GMV: Gross merchandise value." in text
        assert "[-> orders.total]" in text
        # Unmatched terms are omitted entirely — prompt budget.
        assert "churn rate" not in text
        assert "ARR" not in text

    async def test_render_with_no_matches_adds_no_glossary_block(
        self, db_session, glossary_source
    ):
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        text = ctx.render(question="how many orders shipped yesterday")
        assert "Glossary" not in text

    async def test_render_without_a_question_is_byte_identical_to_before(
        self, db_session, glossary_source
    ):
        """The pre-T3 signature's whole contract: a glossary-loaded context
        must render EXACTLY as it did with no question argument at all."""
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        assert ctx.render() == ctx.render(question=None)
        assert "Glossary" not in ctx.render()

    async def test_a_synonym_matched_term_gets_a_note_naming_both_spellings(
        self, db_session, glossary_source
    ):
        """Verified live: the hint rendered but was descriptive prose, and
        the model still copied the QUESTION's (hamza-less) spelling into a
        SQL predicate, getting zero rows against the STORED (hamza)
        spelling. Matching via a SYNONYM must now render a mechanical
        NOTE naming both spellings."""
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        text = ctx.render(question="ما هو اتجاه هجوم العدو؟")
        assert ("NOTE: the question wrote 'اتجاه هجوم العدو' but the "
               "STORED value is 'إتجاه هجوم العدو' — use the stored "
               "spelling verbatim in SQL predicates.") in text
        assert "[-> v_student_solution_correction.symbol_name]" in text

    async def test_a_term_matched_directly_gets_no_note(
        self, db_session, glossary_source
    ):
        """When the question uses the TERM's own spelling (not a synonym),
        there is no substitution to warn about."""
        ctx = await load_context(db_session, glossary_source["ds"].id,
                                 glossary_source["org"].id)
        text = ctx.render(question="ما هو إتجاه هجوم العدو؟")
        assert "NOTE:" not in text
        # And GMV, matched via the term text itself elsewhere, also stays
        # note-free.
        text2 = ctx.render(question="what is our GMV")
        assert "NOTE:" not in text2


class TestLargeCatalogRenderBudget:
    """H7: round-4 live measurement crashed conditional accuracy 75% -> 25%.
    Root cause, proven live: the old render() built one fully-enriched line
    per object, then sliced the WHOLE text to `max_chars`. On the maps
    source's 82-object catalog (full render 85,095 chars) that slice landed
    mid-list and silently dropped objects past it -- including the CANONICAL
    `omda_symbol_count` and `maps_states`, while the alphabetically-early
    `cycle_students` survived. The model then generated SQL against whatever
    happened to still be in its prompt.

    This reproduces that scale (82 objects, >80k chars full render) and pins
    the two-pass fix's guarantee: every object NAME survives the default
    budget, and canonical objects are listed AND enriched first.
    """

    @staticmethod
    def _big_ctx() -> SchemaContext:
        ctx = SchemaContext(source_id=1, family="postgresql")
        long_desc = "Detailed description of what this table holds and why. " * 20
        columns = {f"col_{i}": "varchar" for i in range(20)}

        # Alphabetically early, plain -- the object that WRONGLY survived the
        # old slice in the live measurement.
        ctx.objects["cycle_students"] = ObjectInfo(
            "cycle_students", "table", long_desc, dict(columns))

        # Alphabetically late, CANONICAL, with more than 6 enum labels on one
        # column -- the object the old slice silently dropped.
        ctx.objects["omda_symbol_count"] = ObjectInfo(
            "omda_symbol_count", "table", long_desc, dict(columns),
            is_canonical=True,
            enum_labels={"col_0": {str(i): f"L{i}" for i in range(10)}},
        )

        # Another alphabetically-late plain object, also dropped by the bug.
        ctx.objects["maps_states"] = ObjectInfo(
            "maps_states", "table", long_desc, dict(columns))

        # Pad out to 82 objects total (already have 3 above), mixing in views
        # so the priority-grouping guarantee (canonical, table, view) is
        # actually exercised. padding_object_006 also carries the
        # live-measured trap: an all-NULL students_count column that must
        # never appear bare in a skeleton line. It is a plain table late
        # enough in enrichment order to reliably remain skeleton-tier under
        # the default budget (verified: it is NOT among the objects pass 2
        # reaches) -- see
        # test_a_high_null_column_is_absent_from_a_skeleton_tier_object.
        for i in range(79):
            kind = "view" if i % 4 == 0 else "table"
            name = f"padding_object_{i:03d}"
            cols = dict(columns)
            high_null = set()
            if name == "padding_object_006":
                cols["students_count"] = "integer"
                high_null = {"students_count"}
            ctx.objects[name] = ObjectInfo(name, kind, long_desc, cols,
                                           high_null=high_null)
        return ctx

    def test_the_fixture_reproduces_the_scale_that_broke(self):
        """Not a claim about render()'s (deliberately degraded) output --
        confirms this test is actually exercising the failure's scale."""
        ctx = self._big_ctx()
        assert len(ctx.objects) == 82
        full = ctx.render(max_chars=10_000_000)  # effectively unbounded
        assert len(full) > 80_000

    def test_every_object_name_survives_the_default_budget(self):
        ctx = self._big_ctx()
        text = ctx.render()
        for name in ctx.objects:
            assert f"- {name} (" in text, f"{name} missing from the default render"

    def test_canonical_objects_are_listed_and_enriched_first(self):
        ctx = self._big_ctx()
        text = ctx.render()
        object_lines = [l for l in text.split("\n") if l.startswith("- ")]

        canon_idx = next(i for i, l in enumerate(object_lines)
                         if l.startswith("- omda_symbol_count "))
        early_idx = next(i for i, l in enumerate(object_lines)
                         if l.startswith("- cycle_students "))
        # Canonical beats even an alphabetically-earlier plain table.
        assert canon_idx < early_idx

        canon_line = object_lines[canon_idx]
        assert "[CANONICAL" in canon_line
        # Enriched, not just a skeleton: dtypes are visible.
        assert "col_0 varchar" in canon_line

    def test_a_high_null_column_is_absent_from_a_skeleton_tier_object(self):
        """Live check on the real 82-object catalog: maps_states stayed a
        SKELETON line (23,921/24,000 chars used) and the bare
        students_count name, with no marker to explain it, was picked
        again. A skeleton line carries no marker by design, so the only
        fix that survives ANY budget is dropping the column from the
        skeleton's column list entirely. padding_object_006 stands in for
        that skeleton-tier object here (confirmed to remain unenriched
        under this fixture's default budget)."""
        ctx = self._big_ctx()
        text = ctx.render()
        line = next(l for l in text.split("\n")
                   if l.startswith("- padding_object_006 "))
        assert "col_0 varchar" not in line, "padding_object_006 unexpectedly enriched"
        assert "students_count" not in line

    def test_enum_label_pairs_are_capped_at_six_in_the_render(self):
        ctx = self._big_ctx()
        text = ctx.render()
        canon_line = next(l for l in text.split("\n")
                          if l.startswith("- omda_symbol_count "))
        for i in range(6):
            assert f"{i}=L{i}" in canon_line
        for i in range(6, 10):
            assert f"{i}=L{i}" not in canon_line


@pytest.fixture
async def chain(db_session):
    """orders -> customers -> regions, a confirmed two-hop chain, plus an
    INFERRED shortcut orders -> regions that must never be used. Module-level
    (not nested in a class) so both TestJoinPath and TestSuggestJoinRoute can
    share it."""
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    ds = DataSource(name="shop", type="postgresql", org_id=org.id, config={})
    db_session.add(ds)
    await db_session.flush()

    objs = {}
    for name, cols in [
        ("orders", [("id", "integer"), ("customer_id", "integer"),
                   ("region_id", "integer")]),
        ("customers", [("id", "integer"), ("region_id", "integer")]),
        ("regions", [("id", "integer"), ("name", "text")]),
        ("island", [("id", "integer")]),   # disconnected from everything
    ]:
        o = SourceObject(data_source_id=ds.id, org_id=org.id, name=name,
                         kind="table")
        db_session.add(o)
        await db_session.flush()
        objs[name] = o
        for cname, dtype in cols:
            db_session.add(SourceColumn(source_object_id=o.id, name=cname,
                                        dtype=dtype))

    db_session.add(SourceRelationship(
        data_source_id=ds.id, org_id=org.id,
        from_object_id=objs["orders"].id, from_column="customer_id",
        to_object_id=objs["customers"].id, to_column="id",
        source="declared", confidence=1.0))
    db_session.add(SourceRelationship(
        data_source_id=ds.id, org_id=org.id,
        from_object_id=objs["customers"].id, from_column="region_id",
        to_object_id=objs["regions"].id, to_column="id",
        source="confirmed", confidence=1.0))
    # The shortcut: real edge, but only INFERRED — never allowed.
    db_session.add(SourceRelationship(
        data_source_id=ds.id, org_id=org.id,
        from_object_id=objs["orders"].id, from_column="region_id",
        to_object_id=objs["regions"].id, to_column="id",
        source="inferred", confidence=0.8))
    await db_session.commit()
    return {"org": org, "ds": ds}


class TestJoinPath:
    """T4 — join edges are not resolved paths (spec L3 gap #7)."""

    async def test_two_hop_path_is_found(self, db_session, chain):
        ctx = await load_context(db_session, chain["ds"].id, chain["org"].id)
        path = ctx.join_path("orders", "regions")
        assert path is not None
        assert [(j.from_table, j.from_column, j.to_table, j.to_column)
               for j in path] == [
            ("orders", "customer_id", "customers", "id"),
            ("customers", "region_id", "regions", "id"),
        ]

    async def test_the_path_never_uses_the_inferred_shortcut(self, db_session, chain):
        """F1, end to end: the inferred orders->regions edge is a real row in
        the DB, but load_context never puts it in ctx.joins, so join_path
        cannot find or use it — the two-hop confirmed/declared route is the
        ONLY route that exists as far as the context is concerned."""
        ctx = await load_context(db_session, chain["ds"].id, chain["org"].id)
        path = ctx.join_path("orders", "regions")
        assert len(path) == 2, "a one-edge shortcut would mean the inferred row leaked in"
        assert not any(j.provenance == "inferred" for j in path)

    async def test_disconnected_tables_return_none(self, db_session, chain):
        ctx = await load_context(db_session, chain["ds"].id, chain["org"].id)
        assert ctx.join_path("orders", "island") is None

    async def test_unknown_table_returns_none(self, db_session, chain):
        ctx = await load_context(db_session, chain["ds"].id, chain["org"].id)
        assert ctx.join_path("orders", "ghost") is None
        assert ctx.join_path("ghost", "orders") is None

    async def test_direct_edge_is_a_single_hop(self, db_session, chain):
        ctx = await load_context(db_session, chain["ds"].id, chain["org"].id)
        path = ctx.join_path("orders", "customers")
        assert len(path) == 1
        assert path[0].to_table == "customers"


class TestSuggestJoinRoute:
    async def test_chains_two_legs_into_one_route_string(self, db_session, chain):
        from app.services.agent.context import suggest_join_route
        ctx = await load_context(db_session, chain["ds"].id, chain["org"].id)
        route = suggest_join_route(ctx, ["orders", "customers", "regions"])
        assert route == ("Join route: orders.customer_id = customers.id "
                         "THEN customers.region_id = regions.id")

    async def test_fewer_than_two_tables_is_none(self, db_session, chain):
        from app.services.agent.context import suggest_join_route
        ctx = await load_context(db_session, chain["ds"].id, chain["org"].id)
        assert suggest_join_route(ctx, ["orders"]) is None
        assert suggest_join_route(ctx, []) is None

    async def test_a_missing_leg_yields_none(self, db_session, chain):
        from app.services.agent.context import suggest_join_route
        ctx = await load_context(db_session, chain["ds"].id, chain["org"].id)
        assert suggest_join_route(ctx, ["orders", "island"]) is None


class TestRetrievalRankedRender:
    """Task R2 (spec section 2-4): retrieval reorders pass-2 enrichment
    priority; it never changes render(question=None), never drops a name
    (H7), and never lets a retrieval failure break the render."""

    @staticmethod
    def _small_ctx() -> SchemaContext:
        """The exact fixture captured (pre-R2, via a checked-out copy of
        context.py at the base of this branch) to pin
        `render(question=None)`'s byte-for-byte output below."""
        ctx = SchemaContext(source_id=1, family="postgresql")
        ctx.objects["customers"] = ObjectInfo(
            "customers", "table", "About customers.",
            {"id": "integer", "city": "text"})
        ctx.objects["orders"] = ObjectInfo(
            "orders", "table", "About orders.",
            {"id": "integer", "customer_id": "integer", "total": "numeric"})
        ctx.objects["v_sales"] = ObjectInfo(
            "v_sales", "view", "About v_sales.",
            {"city": "text", "revenue": "numeric"})
        ctx.objects["omda_symbol_count"] = ObjectInfo(
            "omda_symbol_count", "table", "Canonical counts.",
            {"col_0": "integer"}, is_canonical=True,
            enum_labels={"col_0": {str(i): f"L{i}" for i in range(10)}})
        ctx.joins.append(JoinInfo("orders", "customer_id", "customers", "id",
                                  "declared"))
        return ctx

    @staticmethod
    def _ranking_ctx() -> SchemaContext:
        """alpha/beta/epsilon/gamma tables + delta view, with a single
        confirmed join gamma -> epsilon, used to exercise ranked-tier
        ordering and 1-hop join promotion without DB setup."""
        ctx = SchemaContext(source_id=1, family="postgresql")
        for name in ("alpha", "beta", "epsilon", "gamma"):
            ctx.objects[name] = ObjectInfo(name, "table", f"{name} desc",
                                           {"id": "integer"})
        ctx.objects["delta"] = ObjectInfo("delta", "view", "delta desc",
                                          {"id": "integer"})
        ctx.joins.append(JoinInfo("gamma", "id", "epsilon", "id", "confirmed"))
        return ctx

    # -- render(question=None) is untouched ---------------------------------

    def test_render_question_none_is_byte_identical_to_pre_r2(self):
        """Pinned against the actual pre-R2 output (verified by running the
        unmodified context.py against this same fixture): any future change
        to `_ordered_objects`/`render`'s no-ranking path that alters this
        text is a regression this test is designed to catch."""
        ctx = self._small_ctx()
        text = ctx.render()
        expected = (
            "Objects:\n"
            "- omda_symbol_count (table) [CANONICAL — the source of truth "
            "for what it describes; prefer it over recomputing from raw "
            "tables]: col_0 integer (0=L0, 1=L1, 2=L2, 3=L3, 4=L4, 5=L5) -- "
            "Canonical counts.\n"
            "- customers (table): id integer, city text -- About customers.\n"
            "- orders (table): id integer, customer_id integer, total "
            "numeric -- About orders.\n"
            "- v_sales (view): city text, revenue numeric -- About v_sales."
            "\n\nJoins you may use (the ONLY joins allowed):\n"
            "- orders.customer_id = customers.id"
        )
        assert text == expected

    def test_ordered_objects_default_arg_matches_no_arg(self):
        ctx = self._small_ctx()
        assert ctx._ordered_objects() == ctx._ordered_objects(None) == ctx._ordered_objects([])

    # -- ranked tier + tie-break ---------------------------------------------

    def test_top_ranked_object_is_enriched_and_listed_first(self, monkeypatch):
        ctx = self._ranking_ctx()
        ranking = [("gamma", 0.9), ("beta", 0.5)]
        monkeypatch.setattr("app.services.agent.context.rank_objects",
                            lambda *a, **k: ranking)
        names = [o.name for o in ctx._ordered_objects(ranking)]
        # gamma (top score) first, beta (ranked, lower score) second,
        # epsilon (gamma's 1-hop join neighbor) promoted next, then the
        # unranked rest (alpha, delta) in their OLD relative order.
        assert names == ["gamma", "beta", "epsilon", "alpha", "delta"]

    def test_canonical_breaks_a_score_tie_in_the_ranked_tier(self):
        ctx = self._ranking_ctx()
        ctx.objects["alpha"].is_canonical = True
        # beta listed first in the ranking list itself; canonical alpha must
        # still come first in the ranked tier because canonical breaks ties,
        # not ranking-list order.
        ranking = [("beta", 0.5), ("alpha", 0.5)]
        names = [o.name for o in ctx._ordered_objects(ranking)]
        assert names[0] == "alpha"
        assert names[1] == "beta"

    def test_unranked_objects_keep_old_relative_order(self):
        ctx = self._ranking_ctx()
        # Only alpha is ranked; beta/gamma/epsilon/delta are all "the rest".
        ranking = [("alpha", 0.9)]
        names = [o.name for o in ctx._ordered_objects(ranking)]
        default_names = [o.name for o in ctx._ordered_objects()]
        rest_ranked = [n for n in names if n != "alpha"]
        rest_default = [n for n in default_names if n != "alpha"]
        assert rest_ranked == rest_default

    def test_render_with_a_question_enriches_the_top_ranked_object_first(
        self, monkeypatch,
    ):
        ctx = self._ranking_ctx()
        monkeypatch.setattr(
            "app.services.agent.context.rank_objects",
            lambda *a, **k: [("gamma", 0.9)])
        text = ctx.render(question="anything about gamma")
        object_lines = [l for l in text.split("\n") if l.startswith("- ")]
        assert object_lines[0].startswith("- gamma ")

    def test_h7_breadth_holds_under_tiny_budget_with_ranking_active(
        self, monkeypatch,
    ):
        ctx = TestLargeCatalogRenderBudget._big_ctx()
        ranking = [(name, 1.0 - i * 0.001)
                  for i, name in enumerate(sorted(ctx.objects, reverse=True))][:12]
        monkeypatch.setattr("app.services.agent.context.rank_objects",
                            lambda *a, **k: ranking)
        text = ctx.render(max_chars=500, question="anything")
        for name in ctx.objects:
            assert f"- {name} (" in text, f"{name} missing under ranking + tiny budget"

    # -- retrieval failures degrade to today's static order ------------------

    def test_retrieval_failure_at_context_layer_degrades_to_static_order(
        self, monkeypatch,
    ):
        def boom(*a, **k):
            raise RuntimeError("scorer exploded")
        monkeypatch.setattr("app.services.agent.context.rank_objects", boom)
        ctx = self._ranking_ctx()
        text_with_question = ctx.render(question="alpha")
        text_without_question = ctx.render(question=None)
        assert text_with_question == text_without_question

    def test_off_topic_question_falls_back_to_static_order(self):
        """retrieval.rank_objects's real (unmocked) lexical scorer, not a
        monkeypatched stand-in: a question with no token overlap with any
        object scores everything 0.0, which `_top_k` now filters out
        entirely -- `rank_objects` returns [], `_ordered_objects` sees an
        empty ranking and falls back to the static priority order exactly
        as if no question had been asked at all. Before the zero-score
        filter, off-topic questions instead returned every object tied at
        0.0 and re-sorted them into a worse-than-static order."""
        # Digits share no word token AND no char 3-5-gram with this
        # fixture's object text (none of "alpha desc"/"beta desc"/etc.
        # contain a digit) -- a genuinely zero-overlap question for
        # Backend A, unlike a nonsense word, which can still collide with
        # real text on a short char n-gram by accident.
        off_topic = "0102030405 0607080900 1112131415"
        ctx = self._ranking_ctx()
        ranked_names = [o.name for o in ctx._ordered_objects(
            ctx._retrieval_ranking(off_topic))]
        default_names = [o.name for o in ctx._ordered_objects(None)]
        assert ranked_names == default_names

        text_with_question = ctx.render(question=off_topic)
        text_without_question = ctx.render(question=None)
        assert text_with_question == text_without_question


class TestEntitiesBlock:
    """Task R3 / spec section 5 (E2): a budget-reserved 'Entities:' block,
    present only when the source HAS entities, that can never push an
    object's NAME out of pass 1 (same reservation rule as Glossary/joins)."""

    @staticmethod
    def _ctx_with_entities() -> SchemaContext:
        ctx = SchemaContext(source_id=1, family="postgresql")
        ctx.objects["customers"] = ObjectInfo(
            "customers", "table", "About customers.", {"id": "integer"})
        ctx.objects["orders"] = ObjectInfo(
            "orders", "table", "About orders.", {"id": "integer"})
        ctx.entities.append(EntityInfo(
            name="customer", business_name="Customer",
            grain="One row per customer.",
            description="A person who placed orders.",
            primary_object="customers"))
        ctx.entities.append(EntityInfo(name="order", grain="One row per order."))
        return ctx

    def test_no_entities_means_no_block(self):
        ctx = SchemaContext(source_id=1, family="postgresql")
        ctx.objects["customers"] = ObjectInfo("customers", "table", None, {})
        assert "Entities" not in ctx.render()

    def test_entities_block_lists_every_entity(self):
        ctx = self._ctx_with_entities()
        text = ctx.render()
        assert "Entities:" in text
        assert "customer (Customer): One row per customer." in text
        assert "[customers]" in text
        assert "- order: One row per order." in text

    def test_entities_reservation_never_evicts_an_object_name(self):
        """Same guarantee joins/glossary already give: reserving the block's
        room can shrink pass 1's column verbosity, but every object NAME
        still survives even at an adversarially tiny budget."""
        ctx = self._ctx_with_entities()
        for i in range(30):
            ctx.entities.append(EntityInfo(
                name=f"entity_{i}",
                description="A very long description " * 10))
        text = ctx.render(max_chars=400)
        assert "- customers (" in text
        assert "- orders (" in text

    def test_entities_block_is_capped_with_a_tail_marker(self):
        """Review fix: unlike Glossary (small AND question-matched) or Joins
        (bounded by the schema's actual FK count), an entity block has no
        inherent size cap -- dozens of drafted entities must not shrink the
        objects budget in proportion to how many exist, so the block itself
        stops at MAX_RENDERED_ENTITIES and says how many were left out."""
        from app.services.agent.context import MAX_RENDERED_ENTITIES

        ctx = SchemaContext(source_id=1, family="postgresql")
        ctx.objects["customers"] = ObjectInfo("customers", "table", None, {})
        for i in range(MAX_RENDERED_ENTITIES + 4):
            ctx.entities.append(EntityInfo(name=f"entity_{i:02d}"))

        text = ctx.render()
        block = text.split("Entities:\n", 1)[1]
        shown = [l for l in block.split("\n") if l.startswith("- entity_")]
        assert len(shown) == MAX_RENDERED_ENTITIES
        assert block.split("\n")[-1] == "(+4 more)"

    def test_entities_ranked_top_n_selected_when_question_given(self, monkeypatch):
        """Selection, not just ordering, follows the ranking when a question
        is given -- the top MAX_RENDERED_ENTITIES by score are the ones kept,
        not an arbitrary/alphabetical slice re-sorted afterward."""
        from app.services.agent.context import MAX_RENDERED_ENTITIES

        ctx = SchemaContext(source_id=1, family="postgresql")
        ctx.objects["customers"] = ObjectInfo("customers", "table", None, {})
        names = [f"entity_{i:02d}" for i in range(10)]
        for name in names:
            ctx.entities.append(EntityInfo(name=name))
        # Reverse-alphabetical ranking: highest score to the LAST name, so a
        # match against plain alphabetical selection would fail this test.
        ranking = list(zip(reversed(names), range(len(names), 0, -1)))
        monkeypatch.setattr(
            "app.services.agent.context.rank_documents",
            lambda docs, question, k: ranking)

        text = ctx.render(question="anything")
        block = text.split("Entities:\n", 1)[1]
        shown = [l for l in block.split("\n") if l.startswith("- entity_")]
        assert shown == [f"- entity_{i:02d}" for i in range(9, 9 - MAX_RENDERED_ENTITIES, -1)]
        assert block.split("\n")[-1] == "(+2 more)"

    def test_entities_ranked_by_question_when_given(self, monkeypatch):
        ctx = self._ctx_with_entities()
        monkeypatch.setattr(
            "app.services.agent.context.rank_documents",
            lambda docs, question, k: [("order", 0.9), ("customer", 0.1)])
        text = ctx.render(question="orders")
        block = text.split("Entities:\n", 1)[1]
        assert block.index("- order") < block.index("- customer")

    def test_entity_ranking_failure_degrades_to_alphabetical(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("boom")
        monkeypatch.setattr("app.services.agent.context.rank_documents", boom)
        ctx = self._ctx_with_entities()
        text = ctx.render(question="anything")
        block = text.split("Entities:\n", 1)[1]
        assert block.index("- customer") < block.index("- order")

    async def test_load_context_populates_entities_from_the_db(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        ds = DataSource(name="shop", type="postgresql", org_id=org.id, config={})
        db_session.add(ds)
        await db_session.flush()
        db_session.add(Entity(
            org_id=org.id, data_source_id=ds.id, name="customer",
            business_name="Customer", grain="One row per customer.",
            description="A person who placed orders.",
            primary_object="customers", source="inferred"))
        await db_session.commit()

        ctx = await load_context(db_session, ds.id, org.id)
        assert [e.name for e in ctx.entities] == ["customer"]
        assert ctx.entities[0].grain == "One row per customer."
