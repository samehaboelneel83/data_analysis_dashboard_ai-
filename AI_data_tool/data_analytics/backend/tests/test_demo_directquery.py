"""Tests for the DirectQuery demo: a SQLite source, a fifth dataset in
`mode="directquery"`, and a small report over it.

The load-bearing test in this file is
`test_the_city_widget_totals_every_group_not_just_the_visible_page`. Everything the
DirectQuery path was recently repaired around comes down to one invariant: a
displayed total is either true for the whole table, or it is absent — never the sum
of the fetched page or of a random sample. A demo that violates it is worse than no
demo, so the seeded data is built so that the invariant is *testable*: 24 cities
against a widget limit of 8, and 12,000 rows against a 10,000-row fetch cap, so both
truncations genuinely bite. A total that merely summed what came back would be
visibly, provably wrong here.

Three recent fixes are pinned alongside it, because the demo is where they would rot
unnoticed:
  * NULL dimension rows are excluded from rendering AND from the total (the frame
    deliberately carries NULL cities with real money attached, so a total that kept
    them differs from the right answer by a measurable amount);
  * tied groups come back in a deterministic order, ties broken by the dimension
    ascending (the priority column is built with an exact tie in it);
  * `limit` is pushed into SQL, so the fetched page is the top N *groups*.

Every query here goes through `run_direct_query` — the same call
`routers/widget_data.py` makes, with the source config assembled exactly the way that
router assembles it — never through a hand-built engine.
"""
import re
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.models import DataSource, Dataset, DatasetColumn, Report, ReportPage, ReportWidget
from app.services.analytics import detect_types
from app.services.demo_content import (
    DEMO_DIRECTQUERY_DATASET_NAME,
    DEMO_DIRECTQUERY_REPORT_NAME,
    DEMO_DIRECTQUERY_SOURCE_NAME,
    DEMO_DIRECTQUERY_TABLE,
    DEMO_DQ_CITY_WIDGET_TITLE,
    DEMO_DQ_PRIORITY_WIDGET_TITLE,
    DEMO_DQ_TABLE_WIDGET_TITLE,
    DEMO_MARKER,
    DEMO_META_KEY,
    build_demo_directquery_frame,
    demo_directquery_sqlite_path,
    is_demo_data_source,
    is_demo_dataset,
    is_demo_report,
    seed_demo_datasets,
    seed_demo_directquery,
)
from app.services.direct_query import DEFAULT_ROW_CAP, run_direct_query
from app.services.widget_data import clear_widget_data_cache, get_widget_data_from_df


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, tmp_path):
    """Point settings.upload_dir at a per-test temp dir, and remove it so the
    implementation has to create it rather than assume it exists."""
    from app.core.config import settings as app_settings

    target = tmp_path / "uploads"
    monkeypatch.setattr(app_settings, "upload_dir", str(target))
    assert not target.exists()
    return target


@pytest.fixture(autouse=True)
def _clear_cache():
    # The DirectQuery cache key includes data_source_id (a small per-test
    # autoincrement int) and source_table (the same string in every test here), so
    # without clearing, one test's entry can answer another test's query.
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


def _source_cfg(source: DataSource) -> dict:
    """Exactly what routers/widget_data.py assembles before calling run_direct_query:
    the stored config, plus `type` off the column. Building it any other way here
    would test a connection shape the app never uses."""
    cfg = dict(source.config or {})
    cfg["type"] = source.type
    return cfg


async def _loaded_dataset(db_session, dataset_id: int) -> Dataset:
    """DirectQuery validates every column against dataset.columns, which is a lazy
    relationship — it has to be eager-loaded before the sync query path touches it."""
    result = await db_session.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    return result.scalar_one()


async def _widgets(db_session, report_id: int) -> list[ReportWidget]:
    result = await db_session.execute(
        select(ReportWidget)
        .join(ReportPage, ReportWidget.page_id == ReportPage.id)
        .where(ReportPage.report_id == report_id)
    )
    return list(result.scalars().all())


def _by_title(widgets: list[ReportWidget], title: str) -> ReportWidget:
    matches = [w for w in widgets if w.title == title]
    assert len(matches) == 1, f"{len(matches)} widgets titled {title!r}"
    return matches[0]


async def _run_widget(db_session, seeded: dict, widget: ReportWidget) -> dict:
    dataset = await _loaded_dataset(db_session, seeded["dataset"].id)
    return run_direct_query(
        _source_cfg(seeded["source"]), dataset, widget.config,
        widget_type=widget.widget_type, cache_ttl_seconds=0,
    )


async def _seed(db_session, org_id) -> dict:
    return await seed_demo_directquery(db_session, org_id)


# ── The data the demo needs in order to prove anything ────────────────────────

def test_the_frame_is_deterministic():
    a, b = build_demo_directquery_frame(), build_demo_directquery_frame()

    assert a.equals(b)


def test_the_frame_is_shaped_so_that_the_truncations_actually_bite():
    """A guard on the fixture data, not on the code.

    If the table had fewer groups than the widget's limit, or fewer rows than the
    fetch cap, the totals tests below would pass against an implementation that
    simply summed the rows it was handed — proving nothing at all.
    """
    frame = build_demo_directquery_frame()

    assert frame["city"].nunique() >= 24
    assert len(frame) > DEFAULT_ROW_CAP, "the table widget would never sample"
    # NULL dimension values with real money attached: a total that failed to exclude
    # them differs from the right answer by this much, rather than by nothing.
    null_city = frame[frame["city"].isna()]
    assert len(null_city) > 0
    assert null_city["amount"].sum() > 0
    # An exact tie, so the deterministic tie-break has something to be deterministic
    # about.
    counts = frame.groupby("priority").size().sort_values(ascending=False)
    assert len(counts) >= 3
    assert (counts.value_counts() > 1).any(), "no two priorities have equal counts"


# ── The rows the seeder writes ────────────────────────────────────────────────

async def test_seed_creates_a_directquery_dataset_over_a_sqlite_data_source(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    seeded = await _seed(db_session, org_id)

    source, dataset = seeded["source"], seeded["dataset"]
    assert source.type == "sqlite"
    assert source.org_id == org_id
    assert dataset.mode == "directquery"
    assert dataset.data_source_id == source.id
    assert dataset.source_table == DEMO_DIRECTQUERY_TABLE
    assert dataset.org_id == org_id
    assert dataset.name == DEMO_DIRECTQUERY_DATASET_NAME
    assert source.name == DEMO_DIRECTQUERY_SOURCE_NAME
    # No file behind it: DirectQuery datasets carry no upload.
    assert dataset.filename is None


async def test_the_sqlite_file_sits_beside_the_demo_csvs_and_holds_the_frame(db_session, two_orgs, upload_dir):
    org_id = two_orgs["a"]["org"].id

    seeded = await _seed(db_session, org_id)

    path = Path(seeded["source"].config["filepath"])
    assert path == demo_directquery_sqlite_path(org_id)
    assert path.parent == upload_dir
    assert path.exists()
    conn = sqlite3.connect(str(path))
    try:
        count = conn.execute(f'SELECT COUNT(*) FROM "{DEMO_DIRECTQUERY_TABLE}"').fetchone()[0]
    finally:
        conn.close()
    assert count == len(build_demo_directquery_frame())


async def test_the_data_source_is_tagged_with_the_demo_marker(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    seeded = await _seed(db_session, org_id)

    assert (seeded["source"].config or {}).get(DEMO_META_KEY) == DEMO_MARKER
    assert is_demo_data_source(seeded["source"])
    assert is_demo_dataset(seeded["dataset"])
    assert is_demo_data_source(DataSource(name="x", type="sqlite", config={"filepath": "x"})) is False


async def test_dataset_columns_are_probed_the_way_a_real_directquery_import_probes_them(db_session, two_orgs):
    """DirectQuery validates every column it interpolates against DatasetColumn rows,
    so a missing one is not a cosmetic gap — the widget raises instead of drawing."""
    org_id = two_orgs["a"]["org"].id

    seeded = await _seed(db_session, org_id)

    result = await db_session.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == seeded["dataset"].id)
    )
    columns = {c.name: c.dtype for c in result.scalars().all()}
    frame = build_demo_directquery_frame()
    assert set(columns) == set(frame.columns)
    assert seeded["dataset"].col_count == len(frame.columns)
    # Types come from the app's own detection over a probe of the source, not from a
    # hand-written map — the same route routers/data_sources.py takes.
    assert columns["amount"] == detect_types(frame.head(50))["amount"]
    assert all(dtype != "unknown" for dtype in columns.values()), columns


async def test_the_report_is_bound_to_the_directquery_dataset_and_marked(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    seeded = await _seed(db_session, org_id)

    report = seeded["report"]
    assert report.name == DEMO_DIRECTQUERY_REPORT_NAME
    assert report.org_id == org_id
    assert report.dataset_id == seeded["dataset"].id
    widgets = await _widgets(db_session, report.id)
    assert len(widgets) >= 4
    for w in widgets:
        assert (w.config or {}).get(DEMO_META_KEY) == DEMO_MARKER, w.title
        assert (w.title or "").strip(), w.widget_type


# ── The query path ────────────────────────────────────────────────────────────

async def test_every_data_widget_returns_data_through_the_real_directquery_path(db_session, two_orgs):
    """Every widget on the report is pushed through `run_direct_query` — the same call
    the HTTP endpoint makes. A config the pushdown planner rejects raises
    DirectQueryUnsupported here rather than rendering an error tile in the browser."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)

    checked = 0
    for widget in await _widgets(db_session, seeded["report"].id):
        if widget.widget_type in {"text", "button", "shape", "image"}:
            continue
        result = await _run_widget(db_session, seeded, widget)
        assert result.get("type") in {"series", "table"}, (widget.title, result.get("type"))
        rows = result.get("rows") or []
        assert rows, f"{widget.title!r} returned no rows"
        if result["type"] == "series":
            for r in rows:
                assert r.get("name") is not None and r.get("value") is not None, (widget.title, r)
        checked += 1

    assert checked >= 4


# ── The totals invariant ──────────────────────────────────────────────────────

async def test_the_city_widget_totals_every_group_not_just_the_visible_page(db_session, two_orgs):
    """THE invariant. `limit` is pushed into SQL, so the shaper only ever sees the top
    N groups; the displayed total must still be measured over all 24."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    widget = _by_title(await _widgets(db_session, seeded["report"].id), DEMO_DQ_CITY_WIDGET_TITLE)

    result = await _run_widget(db_session, seeded, widget)

    frame = build_demo_directquery_frame()
    per_city = frame.groupby("city")["amount"].sum()  # pandas drops the NULL key
    limit = widget.config["limit"]
    assert len(result["rows"]) == limit
    assert len(per_city) > limit, "the limit did not truncate — this proves nothing"

    visible = sum(r["value"] for r in result["rows"])
    total = result["totals"][1]
    assert result["totals"][0] is None, "the dimension column carries the Total label"
    assert total == pytest.approx(per_city.sum(), rel=1e-9), "the total is not the table's"
    # Every value is positive, so the page is a strict subset and its sum is strictly
    # smaller: a page-sum masquerading as a total cannot coincidentally be right.
    assert visible < total * 0.999


async def test_the_city_total_excludes_null_dimension_rows(db_session, two_orgs):
    """NULL dimension rows are dropped by pandas' groupby, so DirectQuery excludes them
    from both the rows and the total. The frame carries NULL cities with real money
    attached, so a total that kept them is a different number, not the same one."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    widget = _by_title(await _widgets(db_session, seeded["report"].id), DEMO_DQ_CITY_WIDGET_TITLE)

    result = await _run_widget(db_session, seeded, widget)

    frame = build_demo_directquery_frame()
    assert all(r["name"] is not None for r in result["rows"]), "a nameless group was rendered"
    total = result["totals"][1]
    assert total == pytest.approx(frame.groupby("city")["amount"].sum().sum(), rel=1e-9)
    assert total < frame["amount"].sum() * 0.999, (
        "the total includes the NULL-city rows, which nothing renders"
    )


async def test_the_count_widget_totals_every_group_not_just_the_visible_page(db_session, two_orgs):
    """The no-measure path is a different implementation (`_run_count_series`, which
    builds its rows itself instead of routing them through the shaper), so it needs
    the invariant asserted separately."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    widget = _by_title(await _widgets(db_session, seeded["report"].id), DEMO_DQ_PRIORITY_WIDGET_TITLE)

    result = await _run_widget(db_session, seeded, widget)

    frame = build_demo_directquery_frame()
    counts = frame.groupby("priority").size()
    limit = widget.config["limit"]
    assert len(result["rows"]) == limit
    assert len(counts) > limit, "the limit did not truncate — this proves nothing"

    visible = sum(r["value"] for r in result["rows"])
    total = result["totals"][1]
    assert total == int(counts.sum())
    assert visible < total


async def test_tied_groups_come_back_in_a_deterministic_order(db_session, two_orgs):
    """Equal values leave SQL free to return either order. The pushdown breaks ties by
    the dimension ascending, matching shape_series, so the demo cannot draw one order
    on one engine and another elsewhere."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    widget = _by_title(await _widgets(db_session, seeded["report"].id), DEMO_DQ_PRIORITY_WIDGET_TITLE)

    result = await _run_widget(db_session, seeded, widget)

    rows = result["rows"]
    tied = [(r["name"], r["value"]) for r in rows]
    ties = [(a, b) for a, b in zip(tied, tied[1:]) if a[1] == b[1]]
    assert ties, "no tie in the fetched page — the ordering rule is untested"
    for (name_a, _), (name_b, _) in ties:
        assert name_a < name_b, f"tied groups came back as {name_a!r}, {name_b!r}"


async def test_the_row_capped_table_totals_the_table_not_the_sample(db_session, two_orgs):
    """The table widget fetches at most DEFAULT_ROW_CAP rows and randomly samples above
    it. Its column totals must still describe all 12,000 rows, sitting under a truthful
    "Showing 10,000 of 12,000"."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    widget = _by_title(await _widgets(db_session, seeded["report"].id), DEMO_DQ_TABLE_WIDGET_TITLE)

    result = await _run_widget(db_session, seeded, widget)

    frame = build_demo_directquery_frame()
    assert result["sampled"] is True, "the demo table is not big enough to sample"
    assert result["sample_size"] == DEFAULT_ROW_CAP
    assert result["total_rows"] == len(frame)
    assert result["total"] == len(frame)

    columns = result["columns"]
    totals = dict(zip(columns, result["totals"]))
    assert totals["amount"] == pytest.approx(frame["amount"].sum(), rel=1e-9)
    assert totals["quantity"] == frame["quantity"].sum()
    # A non-numeric column has no sum in either engine.
    assert totals["city"] is None


async def test_the_pushdown_agrees_with_import_mode_row_for_row(db_session, two_orgs):
    """The strongest available statement of correctness: the same config over the same
    data must produce the same rows, in the same order, whichever engine runs it."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    frame = build_demo_directquery_frame()

    for widget in await _widgets(db_session, seeded["report"].id):
        if widget.widget_type in {"text", "button", "shape", "image", "table"}:
            continue
        pushed = await _run_widget(db_session, seeded, widget)
        local = get_widget_data_from_df(frame.copy(), widget.config, widget.widget_type)

        assert [r["name"] for r in pushed["rows"]] == [r["name"] for r in local["rows"]], widget.title
        for a, b in zip(pushed["rows"], local["rows"]):
            assert a["value"] == pytest.approx(b["value"], rel=1e-9), (widget.title, a, b)
        if "totals" in local:
            assert pushed["totals"][1] == pytest.approx(local["totals"][1], rel=1e-9), widget.title


# ── Re-seeding ────────────────────────────────────────────────────────────────

async def _counts(db_session, org_id) -> tuple[int, int, int]:
    sources = (await db_session.execute(
        select(func.count(DataSource.id)).where(DataSource.org_id == org_id)
    )).scalar_one()
    datasets = (await db_session.execute(
        select(func.count(Dataset.id)).where(Dataset.org_id == org_id, Dataset.mode == "directquery")
    )).scalar_one()
    reports = (await db_session.execute(
        select(func.count(Report.id)).where(Report.org_id == org_id)
    )).scalar_one()
    return sources, datasets, reports


async def test_seeding_twice_leaves_one_source_one_dataset_and_one_report(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id

    await _seed(db_session, org_id)
    await _seed(db_session, org_id)

    assert await _counts(db_session, org_id) == (1, 1, 1)


async def test_reseeding_keeps_the_sqlite_file_usable(db_session, two_orgs):
    """The re-seed deletes the SQLite file the old DataSource pointed at. Any pooled
    connection still holding that file has to be disposed first — otherwise the unlink
    fails outright on Windows, and on POSIX the pool goes on serving the deleted
    inode, so the demo silently queries a file nobody can see."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    widget = _by_title(await _widgets(db_session, seeded["report"].id), DEMO_DQ_CITY_WIDGET_TITLE)
    before = await _run_widget(db_session, seeded, widget)

    reseeded = await _seed(db_session, org_id)  # must not raise

    path = Path(reseeded["source"].config["filepath"])
    assert path.exists()
    widget = _by_title(await _widgets(db_session, reseeded["report"].id), DEMO_DQ_CITY_WIDGET_TITLE)
    after = await _run_widget(db_session, reseeded, widget)
    assert after["rows"] == before["rows"]
    assert after["totals"] == before["totals"]


async def test_reseeding_does_not_delete_a_users_own_data_source_of_the_same_name(db_session, two_orgs):
    """Cleanup matches the marker, never the name. An implementation that deletes by
    name passes every other test in this file and destroys a user's connection."""
    org_id = two_orgs["a"]["org"].id
    await _seed(db_session, org_id)
    mine = DataSource(
        name=DEMO_DIRECTQUERY_SOURCE_NAME,           # the same name as the demo's
        type="sqlite",
        config={"filepath": "C:/somewhere/mine.db"},  # ...but no demo marker
        org_id=org_id,
    )
    db_session.add(mine)
    await db_session.commit()
    mine_id = mine.id

    await _seed(db_session, org_id)

    survivor = await db_session.get(DataSource, mine_id)
    assert survivor is not None, "a user's own data source was deleted by the re-seed"
    assert survivor.config == {"filepath": "C:/somewhere/mine.db"}


async def test_reseeding_does_not_delete_a_users_own_report_over_the_demo_dataset(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    mine = Report(name=DEMO_DIRECTQUERY_REPORT_NAME, dataset_id=seeded["dataset"].id, org_id=org_id)
    db_session.add(mine)
    await db_session.commit()
    mine_id = mine.id

    await _seed(db_session, org_id)

    assert await db_session.get(Report, mine_id) is not None, "a user's own report was deleted"


async def test_each_org_gets_its_own_sqlite_file_and_data_source(db_session, two_orgs):
    """Two orgs must not share the file: one org re-seeding unlinks it, which would
    empty the other org's demo underneath it."""
    a = await _seed(db_session, two_orgs["a"]["org"].id)
    b = await _seed(db_session, two_orgs["b"]["org"].id)

    assert a["source"].config["filepath"] != b["source"].config["filepath"]
    assert a["source"].id != b["source"].id


async def test_reseeding_one_org_leaves_another_orgs_directquery_demo_alone(db_session, two_orgs):
    org_a, org_b = two_orgs["a"]["org"].id, two_orgs["b"]["org"].id
    await _seed(db_session, org_a)
    b = await _seed(db_session, org_b)
    b_source_id, b_dataset_id = b["source"].id, b["dataset"].id

    await _seed(db_session, org_a)

    assert await db_session.get(DataSource, b_source_id) is not None
    assert await db_session.get(Dataset, b_dataset_id) is not None
    assert Path(b["source"].config["filepath"]).exists(), "another org's SQLite file was deleted"
    assert await _counts(db_session, org_b) == (1, 1, 1)


async def test_reseeding_the_whole_demo_leaves_no_orphaned_data_source(db_session, two_orgs):
    """The endpoint seeds the import datasets first, and `seed_demo_datasets` removes
    every demo dataset in the org — the DirectQuery one included. Its DataSource and
    SQLite file must go with it rather than accumulating one per re-seed."""
    org_id = two_orgs["a"]["org"].id

    for _ in range(2):
        await seed_demo_datasets(db_session, org_id)
        await seed_demo_directquery(db_session, org_id)

    sources = (await db_session.execute(
        select(DataSource).where(DataSource.org_id == org_id)
    )).scalars().all()
    datasets = (await db_session.execute(
        select(Dataset).where(Dataset.org_id == org_id)
    )).scalars().all()
    assert len(sources) == 1
    assert len(datasets) == 6  # the five import frames + the DirectQuery one
    assert len([d for d in datasets if d.mode == "directquery"]) == 1


async def test_the_seeder_does_not_commit(db_session, two_orgs):
    """The endpoint owns one transaction across every seeder, so a later failure rolls
    the DirectQuery content back with the rest."""
    org_id = two_orgs["a"]["org"].id

    await _seed(db_session, org_id)
    await db_session.rollback()

    assert await _counts(db_session, org_id) == (0, 0, 0)


async def test_the_seeded_report_is_recognised_by_the_shared_demo_predicates(db_session, two_orgs):
    """`is_demo_report` / `is_demo_dataset` are what a future "remove demo content"
    action will use. The DirectQuery content has to answer to them too."""
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)

    report = (await db_session.execute(
        select(Report)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
        .where(Report.id == seeded["report"].id)
    )).scalars().unique().one()

    assert is_demo_report(report)


# ── The renderer contract ─────────────────────────────────────────────────────

# Only one branch of WidgetRenderer.tsx draws `data.totals`. A widget outside it can
# ask for totals, receive a correct one from the backend, and show nothing — the exact
# shape of the two config-contract bugs this plan has already turned up (the Card
# reading `roles.measures`, the dual-axis charts ignoring `dimension_granularity`).
_RENDERER_TSX = (
    # The widget-type dispatch lives in WidgetBody.tsx since it was extracted from
    # WidgetRenderer.tsx; reading the old file found no branches at all.
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "report" / "WidgetBody.tsx"
)


def _widget_types_whose_renderer_draws_totals() -> set[str]:
    """The widget types in the one WidgetRenderer branch that renders `data.totals`.

    Read out of the renderer rather than copied from it, so that moving the totals row
    to a different widget type fails this test instead of silently making the demo's
    Total rows invisible.

    The totals row lives in the extracted `WindowedTable` component, not inline in the
    dispatch branch, so we resolve one level of indirection: a branch draws totals if
    its region renders `data.totals` directly OR renders a component whose own definition
    does. Each branch's region is capped at the first top-level helper definition after it,
    so a component defined below the dispatch (like WindowedTable) is not misattributed to
    the last branch.
    """
    src = _RENDERER_TSX.read_text(encoding="utf-8")

    # Top-level component definitions (capitalised names), and which of them draw totals.
    defs = [(m.start(), m.group(1))
            for m in re.finditer(r"\n(?:export\s+)?(?:function|const)\s+([A-Z]\w*)", src)]
    def_starts = [pos for pos, _ in defs]
    totals_components = set()
    for i, (pos, name) in enumerate(defs):
        body_end = defs[i + 1][0] if i + 1 < len(defs) else len(src)
        if "data.totals" in src[pos:body_end]:
            totals_components.add(name)

    branches = list(re.finditer(r"if \((wt === '[a-z_]+'(?:\s*\|\|\s*wt === '[a-z_]+')*)\)", src))
    assert branches, f"could not find any widget-type branch in {_RENDERER_TSX}"
    drawing = []
    for i, match in enumerate(branches):
        next_branch = branches[i + 1].start() if i + 1 < len(branches) else len(src)
        next_def = next((d for d in def_starts if d > match.end()), len(src))
        region = src[match.end():min(next_branch, next_def)]
        if "data.totals" in region or any(f"<{c}" in region for c in totals_components):
            drawing.append(set(re.findall(r"'([a-z_]+)'", match.group(1))))
    assert len(drawing) == 1, f"{len(drawing)} branches render data.totals: {drawing}"
    return drawing[0]


def test_the_renderer_parser_really_reads_the_renderer():
    """Guard the parser, not the demo: a regex that stopped matching would return an
    empty set and let the test below pass over nothing."""
    types = _widget_types_whose_renderer_draws_totals()

    assert {"table", "crosstab"} <= types, sorted(types)
    assert "bar" not in types, "a bar chart does not draw a totals row"


async def test_every_widget_asking_for_totals_is_one_whose_renderer_draws_them(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    seeded = await _seed(db_session, org_id)
    drawn = _widget_types_whose_renderer_draws_totals()

    asking = [w for w in await _widgets(db_session, seeded["report"].id) if w.config.get("show_totals")]

    assert len(asking) >= 2, "the demo asks for no totals at all"
    for widget in asking:
        assert widget.widget_type in drawn, (
            f"{widget.title!r} is a {widget.widget_type}: the backend computes its total "
            f"and the renderer never draws it"
        )
