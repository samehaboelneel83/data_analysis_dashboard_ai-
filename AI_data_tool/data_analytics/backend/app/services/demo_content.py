"""Demo dataset frames for the "Load demo content" feature.

Four pandas DataFrames, each shaped for a specific cluster of widgets rather than
generic sample data. A frame that merely "looks like data" is not enough: a Gantt
needs ordered start/end dates, a correlation matrix needs columns that actually
correlate (and columns that deliberately don't), a waterfall/diverging chart needs
negative values to show a band crossing zero. Get the shape wrong and the demo
report renders a grid of empty or meaningless widgets even though every field
technically has a value.

Everything is drawn from a single seeded Generator (`numpy.random.default_rng`)
so the whole demo — datasets, reports, calculated columns downstream — is
byte-for-byte reproducible across runs.

`build_demo_frames` is pure data generation; `seed_demo_datasets` persists those
frames as real Dataset rows, via a CSV round trip through the same loader and
type detection a user upload goes through; `seed_demo_reports` builds the reports
that chart them; `seed_demo_features` then layers the app's own features over both.

THREE seeders, called in that order — the third is not optional. It takes what the
first two returned and is where the calculated column, the measure, the column
formats, the display rules, the table chrome and every interaction artefact live.
Skip it and the demo still loads: four datasets, four reports, every widget drawing.
It just stops demonstrating anything the app does beyond picking a chart type.

No seeder commits — the caller owns one transaction across all three, so a failure
while building reports rolls the datasets back with it rather than leaving someone
who clicked "Load demo content" holding four datasets and no reports.

DEMO_MARKER tags anything the loader creates (org name, dataset name, ...) so a
future "remove demo content" action can find it unambiguously without guessing
at naming conventions.
"""
from __future__ import annotations

import base64
import copy
import math
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from ..core.config import settings
from ..models.models import (
    Bookmark, DataSource, Dataset, DatasetColumn, HierarchyNode, Report, ReportPage,
    ReportWidget,
)
from .analytics import detect_types, load_file
from .frame_cache import write_parquet_sidecar
from .connections import preview_table
from .engines import dispose_engine

DEMO_MARKER = "__demo__"

_SEED = 20260822

_REGIONS: dict[str, list[str]] = {
    "North America": ["United States", "Canada", "Mexico"],
    "Europe": ["United Kingdom", "Germany", "France", "Spain"],
    "Asia Pacific": ["Japan", "Australia", "India", "Singapore"],
    "Latin America": ["Brazil", "Argentina", "Chile"],
}

_PRODUCTS: dict[str, str] = {
    "Aurora Suite": "Software",
    "Aurora Suite Pro": "Software",
    "Beacon Analytics": "Software",
    "Beacon Analytics Lite": "Software",
    "Comet Hardware Kit": "Hardware",
    "Comet Sensor Pack": "Hardware",
    "Drift Support Plan": "Services",
    "Drift Onboarding Package": "Services",
    "Ember Training Course": "Services",
    "Flux Connector": "Hardware",
}

_CHANNELS = ["Online", "Retail", "Wholesale", "Partner"]

_GROUPS = ["A", "B", "C", "D"]

# 2025 revenue runs this much above 2024. See _sales_frame.
_YOY_GROWTH = 1.18

_PHASES = ["Planning", "Design", "Development", "Testing", "Deployment"]

_OWNERS = [
    "Ava Chen", "Liam Patel", "Noor Haddad", "Maria Silva", "Tom Becker",
    "Priya Nair", "Jonas Kim", "Elena Rossi", "Sam Okafor", "Grace Lund",
]

_TASK_WORDS = [
    "Kickoff", "Requirements Review", "Wireframes", "API Design", "Data Migration",
    "Integration Testing", "User Acceptance Testing", "Rollout", "Retrospective",
    "Documentation", "Security Review", "Performance Tuning", "Beta Feedback",
    "Accessibility Audit", "Content Freeze", "Load Testing", "Training Materials",
    "Launch Readiness", "Post-Launch Support", "Backlog Grooming",
]

_SENTIMENTS = ["Positive", "Neutral", "Negative"]

_TOPICS = [
    "Performance", "Pricing", "Support", "Onboarding", "Reliability", "UI/UX",
    "Integrations", "Documentation",
]

_PHRASES: dict[str, list[str]] = {
    "Positive": [
        "The dashboard loads incredibly fast now.",
        "Support team resolved my issue within minutes.",
        "Onboarding was smooth and the tutorials were clear.",
        "Pricing feels fair for the value we get.",
        "Love how easy it is to build a new report.",
        "The new filters saved us hours every week.",
        "Reliability has been rock solid this quarter.",
        "The UI redesign makes everything easier to find.",
        "Integrations with our other tools just work.",
        "Documentation finally answers our questions directly.",
        "Our whole team switched over without any friction.",
        "Export to PDF is a small thing but so useful.",
    ],
    "Neutral": [
        "The dashboard does what it says on the tin.",
        "Support answered but it took a couple of days.",
        "Onboarding covered the basics, nothing more.",
        "Pricing is about what we expected going in.",
        "Reports look fine once you know where to click.",
        "Reliability seems average compared to our last tool.",
        "The UI takes some getting used to.",
        "Integrations work but the setup is a bit fiddly.",
        "Documentation exists but could use more examples.",
        "It does the job for our current use case.",
    ],
    "Negative": [
        "The dashboard was slow to load this week.",
        "Support took far too long to respond.",
        "Onboarding left several of us confused.",
        "Pricing jumped without much warning.",
        "Reliability has been shaky since the last update.",
        "The UI buries settings we use every day.",
        "Integrations kept dropping our connection.",
        "Documentation is out of date in several places.",
        "We hit the same bug three times this month.",
        "Reports timed out on our larger datasets.",
    ],
}


def _sales_frame(rng: np.random.Generator, n: int = 2000) -> pd.DataFrame:
    """24 consecutive months of transactions, with refunds and loss-making rows.

    `margin_pct` is derived from `revenue`/`cost`, never drawn on its own, so a
    later calculated-column demo that recomputes margin_pct from the same two
    columns lands on the same numbers.
    """
    months = pd.period_range("2024-01", periods=24, freq="M")
    month_starts = months.to_timestamp()

    # Guarantee every one of the 24 months is represented: the first 24 rows
    # cover them one-for-one, the rest are a random draw across all 24. Leaving
    # this to chance alone (2000 rows / 24 months) would almost always work but
    # is not a guarantee, and the demo must be exactly reproducible either way.
    month_idx = np.concatenate([np.arange(24), rng.integers(0, 24, size=n - 24)])
    rng.shuffle(month_idx)
    day_offset = rng.integers(0, 28, size=n)  # 1..28, safe across all months
    dates = month_starts[month_idx] + pd.to_timedelta(day_offset, unit="D")

    region_list = list(_REGIONS)
    regions = np.array(region_list)[rng.integers(0, len(region_list), size=n)]
    countries = np.array([rng.choice(_REGIONS[r]) for r in regions])

    product_list = list(_PRODUCTS)
    products = np.array(product_list)[rng.integers(0, len(product_list), size=n)]
    categories = np.array([_PRODUCTS[p] for p in products])

    channels = np.array(_CHANNELS)[rng.integers(0, len(_CHANNELS), size=n)]

    # ~3% of rows are refunds: negative revenue. Cost is always a positive
    # expense (return processing etc.), drawn from the same magnitude as a
    # normal sale so the frame stays internally consistent.
    is_refund = rng.random(n) < 0.03
    revenue_magnitude = rng.gamma(shape=6.0, scale=700.0, size=n)
    # Year-on-year growth. Without it the two years are statistically identical and
    # every "change" widget — the change chart above all — animates between two
    # frames that look the same, which is the one thing a change chart must not do.
    # Derived from month_idx (0-11 = 2024, 12-23 = 2025) rather than from a fresh
    # draw, so it consumes nothing from the shared generator and leaves every other
    # column's stream exactly where it was.
    revenue_magnitude = revenue_magnitude * np.where(month_idx < 12, 1.0, _YOY_GROWTH)
    revenue = np.where(is_refund, -revenue_magnitude, revenue_magnitude)

    # cost_ratio > 1 means cost exceeded revenue on that sale — a genuine loss,
    # which is what gives margin_pct a negative tail for ordinary (non-refund)
    # rows as well as refund rows.
    cost_ratio = rng.uniform(0.55, 1.15, size=n)
    cost = revenue_magnitude * cost_ratio

    margin_pct = np.where(revenue != 0, (revenue - cost) / revenue * 100, 0.0)

    units = rng.integers(1, 400, size=n)
    target = revenue_magnitude * rng.uniform(0.85, 1.15, size=n)

    return pd.DataFrame({
        "date": dates,
        # Pre-bucketed period columns, derived from `date` so they can never disagree
        # with it. shape_series applies `dimension_granularity` itself, but the dual-axis
        # and change shapers do NOT — shape_dual_series groups by the raw column and
        # shape_bubble_animated frames by the raw column, so pointed at `date` they
        # produce one point (or one animation frame) per calendar day. A monthly axis
        # and a per-year animation need the buckets to already exist as columns.
        "year": dates.year,
        "month": dates.strftime("%Y-%m"),
        "region": regions,
        "country": countries,
        "product": products,
        "category": categories,
        "channel": channels,
        "revenue": np.round(revenue, 2),
        "units": units,
        "cost": np.round(cost, 2),
        "margin_pct": np.round(margin_pct, 2),
        "target": np.round(target, 2),
    })


def _metrics_frame(rng: np.random.Generator, n: int = 200) -> pd.DataFrame:
    """Numeric pairs for scatter/bubble/correlation-matrix widgets.

    height/weight are built from a shared signal plus noise so they correlate
    strongly (r > 0.7); score_a/score_b are drawn independently so they don't
    (|r| < 0.3). A correlation matrix needs both a filled cell and an empty one
    to be worth looking at.
    """
    height = rng.normal(170.0, 10.0, size=n)
    weight = 70.0 + 0.8 * (height - 170.0) + rng.normal(0.0, 6.0, size=n)
    bmi = weight / ((height / 100.0) ** 2)

    score_a = rng.normal(70.0, 15.0, size=n)
    score_b = rng.normal(65.0, 18.0, size=n)

    group = np.array(_GROUPS)[rng.integers(0, len(_GROUPS), size=n)]

    return pd.DataFrame({
        "sample_id": np.arange(1, n + 1),
        "height": np.round(height, 1),
        "weight": np.round(weight, 1),
        "bmi": np.round(bmi, 1),
        "score_a": np.round(score_a, 1),
        "score_b": np.round(score_b, 1),
        "group": group,
    })


def _projects_frame(rng: np.random.Generator, n: int = 200) -> pd.DataFrame:
    """Tasks with start/end dates that always satisfy end > start, for the Gantt."""
    task_idx = rng.integers(0, len(_TASK_WORDS), size=n)
    tasks = [f"{_TASK_WORDS[i]} #{row + 1}" for row, i in enumerate(task_idx)]

    owners = np.array(_OWNERS)[rng.integers(0, len(_OWNERS), size=n)]
    phases = np.array(_PHASES)[rng.integers(0, len(_PHASES), size=n)]

    start_offset = rng.integers(0, 700, size=n)
    start_date = pd.Timestamp("2024-01-01") + pd.to_timedelta(start_offset, unit="D")
    # Duration is drawn from a strictly positive range, so end_date > start_date
    # holds for every row by construction rather than by chance.
    duration = rng.integers(5, 120, size=n)
    end_date = start_date + pd.to_timedelta(duration, unit="D")

    progress_pct = rng.integers(0, 101, size=n)

    return pd.DataFrame({
        "task": tasks,
        "owner": owners,
        "phase": phases,
        "start_date": start_date,
        "end_date": end_date,
        "progress_pct": progress_pct,
    })


def _feedback_frame(rng: np.random.Generator, n: int = 200) -> pd.DataFrame:
    """Free-text comments with varied vocabulary, for the word cloud widget."""
    sentiments = np.array(_SENTIMENTS)[rng.integers(0, len(_SENTIMENTS), size=n)]
    comments = [rng.choice(_PHRASES[s]) for s in sentiments]
    topics = np.array(_TOPICS)[rng.integers(0, len(_TOPICS), size=n)]

    return pd.DataFrame({
        "comment": comments,
        "sentiment": sentiments,
        "topic": topics,
    })


_ROUTE_CITIES = [
    # name, lat, lon, country -- real hubs, with countries named to MATCH the
    # frontend atlas so the layered map's region layer paints without holes
    ("New York", 40.71, -74.01, "United States"), ("London", 51.51, -0.13, "United Kingdom"),
    ("Tokyo", 35.68, 139.69, "Japan"), ("Sydney", -33.87, 151.21, "Australia"),
    ("Sao Paulo", -23.55, -46.63, "Brazil"), ("Dubai", 25.20, 55.27, "United Arab Emirates"),
    ("Singapore", 1.35, 103.82, "Singapore"), ("Frankfurt", 50.11, 8.68, "Germany"),
    ("Los Angeles", 34.05, -118.24, "United States"), ("Johannesburg", -26.20, 28.05, "South Africa"),
]


def _routes_frame(rng: np.random.Generator, n: int = 300) -> pd.DataFrame:
    """Shipping routes between real cities: origin/destination coordinates for the
    line map, dense origin points for the cluster map, and from/to city pairs for
    the network graph -- one frame serving all three link-shaped widgets."""
    oi = rng.integers(0, len(_ROUTE_CITIES), n)
    di = rng.integers(0, len(_ROUTE_CITIES), n)
    di = np.where(di == oi, (di + 1) % len(_ROUTE_CITIES), di)
    rows = {
        "from_city": [_ROUTE_CITIES[i][0] for i in oi],
        "origin_lat": [_ROUTE_CITIES[i][1] + float(rng.normal(0, 0.8)) for i in oi],
        "origin_lon": [_ROUTE_CITIES[i][2] + float(rng.normal(0, 0.8)) for i in oi],
        "to_city": [_ROUTE_CITIES[i][0] for i in di],
        "dest_lat": [_ROUTE_CITIES[i][1] for i in di],
        "dest_lon": [_ROUTE_CITIES[i][2] for i in di],
        "dest_country": [_ROUTE_CITIES[i][3] for i in di],
        "shipments": rng.integers(1, 40, n).astype(float),
    }
    return pd.DataFrame(rows)


def build_demo_frames() -> dict[str, pd.DataFrame]:
    """Build the four demo DataFrames from one seeded generator.

    Frames are generated in a fixed order (sales, metrics, projects, feedback)
    from a single `default_rng(20260822)` instance so the whole batch — not just
    each frame in isolation — is reproducible run to run.
    """
    rng = np.random.default_rng(_SEED)
    return {
        "sales": _sales_frame(rng),
        "metrics": _metrics_frame(rng),
        "projects": _projects_frame(rng),
        "feedback": _feedback_frame(rng),
        "routes": _routes_frame(rng),
    }


# ── Persistence ───────────────────────────────────────────────────────────────

# Reserved key inside Dataset.column_meta carrying DEMO_MARKER. column_meta is
# otherwise keyed by column name, and no column can be called this, so the marker
# cannot collide with a real per-column override. Cleanup matches on this key and
# never on the dataset name: a user is entitled to have their own dataset called
# "Demo — Sales", and a re-seed must not touch it.
DEMO_META_KEY = "__demo__"

# Display names, keyed by the frame keys from build_demo_frames(). Names are for
# humans only — nothing in the seed/cleanup logic keys off them.
DEMO_DATASET_NAMES: dict[str, str] = {
    "sales": "Demo — Sales",
    "metrics": "Demo — Metrics",
    "projects": "Demo — Projects",
    "feedback": "Demo — Feedback",
    "routes": "Demo — Routes",
}

DEMO_DATASET_DESCRIPTIONS: dict[str, str] = {
    "sales": "Two years of transactions across regions, products and channels, "
             "including refunds and loss-making rows.",
    "metrics": "Numeric samples with one strongly correlated pair and one "
               "uncorrelated pair, for scatter, bubble and correlation widgets.",
    "projects": "Project tasks with owners, phases and ordered start/end dates, "
                "for the Gantt and progress widgets.",
    "feedback": "Free-text customer comments tagged by sentiment and topic, for "
                "the word cloud and text widgets.",
    "routes": "Shipping routes between world cities with coordinates and volumes, "
              "for the line map, cluster map and network graph.",
}


def is_demo_dataset(dataset: Dataset) -> bool:
    """True if `dataset` was created by the demo loader.

    Identified by the marker in column_meta, never by name.
    """
    return (dataset.column_meta or {}).get(DEMO_META_KEY) == DEMO_MARKER


def _demo_csv_path(org_id: int, key: str) -> Path:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    # org_id in the filename keeps two orgs' demos from writing over each other,
    # which would otherwise make one org's re-seed corrupt another org's data.
    return upload_dir / f"demo_{org_id}_{key}.csv"


async def _remove_existing_demo_datasets(db: AsyncSession, org_id: int) -> None:
    """Delete this org's previously seeded demo datasets and their files.

    Scoped to `org_id` in the query, so a re-seed in one org cannot reach into
    another's. Filtering on the marker happens in Python rather than SQL because
    column_meta is a portable JSON column and the app runs on both SQLite and
    Postgres; the set of datasets in one org is small enough that this is cheap.
    """
    result = await db.execute(select(Dataset).where(Dataset.org_id == org_id))
    for ds in result.scalars().all():
        if not is_demo_dataset(ds):
            continue
        if ds.filename:
            Path(ds.filename).unlink(missing_ok=True)
        await db.delete(ds)  # cascades to DatasetColumn rows
    await db.flush()


async def seed_demo_datasets(db: AsyncSession, org_id: int) -> dict[str, Dataset]:
    """Persist the demo frames as real Dataset + DatasetColumn rows for one org.

    Each frame is written to a CSV under settings.upload_dir and then read back
    with the app's own loader before types are detected, so the demo goes through
    exactly the representation a user upload does — including the CSV round trip
    that turns dates into strings and hands them back to detect_types to re-infer.
    Anything the demo exercises is therefore something real data exercises too.

    Idempotent: any previously seeded demo datasets in this org are removed first,
    so seeding twice leaves one copy. Returns the created Datasets keyed by frame
    name.

    Does NOT commit — the caller owns the transaction, so a later failure while
    seeding reports rolls the datasets back too. The CSV writes are not
    transactional and a rollback therefore strands the files, which is the lesser
    harm deliberately chosen: an orphaned CSV is referenced by nothing, invisible to
    the user, and overwritten by the next seed, whereas committing here would leave
    someone who clicked "Load demo content" holding four datasets and no reports.
    """
    await _remove_existing_demo_datasets(db, org_id)

    created: dict[str, Dataset] = {}
    for key, frame in build_demo_frames().items():
        path = _demo_csv_path(org_id, key)
        frame.to_csv(path, index=False)
        write_parquet_sidecar(str(path))

        df = load_file(str(path))
        type_map = detect_types(df)

        ds = Dataset(
            name=DEMO_DATASET_NAMES[key],
            description=DEMO_DATASET_DESCRIPTIONS[key],
            filename=str(path),
            row_count=len(df),
            col_count=len(df.columns),
            file_size=path.stat().st_size,
            column_meta={DEMO_META_KEY: DEMO_MARKER},
            org_id=org_id,
        )
        db.add(ds)
        await db.flush()

        for col_name, dtype in type_map.items():
            db.add(DatasetColumn(
                dataset_id=ds.id, name=col_name, dtype=dtype,
                missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={},
            ))

        created[key] = ds

    await db.flush()
    return created


# ── Demo reports ──────────────────────────────────────────────────────────────

DEMO_REPORT_NAMES: dict[str, str] = {
    "sales_overview": "Demo — Sales Overview",
    "distributions": "Demo — Distributions",
    "time_and_change": "Demo — Time & Change",
    "projects_feedback": "Demo — Projects & Feedback",
    "maps": "Demo — World Sales Map",
    "models": "Demo — Models",
}

DEMO_REPORT_DESCRIPTIONS: dict[str, str] = {
    "sales_overview": "Every core visual over two years of sales: KPIs, comparisons, "
                      "tables, part-to-whole, and the canvas objects.",
    "distributions": "Distribution and relationship visuals over 200 numeric samples, "
                     "including a correlation matrix with one strong and one weak pair.",
    "time_and_change": "Two measures at a time across 24 months and two years: dual "
                       "axes, a comparison against target, and a change chart animating "
                       "2024 against 2025.",
    "projects_feedback": "A project schedule over 200 dated tasks, and what customers "
                         "talk about — the one report drawing on two datasets at once.",
    "models": "Build, diagnose, compare, save and score a model without leaving the canvas: "
              "a regression, a tree and a head-to-head on the same held-out rows, a saved "
              "model re-scoring by region, a logistic model and natural segments.",
    "maps": "Revenue by country three ways: shaded regions, centred points and sized bubbles — same data, same filters, no coordinate columns needed.",
}

GRID_COLUMNS = 12

# A tiny inline bar-chart mark, embedded as a base64 data URI rather than fetched
# from a host. An <img src="https://..."> in the demo shows a broken-image icon on
# an offline or firewalled deployment, which is exactly where a canned demo is most
# often opened, and a broken tile is indistinguishable from a mis-configured one.
_DEMO_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 120" role="img">'
    '<rect width="240" height="120" rx="10" fill="#141a2e"/>'
    '<rect x="28" y="70" width="26" height="30" rx="3" fill="#6c8fff"/>'
    '<rect x="66" y="52" width="26" height="48" rx="3" fill="#6c8fff"/>'
    '<rect x="104" y="34" width="26" height="66" rx="3" fill="#a78bfa"/>'
    '<rect x="142" y="58" width="26" height="42" rx="3" fill="#6c8fff"/>'
    '<rect x="180" y="24" width="26" height="76" rx="3" fill="#4ade80"/>'
    '<text x="28" y="24" fill="#e6ebff" font-family="sans-serif" font-size="15">datalytics demo</text>'
    '</svg>'
)
DEMO_IMAGE_DATA_URI = (
    "data:image/svg+xml;base64,"
    + base64.b64encode(_DEMO_LOGO_SVG.encode("utf-8")).decode("ascii")
)


class _GridPacker:
    """Lays widgets out left-to-right in rows of a fixed-column grid.

    Non-overlap is structural rather than checked afterwards: every widget in a row
    shares the row's `y` and occupies a disjoint x-span, and the next row starts at
    `y + (tallest widget in the row)`, so a row's band [y, y + row_h) contains all of
    its widgets and nothing else. The alternative is hand-placing three dozen
    rectangles, where one transposed coordinate renders two tiles on top of each
    other and the demo looks broken.
    """

    def __init__(self, columns: int = GRID_COLUMNS) -> None:
        self.columns = columns
        self._x = 0
        self._y = 0
        self._row_h = 0

    def place(self, w: int, h: int) -> dict[str, int]:
        if w > self.columns:
            raise ValueError(f"widget width {w} exceeds the {self.columns}-column grid")
        if self._x + w > self.columns:
            self._y += self._row_h
            self._x = 0
            self._row_h = 0
        rect = {"x": self._x, "y": self._y, "w": w, "h": h}
        self._x += w
        self._row_h = max(self._row_h, h)
        return rect


# Widget specs: (widget_type, title, w, h, config). Order is layout order — the
# packer wraps to a new row whenever the next widget would run past column 12.
#
# Config keys are NOT interchangeable between widget types, and a wrong one produces
# a widget that looks fully configured and draws nothing. Every key below was read
# off its consumer in app/services/widget_data.py:
#   * shape_series (bar/line/area/pie/donut/treemap/funnel/list/slicer/step/
#     dot_plot/needle/scatter/kpi/table/crosstab/matrix) reads `dimension`,
#     `dimension2` and `measure` DIRECTLY off config — not through resolve_roles.
#   * every other shaper goes through resolve_roles, whose legacy map is
#     dimension -> category, dimension2 -> category2, and measure/measure2/size/
#     color/group/start/end/target/direction under their own names.
#   * `measures` (correlation_matrix, parallel_coordinates) is read straight off
#     config; shape_card alone reads it out of `roles` — see the card widget below.


def _sales_overview_specs(datasets: dict[str, Dataset]) -> list[tuple[str, str, int, int, dict]]:
    return [
        # ── Row 1: the headline numbers ──
        # No dimension: shape_series falls through to its single-aggregate branch and
        # returns a scalar, which is what the KPI renderer reads (data.rows[0].value).
        ("kpi", "Total revenue", 3, 3,
         {"measure": "revenue", "aggregation": "sum"}),
        ("kpi", "Units sold", 3, 3,
         {"measure": "units", "aggregation": "sum"}),
        ("kpi", "Average margin %", 3, 3,
         {"measure": "margin_pct", "aggregation": "avg"}),
        # shape_card is the one shaper that reads `measures` out of resolve_roles
        # rather than off config, so the `roles` form is what actually produces rows.
        # The plain `measures` key is written alongside it because that is the form
        # WidgetConfigPanel seeds its multi-select from. See the task report.
        # h=5, not the KPIs' 3: this stacks one row per measure and three of them were
        # clipped at h=3. The packer starts row 2 below the tallest tile here, so the
        # extra height pushes the next row down rather than overlapping it.
        ("card", "Revenue, cost and units", 3, 5,
         {"measures": ["revenue", "cost", "units"],
          "roles": {"measures": ["revenue", "cost", "units"]},
          "aggregation": "sum"}),

        # ── Row 2: comparison ──
        ("bar", "Revenue by region", 6, 5,
         {"dimension": "region", "measure": "revenue", "aggregation": "sum",
          "limit": 10, "sort": "desc", "sort_by": "value"}),
        ("line", "Monthly revenue", 6, 5,
         {"dimension": "date", "dimension_granularity": "month", "measure": "revenue",
          "aggregation": "sum", "limit": 24, "sort": "asc", "sort_by": "name"}),

        # ── Row 3: trend and part-to-whole ──
        # 5 wide, giving the column to the pie beside it: pie labels render OUTSIDE the
        # arc and were clipped at 3. A trend line reads fine one column narrower.
        ("area", "Monthly units shipped", 5, 5,
         {"dimension": "date", "dimension_granularity": "month", "measure": "units",
          "aggregation": "sum", "limit": 24, "sort": "asc", "sort_by": "name"}),
        ("pie", "Revenue by category", 4, 5,
         {"dimension": "category", "measure": "revenue", "aggregation": "sum",
          "limit": 10, "sort": "desc", "sort_by": "value"}),
        ("donut", "Revenue by channel", 3, 5,
         {"dimension": "channel", "measure": "revenue", "aggregation": "sum",
          "limit": 10, "sort": "desc", "sort_by": "value"}),

        # ── Row 4: detail ──
        # Neither dimension nor measure: shape_series' raw-table branch, driven by
        # `columns`. That branch is what gives the table real per-transaction rows
        # (and the column-shaped result Task 5's value_map rule needs) rather than an
        # aggregated two-column series.
        ("table", "Largest transactions", 6, 6,
         {"columns": ["date", "region", "product", "channel", "revenue", "units", "margin_pct"],
          "limit": 100, "sort_col": "revenue", "sort": "desc"}),
        ("crosstab", "Revenue: region x category", 6, 6,
         {"dimension": "region", "dimension2": "category", "measure": "revenue",
          "aggregation": "sum"}),

        # ── Row 5: pivoted detail and selection ──
        ("matrix", "Units: product x channel", 6, 6,
         {"dimension": "product", "dimension2": "channel", "measure": "units",
          "aggregation": "sum"}),
        ("list", "Revenue by country", 3, 6,
         {"dimension": "country", "measure": "revenue", "aggregation": "sum",
          "limit": 14, "sort": "desc", "sort_by": "value"}),
        # No shaper is registered for `slicer`, so it falls back to shape_series: a
        # dimension with no measure gives one {name, value} row per distinct value,
        # which is exactly the checkbox list the slicer renders.
        ("slicer", "Region", 3, 6,
         {"dimension": "region", "limit": 10, "sort": "asc", "sort_by": "name"}),

        # ── Row 6: goal, flow, hierarchy ──
        # `target` is a role name in its own right in resolve_roles, NOT `measure2`.
        ("gauge", "Revenue against target", 4, 5,
         {"measure": "revenue", "target": "target", "aggregation": "sum"}),
        ("funnel", "Revenue by channel", 4, 5,
         {"dimension": "channel", "measure": "revenue", "aggregation": "sum",
          "limit": 10, "sort": "desc", "sort_by": "value"}),
        ("treemap", "Revenue by product", 4, 5,
         {"dimension": "product", "measure": "revenue", "aggregation": "sum",
          "limit": 10, "sort": "desc", "sort_by": "value"}),
        # ── Hierarchies: five layouts over one shaper ────────────────────────
        # Deliberately the SAME levels across the first four, so a reader can
        # see that the layouts differ while the numbers do not -- which is the
        # guarantee of driving all six from one shaper.
        ("tree", "Revenue by region and country", 4, 6,
         {"levels": ["region", "country"], "measure": "revenue",
          "aggregation": "sum"}),
        # sum, not avg: a sunburst draws each value as a share of its parent,
        # so a non-additive aggregation would make the geometry state something
        # the data does not. The shaper refuses it; the demo does not tempt it.
        ("sunburst", "Where revenue sits", 5, 5,
         {"levels": ["region", "country"], "measure": "revenue",
          "aggregation": "sum"}),
        ("icicle", "Revenue by level", 6, 4,
         {"levels": ["region", "country"], "measure": "revenue",
          "aggregation": "sum"}),
        # Two layers reading the SAME column two ways -- the case a chart
        # keyed by measure name collapses into one series, and the reason
        # Graph Builder exists rather than a fourth fixed combination.
        ("custom_graph", "Revenue totalled and averaged", 6, 5,
         {"dimension": "region", "layers": [
             {"mark": "bar", "measure": "revenue", "aggregation": "sum", "axis": "left"},
             {"mark": "line", "measure": "revenue", "aggregation": "avg", "axis": "right"}]}),
        # Same levels again, and the same reason for sum: a circle pack
        # nests each child inside its parent, so the parent's area is the
        # sum of what it contains.
        ("circle_pack", "Revenue nested by region", 5, 5,
         {"levels": ["region", "country"], "measure": "revenue",
          "aggregation": "sum"}),
        ("dendrogram", "Category structure", 6, 5,
         {"levels": ["category", "product"], "measure": "revenue",
          "aggregation": "sum"}),
        # The org chart shows the OTHER input mode: explicit parent-child
        # links, where the depth is data rather than schema. Levels could not
        # express a reporting line of unknown depth.
        ("org", "Product lines by category", 6, 5,
         {"levels": ["category", "product"], "measure": "revenue",
          "aggregation": "sum"}),

        # ── Row 7: two-dimensional grids ──
        # ribbon and heatmap share shape_heatmap: rows = dimension, columns =
        # dimension2, cell = measure. `dimension2` is required for both; without it
        # the shaper returns an empty result rather than degrading to a series.
        ("ribbon", "Category mix by region", 6, 6,
         {"dimension": "region", "dimension2": "category", "measure": "revenue",
          "aggregation": "sum"}),
        ("heatmap", "Revenue: region x channel", 6, 6,
         {"dimension": "region", "dimension2": "channel", "measure": "revenue",
          "aggregation": "sum"}),

        # ── Row 8: contribution and stepped trend ──
        ("waterfall", "Revenue build by region", 6, 5,
         {"dimension": "region", "measure": "revenue", "aggregation": "sum", "limit": 20}),
        ("step", "Quarterly cost", 6, 5,
         {"dimension": "date", "dimension_granularity": "quarter", "measure": "cost",
          "aggregation": "sum", "limit": 12, "sort": "asc", "sort_by": "name"}),

        # ── Row 9: ranked points ──
        ("dot_plot", "Average sale by country", 6, 5,
         {"dimension": "country", "measure": "revenue", "aggregation": "avg",
          "limit": 14, "sort": "desc", "sort_by": "value"}),
        # `baseline` is read by NeedlePlotRenderer, not by any shaper: it is where the
        # stems are drawn from. Zero is the meaningful baseline for a margin %, which
        # the sales frame deliberately drives negative on some rows.
        ("needle", "Average margin % by product", 6, 5,
         {"dimension": "product", "measure": "margin_pct", "aggregation": "avg",
          "limit": 10, "sort": "asc", "sort_by": "name", "baseline": 0}),

        # ── Row 10: opposed measures ──
        # butterfly goes through shape_dual_series: measure is the left wing,
        # measure2 the right. measure2 is a role of its own, so the config key is
        # literally "measure2".
        ("butterfly", "Revenue against target by region", 12, 5,
         {"dimension": "region", "measure": "revenue", "measure2": "target",
          "aggregation": "sum", "limit": 20}),

        # ── Row 11: canvas objects, which have no data of their own ──
        ("text", "About this report", 4, 4,
         {"content": "Demo — Sales Overview\n\n"
                     "Two years of transactions across 4 regions, 14 countries, 10 products "
                     "and 4 channels, including refunds (negative revenue) and loss-making "
                     "sales (negative margin).\n\n"
                     "Click a bar, slice or row to cross-filter the page."}),
        ("image", "Logo", 4, 4,
         {"url": DEMO_IMAGE_DATA_URI, "alt": "datalytics demo logo", "fit": "contain"}),
        ("shape", "Divider", 2, 4,
         {"shape": "rounded", "fill": "#1b2340", "stroke": "#6c8fff"}),
        # No `action` here: this report has a single page and no bookmarks yet. Task 5
        # of this plan owns interactions and wires this button to a target.
        ("button", "Explore", 2, 4,
         {"label": "Explore the data"}),
        ("web_content", "Live embed", 4, 4,
         {"url": "https://example.com/"}),
        ("custom_visual", "Custom visual", 4, 4,
         {"url": "/custom-visual-demo.html", "dimension": "region", "measure": "revenue", "aggregation": "sum"}),
        # A script tile: server-side Python over the widget's own secured
        # frame. Deliberately a plain aggregation -- a demo script is read by
        # people deciding whether to trust the feature, so it shows the shape
        # of the contract (`df` in, `result` out) and nothing clever.
        ("script", "Revenue by region (script)", 4, 4,
         {"code": "result = df.groupby('region', as_index=False)['revenue'].sum()"}),
    ]


def _distributions_specs(datasets: dict[str, Dataset]) -> list[tuple[str, str, int, int, dict]]:
    return [
        # ── Row 1 ──
        # shape_histogram reads `measure` and `bins` straight off config. It has no
        # dimension at all, and a `dimension` key here would simply be ignored.
        ("histogram", "BMI distribution", 6, 5,
         {"measure": "bmi", "bins": 20}),
        ("box_plot", "BMI by group", 6, 5,
         {"dimension": "group", "measure": "bmi", "limit": 10}),

        # ── Row 2 ──
        # scatter is registered to shape_series, whose rows are {name, value}, and
        # ScatterChartRenderer plots x = row.x ?? row.name on a type="number" axis.
        # So the dimension has to be a NUMERIC column: a categorical one would put
        # strings on a numeric axis and draw an empty plot area. height (150 distinct
        # values) against average weight is a genuine scatter.
        ("scatter", "Weight against height", 6, 5,
         {"dimension": "height", "measure": "weight", "aggregation": "avg",
          "limit": 250, "sort": "asc", "sort_by": "name"}),
        # numeric_series uses shape_xy_numeric: measure is X, measure2 is Y, and it is
        # row-level — no aggregation and no dimension.
        ("numeric_series", "Height against weight (raw points)", 6, 5,
         {"measure": "height", "measure2": "weight", "limit": 200}),

        # ── Row 3 ──
        # bubble: dimension is the grain (one bubble per value), measure/measure2 are
        # x/y, size is the radius, color an optional numeric and group an optional
        # categorical legend. shape_bubble returns empty when group == category, so
        # the grain is sample_id and `group` carries the legend.
        ("bubble", "Height, weight and BMI by sample", 6, 6,
         {"dimension": "sample_id", "measure": "height", "measure2": "weight",
          "size": "bmi", "color": "score_a", "group": "group",
          "aggregation": "avg", "limit": 200}),
        # `measures` is read straight off config by shape_correlation_matrix.
        # height/weight correlate strongly (r about .80) and score_a/score_b
        # deliberately do not (r about .01), so the matrix has a hot cell and a cold
        # one rather than a uniform wash.
        ("correlation_matrix", "Correlation between measures", 6, 6,
         {"measures": ["height", "weight", "bmi", "score_a", "score_b"]}),

        # ── Row 4 ──
        ("parallel_coordinates", "Samples across every measure", 7, 6,
         {"measures": ["height", "weight", "bmi", "score_a", "score_b"], "limit": 200}),
        # vector_plot: measure/measure2 position the arrow, size is its length and
        # `direction` is an angle in DEGREES (0 = east, counter-clockwise). The
        # metrics frame has no true bearing column, so score_a stands in as the angle
        # — it spreads over roughly 20-120 degrees, which fans the arrows visibly.
        ("vector_plot", "Sample field (angle from score A)", 5, 6,
         {"measure": "height", "measure2": "weight", "size": "bmi",
          "direction": "score_a", "limit": 200}),
    ]


def _time_and_change_specs(datasets: dict[str, Dataset]) -> list[tuple[str, str, int, int, dict]]:
    """Every widget here goes through shape_dual_series or shape_bubble_animated.

    Both resolve their columns through resolve_roles, so the config keys are the ROLE
    names, not shape_series' `dimension`/`measure` pair — with one trap in the middle:
    the role a widget declares in ROLE_SPECS decides which key WidgetConfigPanel writes.
    dual_axis_bar/line/bar_line declare `category`, which configKeyFor maps to
    `dimension`; the two time-series types declare `start`, which maps to itself. Both
    land on the same variable in shape_dual_series (`category or start`), so either key
    draws — but only the one its ROLE_SPEC declares survives a round trip through the
    config panel, which rewrites the widget from its role fields.
    """
    return [
        # ── Row 1: two measures over a dimension, one axis each ──
        ("dual_axis_bar", "Revenue and cost by region", 6, 5,
         {"dimension": "region", "measure": "revenue", "measure2": "cost",
          "aggregation": "sum", "limit": 10}),
        ("dual_axis_line", "Revenue and units by product", 6, 5,
         {"dimension": "product", "measure": "revenue", "measure2": "units",
          "aggregation": "sum", "limit": 10}),

        # ── Row 2: a magnitude against a rate, and the first time axis ──
        # avg, not sum: margin_pct is a rate, and summing 500 percentages produces a
        # number with no meaning that still draws a perfectly convincing line.
        ("dual_axis_bar_line", "Average sale and margin % by channel", 6, 5,
         {"dimension": "channel", "measure": "revenue", "measure2": "margin_pct",
          "aggregation": "avg", "limit": 10}),
        # `month` (a "YYYY-MM" column), never `date`: shape_dual_series has no
        # `dimension_granularity` handling, so grouping by the raw date column would
        # give one point per calendar day and `limit` would then cut the series down
        # to the first few weeks of 2024 — a plausible-looking chart of the wrong thing.
        ("dual_axis_time_series", "Revenue and cost by month", 6, 5,
         {"start": "month", "measure": "revenue", "measure2": "cost",
          "aggregation": "sum", "limit": 24}),

        # ── Row 3: comparison against a goal, and the change chart ──
        ("comparative_time_series", "Revenue against target by month", 6, 5,
         {"start": "month", "measure": "revenue", "measure2": "target",
          "aggregation": "sum", "limit": 24}),
        # `animation` is a role of its own — the frames the scrubber steps through.
        # `year` gives it the two points the sales frame is built to compare; a change
        # chart with one frame is a still picture with a play button on it.
        ("bubble_change", "Average sale by region: 2024 against 2025", 6, 6,
         {"dimension": "region", "measure": "revenue", "measure2": "cost",
          "size": "units", "color": "margin_pct", "animation": "year",
          "aggregation": "avg", "limit": 200}),
        ("forecast", "Revenue forecast (6 months)", 6, 5,
         {"dimension": "date", "dimension_granularity": "month", "measure": "revenue",
          "aggregation": "sum", "forecast_periods": 6}),
        ("sankey", "Channel to region flow", 6, 5,
         {"dimension": "channel", "dimension2": "region", "measure": "revenue",
          "limit": 30}),
        # An explicit first level rather than auto_split: the demo should
        # show the visual answering a question, not show off its guess.
        ("decomposition", "Revenue, broken down", 5, 6,
         {"roles": {"measure": "revenue"}, "aggregation": "sum",
          "split_by": "category"}),
        # One chart per region, on ONE shared scale -- which is the entire
        # reason to face a chart rather than draw three of them.
        ("small_multiples", "Category mix by region", 6, 5,
         {"facet_by": "region", "inner_widget_type": "bar",
          "dimension": "category", "measure": "revenue", "aggregation": "sum"}),

    ]


def _projects_feedback_specs(datasets: dict[str, Dataset]) -> list[tuple[str, str, int, int, dict]]:
    """The one demo report drawing on two datasets: projects for the Gantt, feedback
    for the word cloud, which carries a per-widget `dataset_id` override."""
    return [
        # shape_gantt roles: category (the bar label), start, end, group. `start`/`end`
        # are role names in their own right, so the config keys are literally "start"
        # and "end" — not "dimension2" or "measure". The renderer runs Date.parse over
        # both and silently drops every row it cannot parse, so a swapped pair does not
        # error: it draws bars of zero width.
        ("schedule", "Project schedule by phase", 7, 6,
         {"dimension": "task", "start": "start_date", "end": "end_date",
          "group": "phase", "limit": 40}),
        # word_cloud falls through to shape_series (dimension + no measure = one row per
        # distinct value, valued by frequency). The dimension has to be a WORD column:
        # WordCloudRenderer draws row.name verbatim, so `comment` would lay whole
        # sentences into the cloud, which d3-cloud mostly fails to place.
        # `dataset_id` overrides the report's dataset for this one widget — the report
        # lists it in additional_dataset_ids so the builder can resolve it.
        ("word_cloud", "What customers talk about", 5, 6,
         {"dataset_id": datasets["feedback"].id, "dimension": "topic",
          "aggregation": "count", "limit": 50, "sort": "desc", "sort_by": "value"}),
    ]


def _maps_specs(datasets: dict[str, Dataset]) -> list[tuple[str, str, int, int, dict]]:
    """The map family over sales.country. Region mode only: the demo frames carry no
    coordinate columns, and plotting countries at their centroids is exactly the
    capability that makes the point/bubble maps usable on such data."""
    return [
        ("map_choropleth", "Revenue by country", 12, 6,
         {"dimension": "country", "measure": "revenue", "aggregation": "sum",
          "limit": 50, "sort": "desc", "sort_by": "value"}),
        ("map_points", "Where we sell", 6, 5,
         {"dimension": "country", "measure": "revenue", "aggregation": "count",
          "limit": 50, "sort": "desc", "sort_by": "value"}),
        ("map_bubbles", "Units by country", 6, 5,
         {"dimension": "country", "measure": "units", "aggregation": "sum",
          "limit": 50, "sort": "desc", "sort_by": "value"}),
        # Routes carry real coordinates -- the two link-shaped maps read them via a
        # per-widget dataset_id override, like the word cloud does with feedback.
        ("map_lines", "Shipping routes", 6, 5,
         {"dataset_id": datasets["routes"].id,
          "roles": {"lat": "origin_lat", "lon": "origin_lon",
                    "lat2": "dest_lat", "lon2": "dest_lon",
                    "category": "to_city", "measure": "shipments"}, "limit": 120}),
        ("map_clusters", "Origin density", 6, 5,
         {"dataset_id": datasets["routes"].id,
          "roles": {"lat": "origin_lat", "lon": "origin_lon", "measure": "shipments"},
          "cluster_cell_degrees": 10}),
        ("network", "City shipping network", 6, 5,
         {"dataset_id": datasets["routes"].id,
          "dimension": "from_city", "dimension2": "to_city", "measure": "shipments",
          "centrality_metric": "betweenness"}),
        ("map_pie", "Category mix by country", 6, 5,
         {"dimension": "country", "dimension2": "category", "measure": "revenue",
          "limit": 10}),
        ("map_layers", "Destinations and origins", 6, 5,
         {"dataset_id": datasets["routes"].id,
          "roles": {"category": "dest_country", "measure": "shipments",
                    "lat": "origin_lat", "lon": "origin_lon"}}),
        ("map_network", "Routes as a network", 6, 5,
         {"dataset_id": datasets["routes"].id,
          "roles": {"category": "from_city", "category2": "to_city",
                    "lat": "origin_lat", "lon": "origin_lon",
                    "lat2": "dest_lat", "lon2": "dest_lon", "measure": "shipments"}}),
        ("map_density", "Origin heat grid", 6, 5,
         {"dataset_id": datasets["routes"].id,
          "roles": {"lat": "origin_lat", "lon": "origin_lon"},
          "cluster_cell_degrees": 8}),
        ("map_contour", "Where shipments concentrate", 6, 5,
         {"dataset_id": datasets["routes"].id,
          "roles": {"lat": "origin_lat", "lon": "origin_lon", "measure": "shipments"}}),
        # A tabs container with two KPI children. The children carry container_id
        # (patched in after ids exist -- see seed_demo_reports) and are skipped at
        # canvas level, so each renders exactly once, inside the container.
        ("container", "Totals (tabbed)", 6, 4, {"container_mode": "tabs"}),
        ("kpi", "Total revenue (tab)", 3, 3,
         {"measure": "revenue", "aggregation": "sum", "__container_child__": "Totals (tabbed)"}),
        ("kpi", "Total units (tab)", 3, 3,
         {"measure": "units", "aggregation": "sum", "__container_child__": "Totals (tabbed)"}),
    ]


#: The saved model the scoring widget applies. Its id only exists once the seed
#: has fitted and stored it, so the spec carries this marker and the seed swaps
#: in the real id (the same late-binding the container children use).
DEMO_MODEL_MARKER = "__demo_prediction_model__"
DEMO_MODEL_NAME = "Demo — Revenue model"


def _models_specs(datasets: dict[str, Dataset]) -> list[tuple[str, str, int, int, dict]]:
    """Build, diagnose, compare, save and score -- on the canvas (Part IV
    criterion 6). The data is synthetic, so two of the models are honestly
    close to guessing; each widget says so against its own baseline, which is
    the point of showing the baseline at all."""
    lin = {"measure": "revenue", "predictors": ["units", "cost", "channel"]}
    return [
        ("model_linear", "What drives revenue (linear regression)", 6, 6, lin),
        ("model_tree", "Revenue as a decision tree", 6, 6,
         {"response": "revenue", "predictors": ["units", "cost", "channel"], "max_depth": 3}),
        ("model_compare", "Which revenue model predicts best", 6, 6,
         {"compare": [{"model": "linear", "response": "revenue", "predictors": ["units", "cost", "channel"]},
                      {"model": "tree", "response": "revenue", "predictors": ["units", "cost", "channel"]}]}),
        ("model_score", "Predicted revenue by region (saved model)", 6, 6,
         {"prediction_model_id": DEMO_MODEL_MARKER, "dimension": "region"}),
        ("model_logistic", "Is it an online sale? (logistic)", 6, 6,
         {"response": "channel", "event_value": "Online", "predictors": ["units", "revenue", "region"]}),
        ("model_cluster", "Natural segments of sales", 6, 6,
         {"measures": ["revenue", "units", "cost"]}),
    ]


async def _seed_demo_model(db: AsyncSession, org_id: int, sales: Dataset) -> int:
    """Fit and store the model the scoring widget applies, exactly as the
    Models panel's "Train and save" would. Removed with its dataset on reseed."""
    import asyncio
    from ..models.models import PredictionModel
    from .analysis.model_store import fit_and_package
    from .widget_data import load_file

    def _fit():
        df = load_file(sales.filename)
        return fit_and_package(df, "revenue", ["units", "cost", "channel", "region"])

    pkg = await asyncio.to_thread(_fit)
    row = PredictionModel(
        org_id=org_id, dataset_id=sales.id, name=DEMO_MODEL_NAME,
        target=pkg.target, features=pkg.features, feature_columns=pkg.feature_columns,
        categories=pkg.categories, task=pkg.task, model_family=pkg.model_family,
        score=pkg.score, score_name=pkg.score_name, artifact=pkg.artifact,
    )
    db.add(row)
    await db.flush()
    return row.id


# (report key, primary dataset key, extra dataset keys, spec builder). Builders take
# the seeded datasets because a widget charting a second dataset needs its id, which
# only exists after the datasets are flushed.
_DEMO_REPORT_SPECS: list[tuple[str, str, list[str], Callable[[dict[str, Dataset]], list]]] = [
    ("sales_overview", "sales", [], _sales_overview_specs),
    ("distributions", "metrics", [], _distributions_specs),
    ("time_and_change", "sales", [], _time_and_change_specs),
    ("projects_feedback", "projects", ["feedback"], _projects_feedback_specs),
    ("maps", "sales", ["routes"], _maps_specs),
    ("models", "sales", [], _models_specs),
]


def is_demo_report(report: Report) -> bool:
    """True if `report` was created by the demo loader.

    Identified by the marker every seeded widget carries in its config, never by the
    report's name — a user is entitled to a report of their own called
    "Demo — Sales Overview" and a re-seed must not delete it. ReportWidget.config is
    the only free-form JSON on the report/page/widget trio, which is why the marker
    lives a level down from the row it identifies. The dunder-namespaced key cannot
    collide with a real config key and no shaper or renderer reads it.

    Requires `report.pages` and each page's `widgets` to be loaded;
    `_remove_existing_demo_reports` eager-loads both.
    """
    return any(
        (widget.config or {}).get(DEMO_META_KEY) == DEMO_MARKER
        for page in report.pages
        for widget in page.widgets
    )


async def _remove_existing_demo_reports(db: AsyncSession, org_id: int) -> None:
    """Delete this org's previously seeded demo reports.

    Scoped to `org_id` in the query so a re-seed in one org cannot reach into
    another's, and filtered on the marker in Python for the same reason
    `_remove_existing_demo_datasets` is: the marker lives in a portable JSON column
    and the app runs on both SQLite and Postgres.
    """
    result = await db.execute(
        select(Report)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
        .where(Report.org_id == org_id)
    )
    for report in result.scalars().unique().all():
        if is_demo_report(report):
            await db.delete(report)  # cascades to pages and widgets
    await db.flush()


async def seed_demo_reports(
    db: AsyncSession, org_id: int, datasets: dict[str, Dataset],
) -> list[Report]:
    """Build the demo reports over the datasets `seed_demo_datasets` returned.

    Idempotent: any previously seeded demo reports in this org are removed first, so
    seeding twice leaves one copy. Does NOT commit — the caller owns the transaction,
    matching `seed_demo_datasets`, so a failure part-way through leaves neither
    datasets nor reports behind.
    """
    await _remove_existing_demo_reports(db, org_id)
    demo_model_id = await _seed_demo_model(db, org_id, datasets["sales"])

    created: list[Report] = []
    for report_key, dataset_key, extra_keys, build_specs in _DEMO_REPORT_SPECS:
        dataset = datasets[dataset_key]
        report = Report(
            name=DEMO_REPORT_NAMES[report_key],
            description=DEMO_REPORT_DESCRIPTIONS[report_key],
            dataset_id=dataset.id,
            # Any dataset a widget on this report charts through a per-widget
            # `dataset_id` override has to be listed here too: ReportBuilder resolves
            # widget datasets out of dataset_id + additional_dataset_ids, so an
            # unlisted one leaves the widget pointing at nothing.
            additional_dataset_ids=[datasets[k].id for k in extra_keys],
            org_id=org_id,
        )
        db.add(report)
        await db.flush()

        page = ReportPage(
            report_id=report.id,
            name="Page 1",
            title=DEMO_REPORT_NAMES[report_key],
            position=0,
        )
        db.add(page)
        await db.flush()

        packer = _GridPacker()
        for widget_type, title, w, h, config in build_specs(datasets):
            if config.get("prediction_model_id") == DEMO_MODEL_MARKER:
                config = {**config, "prediction_model_id": demo_model_id}
            db.add(ReportWidget(
                page_id=page.id,
                widget_type=widget_type,
                title=title,
                config={**config, DEMO_META_KEY: DEMO_MARKER},
                layout=packer.place(w, h),
            ))

        await db.flush()
        created.append(report)

    await db.flush()

    # Resolve container children: a spec marks a child with the TITLE of its container
    # (ids do not exist until flush); this rewrites the marker into the container_id
    # reference the renderer actually reads.
    for report in created:
        result = await db.execute(
            select(ReportPage).options(selectinload(ReportPage.widgets))
            .where(ReportPage.report_id == report.id)
        )
        for page in result.scalars().all():
            by_title = {w.title: w for w in page.widgets}
            for w in page.widgets:
                marker = (w.config or {}).get("__container_child__")
                if marker and marker in by_title:
                    cfg = dict(w.config)
                    cfg.pop("__container_child__")
                    cfg["container_id"] = by_title[marker].id
                    w.config = cfg
                    flag_modified(w, "config")
    await db.flush()
    return created


# ── The feature layer ─────────────────────────────────────────────────────────
#
# Everything above builds datasets and the widgets that chart them. This section
# layers the app's OWN features over that content: a calculated column, a measure,
# column formats, all three kinds of display rule, table chrome, and the interaction
# artefacts (slicer, cross-filter, drill hierarchy, bookmark, navigation button).
#
# It runs as a third pass rather than being folded into the two seeders above,
# because it needs both of them to have finished: the hierarchy hangs off a Dataset
# that must already exist, and the widgets it patches are created by seed_demo_reports.
# See seed_demo_features.

_COLOUR_BELOW = "#f87171"   # red
_COLOUR_NEAR = "#fbbf24"    # amber
_COLOUR_AT = "#4ade80"      # green
_COLOUR_ACCENT = "#6c8fff"  # blue
_COLOUR_ALT = "#a78bfa"     # violet

# Row-level, evaluated by widget_data.apply_calculated_columns BEFORE any grouping.
# `profit` is deliberately built from the same two columns the sales frame derives
# margin_pct from, so recomputing margin from it lands back on margin_pct — a
# calculated column whose arithmetic can be checked against something already there.
DEMO_CALCULATED_COLUMNS: list[dict] = [
    {
        "name": "profit",
        "expression": "revenue - cost",
        "dtype": "numeric",
        # CalcColumnDef carries its own format; WidgetRenderer merges these over
        # Dataset.column_formats, so a calculated column never needs an entry there.
        "format": {"type": "currency", "symbol": "$", "decimals": 0},
    },
]

# Post-aggregation, evaluated by measure_eval at the REQUESTING WIDGET'S grain — a
# different engine from the one above, not a different flavour of it. Margin taken on
# a group's totals is not the mean of that group's row-level margins: refunds carry a
# negative revenue against a positive cost, which drags the ratio of the sums roughly
# eight points below the mean of the ratios. The demo shows both side by side on the
# detail page so the difference is visible rather than asserted.
#
# The name must not collide with a real or calculated column: shape_series resolves a
# column FIRST and only falls through to resolve_measure when the name matches none,
# so a colliding measure would silently never run. routers/datasets.py rejects such a
# name on save; a seeded measure obeys the same rule.
DEMO_MEASURE_NAME = "Margin % (on totals)"

DEMO_MEASURES: list[dict] = [
    {
        "name": DEMO_MEASURE_NAME,
        "expression": "(SUM(revenue) - SUM(cost)) / SUM(revenue) * 100",
        # The measure path ignores the widget's `aggregation` entirely — the
        # expression says how to aggregate. Recorded as avg rather than sum so nothing
        # in the UI ever labels a percentage as a total.
        "default_aggregation": "avg",
        "format": {"type": "percent", "decimals": 1},
    },
]

# Dataset.column_formats, keyed by column name. WidgetRenderer reads these by name:
# allFormats[cfg.measure] for a chart's value axis, allFormats[column] per column for
# a table. A format on a column nothing displays changes nothing on screen, so each
# one here is a column the demo actually shows.
DEMO_COLUMN_FORMATS: dict[str, dict] = {
    "revenue": {"type": "currency", "symbol": "$", "decimals": 0},
    "cost": {"type": "currency", "symbol": "$", "decimals": 0},
    # NOT multiplied by 100 on render (chartUtils.formatValue appends '%' to the number
    # as given), and margin_pct is already stored on a 0-100 scale.
    "margin_pct": {"type": "percent", "decimals": 1},
}

# The drill chain, coarse to fine: 4 regions -> 14 countries -> 10 products. Stored as
# HierarchyNode rows, one child per level. getChildNode (frontend/src/lib/
# hierarchyUtils.ts) takes the FIRST node whose parent is the current one, so a level
# with two children makes the drill path depend on row order.
DEMO_DRILL_FOLDER = "Sales drill-down"
DEMO_DRILL_LEVELS: list[tuple[str, str]] = [
    ("Region", "region"),
    ("Country", "country"),
    ("Product", "product"),
]

DEMO_DETAIL_PAGE_NAME = "Profit & Margin"
DEMO_DETAIL_PAGE_TITLE = "Profit and margin: a calculated column beside a measure"

DEMO_BOOKMARK_NAME = "Europe only"
# Preferred bookmarked value; falls back to the first distinct value if the slicer is
# ever re-pointed at another column, so the bookmark can never capture a filter that
# matches no row.
DEMO_BOOKMARK_VALUE = "Europe"

# Titles of the widgets the feature layer patches. Looked up by title AND type, never
# by position: task 3 owns the order of _sales_overview_specs, and an insertion there
# would otherwise move a gauge's bands onto whatever now sits in that slot.
_GAUGE_TITLE = "Revenue against target"
_TABLE_TITLE = "Largest transactions"
_EXPRESSION_BAR_TITLE = "Revenue by region"

# Detail-page widget titles, referenced by the tests and by nothing else at runtime.
DEMO_CALC_WIDGET_TITLE = "Profit by region"
DEMO_MEASURE_WIDGET_TITLE = "Margin % by region"


@lru_cache(maxsize=1)
def _demo_sales_frame() -> pd.DataFrame:
    """The sales frame, built once. Read-only — callers must not mutate it."""
    return build_demo_frames()["sales"]


def demo_gauge_bands() -> list[dict]:
    """Bands for the gauge's interval rule, derived from the data rather than typed in.

    A hardcoded band set silently stops matching the moment the frame changes, and the
    rule then fails OPEN: no error, no styling, a gauge that looks fine. That is not
    hypothetical — task 4 added 18% year-on-year growth and moved total revenue by 15%.

    Anchored on the total of the `target` column, which is what the gauge is measured
    against: below 75% of target, approaching it, and at or above it.
    """
    frame = _demo_sales_frame()
    value_total = float(frame["revenue"].sum())
    target_total = float(frame["target"].sum())

    step = 100_000  # round to something a human would put on an axis
    warn = math.floor(target_total * 0.75 / step) * step
    goal = math.floor(target_total / step) * step
    # Comfortably above both, so the top band always has room for the needle.
    top = math.ceil(max(value_total, target_total) * 1.5 / step) * step

    return [
        {"min": 0, "max": warn, "color": _COLOUR_BELOW},
        {"min": warn, "max": goal, "color": _COLOUR_NEAR},
        {"min": goal, "max": top, "color": _COLOUR_AT},
    ]


def demo_gauge_rule() -> dict:
    """An `interval` (bands) rule for the gauge.

    `column` names what the rule READS, and it must exist in the SHAPED result, not in
    the dataframe. A gauge's shaped result is one row of {value, target} — pointing
    this at `revenue` (a real column of the dataset!) records an error in rule_errors
    and stops the rule applying, leaving a gauge that renders perfectly, unstyled.
    """
    return {
        "id": "demo-gauge-bands",
        "kind": "interval",
        "target": "mark",
        "label": "Against target",
        "column": "value",
        "bands": demo_gauge_bands(),
    }


def demo_value_map_rule(column: str) -> dict:
    """A `value_map` rule over a table column.

    Like interval, `column` is read from the shaped result — for a raw table that is
    its configured column list. The engine cell-scopes a rule whose column is present
    in a table-shaped result, so this paints the region cell of each row rather than
    the whole row.
    """
    palette = [_COLOUR_ACCENT, _COLOUR_ALT, _COLOUR_AT, _COLOUR_NEAR]
    return {
        "id": "demo-region-colours",
        "kind": "value_map",
        "target": "mark",
        "label": "Region",
        "column": column,
        "any_category": False,
        "mappings": [
            {"value": region, "color": palette[i % len(palette)]}
            for i, region in enumerate(_REGIONS)
        ],
    }


def demo_expression_rule() -> dict:
    """An `expression` rule highlighting the marks above the widget's own average.

    `AVG(value)` reduces to a scalar, which _match_mask broadcasts across every row —
    so the threshold is computed from the shaped result itself and cannot go stale the
    way a typed-in number would. Deliberately carries no `condition`: DisplayRulesPanel
    recompiles `expression` from `condition` on every edit, and a structured condition
    can only express a literal comparison, so round-tripping this rule through the panel
    would overwrite the aggregate with a constant.
    """
    return {
        "id": "demo-above-average-region",
        "kind": "expression",
        "target": "mark",
        "label": "Above the average region",
        "expression": "value > AVG(value)",
        "style": {"fill": _COLOUR_AT},
    }


# The column list for the transactions table. margin_pct is dropped and cost/profit
# added: the raw-table branch of shape_series totals EVERY numeric column it is handed
# with no per-column opt-out, so leaving a rate in the list puts a convincing,
# meaningless number in the footer the moment `show_totals` goes on.
_TABLE_COLUMNS = ["date", "region", "product", "channel", "revenue", "cost", "profit", "units"]


def _detail_page_specs(drill_root_id: int) -> list[tuple[str, str, int, int, dict]]:
    """The second page of the sales report: the two engines beside each other.

    Both bars group by region and both name something that is not a column of the file.
    One resolves through apply_calculated_columns (row level, before grouping); the
    other through measure_eval (after grouping, at this widget's grain). They answer
    different questions and the page says so.
    """
    return [
        ("text", "Two engines, one page", 4, 5,
         {"content": "Calculated column vs measure\n\n"
                     "profit = revenue - cost is a CALCULATED COLUMN: it is evaluated "
                     "once per transaction, before anything is grouped, so summing it by "
                     "region is an ordinary sum.\n\n"
                     f"'{DEMO_MEASURE_NAME}' is a MEASURE: it is evaluated after grouping, "
                     "on each group's totals. It is not the average of the per-row margins "
                     "— refunds carry negative revenue against a positive cost, which pulls "
                     "the two apart by about eight points.\n\n"
                     "Click a bar on the right to drill from region to country to product; "
                     "the measure is recomputed at each level."}),
        ("bar", DEMO_CALC_WIDGET_TITLE, 4, 5,
         {"dimension": "region", "measure": "profit", "aggregation": "sum",
          "limit": 10, "sort": "desc", "sort_by": "value"}),
        # `hierarchyNodeId` (camelCase — WidgetRenderer reads it verbatim off config)
        # points at the TOP level of the chain; the renderer walks to the child node on
        # each drill and rewrites cfg.dimension with that node's column.
        ("bar", DEMO_MEASURE_WIDGET_TITLE, 4, 5,
         {"dimension": DEMO_DRILL_LEVELS[0][1], "measure": DEMO_MEASURE_NAME,
          # Ignored on the measure path (the expression says how to aggregate), but a
          # rate must never be labelled a total anywhere it is read back.
          "aggregation": "avg",
          # Above the widest drill level (14 countries) so no level is truncated.
          "limit": 20, "sort": "desc", "sort_by": "value",
          "hierarchyNodeId": drill_root_id}),
    ]


def _one_widget(widgets: list[ReportWidget], widget_type: str, title: str | None = None) -> ReportWidget:
    """Find the single widget of this type (and title). Raises rather than guessing.

    Looking widgets up by identity is what keeps the feature layer attached to the
    right tiles as tasks 3/4's spec lists change. A silent first-match would move a
    display rule onto a different widget with nothing to show for it — the rule would
    still evaluate, still report no errors, and style the wrong thing.
    """
    matches = [
        w for w in widgets
        if w.widget_type == widget_type and (title is None or w.title == title)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one {widget_type} widget"
            + (f" titled {title!r}" if title else "")
            + f", found {len(matches)}"
        )
    return matches[0]


def _patch(widget: ReportWidget, **config) -> None:
    """Merge keys into a widget's config, reassigning so SQLAlchemy sees the change.

    Column(JSON) has no mutation tracking: editing `widget.config` in place leaves the
    instance clean and the flush writes nothing.
    """
    widget.config = {**(widget.config or {}), **config}
    flag_modified(widget, "config")


async def _seed_drill_hierarchy(db: AsyncSession, dataset: Dataset) -> HierarchyNode:
    """Create the region -> country -> product drill chain, returning its top level.

    Nothing is deleted first: HierarchyNode rows hang off the Dataset with an ORM
    cascade, and seed_demo_datasets has already dropped and rebuilt this org's demo
    datasets, so a re-seed starts from an empty hierarchy by construction.
    """
    folder = HierarchyNode(
        dataset_id=dataset.id, name=DEMO_DRILL_FOLDER, node_type="folder", position=0,
    )
    db.add(folder)
    await db.flush()

    parent_id = folder.id
    top: HierarchyNode | None = None
    for position, (name, column) in enumerate(DEMO_DRILL_LEVELS):
        node = HierarchyNode(
            dataset_id=dataset.id,
            parent_id=parent_id,
            name=name,
            node_type="dimension",
            column_name=column,
            # Drill LEVELS, not measures — an aggregation here would make the field
            # list offer them as numbers to summarise.
            aggregation=None,
            position=position,
        )
        db.add(node)
        await db.flush()
        top = top or node
        parent_id = node.id

    assert top is not None  # DEMO_DRILL_LEVELS is never empty
    return top


async def seed_demo_features(
    db: AsyncSession, org_id: int, datasets: dict[str, Dataset], reports: list[Report],
) -> None:
    """Layer the app's own features over the seeded demo content.

    MUST run after both seed_demo_datasets and seed_demo_reports, and takes what each
    returned: the datasets it decorates and the reports whose widgets it patches. The
    caller (the "Load demo content" endpoint) owns the transaction — this flushes and
    never commits, exactly like the two seeders before it, so a failure here rolls the
    whole demo back rather than leaving a half-featured one behind.

    Idempotent for free: the hierarchy hangs off a Dataset and the bookmark and detail
    page hang off a Report, all three of which the seeders above have already dropped
    and rebuilt for this org. Nothing here needs its own cleanup pass, and nothing here
    can reach outside `org_id`, because every row it touches is reached through one of
    those two org-scoped collections.
    """
    # Nothing below writes org_id: HierarchyNode and Bookmark have no org column of
    # their own, and the Dataset and Report rows this decorates already carry one. So
    # the scope of everything created here is inherited from the two collections passed
    # in — which makes verifying THEM the only place the caller's org can be enforced.
    # An org mix-up would otherwise hang one org's drill hierarchy off another's
    # dataset, and nothing downstream would notice.
    stray = [d.name for d in datasets.values() if d.org_id != org_id]
    stray += [r.name for r in reports if r.org_id != org_id]
    if stray:
        raise ValueError(
            f"demo content belonging to another org was passed to the feature layer: {stray}"
        )

    sales = datasets["sales"]

    # ── Dataset-level: the two expression engines, and how their columns render ──
    sales.calculated_columns = copy.deepcopy(DEMO_CALCULATED_COLUMNS)
    sales.measures = copy.deepcopy(DEMO_MEASURES)
    sales.column_formats = copy.deepcopy(DEMO_COLUMN_FORMATS)
    for attr in ("calculated_columns", "measures", "column_formats"):
        flag_modified(sales, attr)

    drill_root = await _seed_drill_hierarchy(db, sales)

    report = next(
        (r for r in reports if r.name == DEMO_REPORT_NAMES["sales_overview"]), None,
    )
    if report is None:  # pragma: no cover - only reachable if the report specs change
        raise ValueError("the sales overview demo report was not seeded")

    pages = (await db.execute(
        select(ReportPage).where(ReportPage.report_id == report.id).order_by(ReportPage.position)
    )).scalars().all()
    main_page = pages[0]

    # ── The detail page, and the button that reaches it ──
    detail_page = ReportPage(
        report_id=report.id,
        name=DEMO_DETAIL_PAGE_NAME,
        title=DEMO_DETAIL_PAGE_TITLE,
        position=max(p.position for p in pages) + 1,
    )
    db.add(detail_page)
    await db.flush()

    packer = _GridPacker()
    for widget_type, title, w, h, config in _detail_page_specs(drill_root.id):
        db.add(ReportWidget(
            page_id=detail_page.id,
            widget_type=widget_type,
            title=title,
            config={**config, DEMO_META_KEY: DEMO_MARKER},
            layout=packer.place(w, h),
        ))
    await db.flush()

    # Every widget on the report, both pages, so a lookup by title has to discriminate:
    # the detail page adds two more bars, and dropping the title from the bar lookup
    # below now raises instead of silently patching whichever bar comes back first.
    widgets = (await db.execute(
        select(ReportWidget)
        .join(ReportPage, ReportWidget.page_id == ReportPage.id)
        .where(ReportPage.report_id == report.id)
    )).scalars().all()

    # WidgetRenderer.handleButtonClick needs BOTH keys — `action` alone is a button
    # that does nothing when clicked, which looks exactly like one nobody wired up.
    button = _one_widget(widgets, "button")
    _patch(button, label="Profit & margin", action="navigate", actionPageId=detail_page.id)

    # ── Display rules: one of each kind the engine supports ──
    _patch(_one_widget(widgets, "gauge", _GAUGE_TITLE), display_rules=[demo_gauge_rule()])
    _patch(
        _one_widget(widgets, "bar", _EXPRESSION_BAR_TITLE),
        display_rules=[demo_expression_rule()],
    )

    # ── The table: chrome, the calculated column, and the colour map ──
    table = _one_widget(widgets, "table", _TABLE_TITLE)
    _patch(
        table,
        columns=list(_TABLE_COLUMNS),
        show_totals=True,
        table_banding=True,
        table_row_lines=True,
        display_rules=[demo_value_map_rule("region")],
    )

    # ── A bookmark replaying a filter the slicer could have emitted ──
    slicer = _one_widget(widgets, "slicer")
    column = slicer.config.get("dimension")
    distinct = [str(v) for v in _demo_sales_frame()[column].unique()]
    value = DEMO_BOOKMARK_VALUE if DEMO_BOOKMARK_VALUE in distinct else distinct[0]
    db.add(Bookmark(
        report_id=report.id,
        name=DEMO_BOOKMARK_NAME,
        position=0,
        # BookmarkState (frontend/src/types/report.ts) — ReportBuilder.applyBookmark
        # reads every one of these keys, and a missing one is a TypeError in the
        # browser rather than a bookmark that restores a little less than it should.
        state={
            "pageId": main_page.id,
            "activeFilters": [{
                "column": column,
                "value": value,
                "label": f"{column.replace('_', ' ').title()} = {value}",
                "sourceWidgetId": slicer.id,
                "sourcePageId": main_page.id,
            }],
            "promptValues": {},
            "hiddenWidgetIds": [],
        },
    ))

    await db.flush()


# ── The UX Showcase demo ────────────────────────────────────────────────────────
#
# A second report that tours every interactive facility the platform has, over the
# same sales dataset seed_demo_features already decorated: the five ReportPage.
# page_type values, button actions (navigate / url), the drill hierarchy bound to a
# chart at two different starting levels, tooltip-page and drillthrough-page binding,
# cross-filter interaction modes, a page prompt, and bookmarks. Nothing here is a new
# capability -- every field is one the app already reads; see WidgetRenderer.tsx and
# PagePropertiesPanel.tsx for where each one is consumed.
#
# MUST run after seed_demo_features: the drill hierarchy it binds to is created there,
# hanging off the `sales` Dataset.

UX_SHOWCASE_REPORT_NAME = "UX Showcase (demo)"
UX_SHOWCASE_REPORT_DESCRIPTION = (
    "One report touring every interactive facility the platform has: button actions, "
    "all five page types, a hierarchical drill-down, cross-filter interaction modes, "
    "a page prompt and two bookmarks -- over the same sales data as the main demo."
)

UX_SHOWCASE_PAGE_NAMES: dict[str, str] = {
    "start": "Start here",
    "drilldown": "Drill-down",
    "popup": "Popup KPIs",
    "tooltip": "Hover detail",
    "drillthrough": "Transaction detail",
    "hidden": "Hidden notes",
    "prompt": "Choose a region",
}

# {{@name}} is the button-url placeholder WidgetRenderer.handleButtonClick substitutes
# from the live report parameter of that name (URL-encoded, after which the scheme is
# re-checked against the http/https allowlist) -- NOT the `{filter}` form, which the
# renderer does not recognise.
UX_SHOWCASE_DOCS_URL = "https://docs.example.com/tour?region={{@region}}"

DEMO_SHOWCASE_BOOKMARK_TOP_REGION = "Top region only"
# Filters on `country`, the SAME dimension the Drill-down page's second chart charts
# (country_chart, below) -- unlike an earlier draft that filtered `month` against two
# charts dimensioned region/country, so restoring it visibly narrows that chart to one
# bar instead of doing nothing observable in linked (highlight) mode.
DEMO_SHOWCASE_BOOKMARK_WEAK_COUNTRY = "Weakest-margin country"


async def _remove_existing_ux_showcase(db: AsyncSession, org_id: int) -> None:
    """Delete this org's previously seeded showcase report, by name.

    Unlike `_remove_existing_demo_reports`, this is scoped to ONE report name rather
    than every marker-tagged report in the org: seed_demo_ux_showcase must be
    idempotent even when called on its own (as a test does), without wiping the
    sales-family reports the generic marker-based cleanup would also catch. The name
    is exclusive to this seeder in the same way DEMO_DETAIL_PAGE_NAME and
    DEMO_DRILL_FOLDER are -- nothing else creates a report called this.
    """
    result = await db.execute(
        select(Report)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
        .where(Report.org_id == org_id, Report.name == UX_SHOWCASE_REPORT_NAME)
    )
    for report in result.scalars().unique().all():
        await db.delete(report)  # cascades to pages, widgets and bookmarks
    await db.flush()


async def seed_demo_ux_showcase(
    db: AsyncSession, org_id: int, datasets: dict[str, Dataset],
) -> Report:
    """Build the "UX Showcase (demo)" report over the sales dataset and its hierarchy.

    MUST run after seed_demo_features (the drill hierarchy it binds to hangs off the
    `sales` Dataset that pass creates). Does NOT commit -- the caller owns the
    transaction, matching every other seeder in this module.

    Idempotent on its own: any previously seeded showcase report in this org is
    removed by name first, so calling this twice (or calling the whole pipeline
    twice) leaves exactly one copy. Every widget it creates carries DEMO_META_KEY, so
    `remove_demo_content`'s generic marker-based cleanup finds it without any change
    there.
    """
    sales = datasets["sales"]
    if sales.org_id != org_id:
        raise ValueError(
            f"demo content belonging to another org was passed to the UX showcase seeder: {sales.name}"
        )

    await _remove_existing_ux_showcase(db, org_id)

    levels = (await db.execute(
        select(HierarchyNode)
        .where(HierarchyNode.dataset_id == sales.id, HierarchyNode.node_type == "dimension")
        .order_by(HierarchyNode.position)
    )).scalars().all()
    if len(levels) < 2:
        raise ValueError(
            "the sales drill hierarchy must exist before the UX showcase seeds "
            "(seed_demo_features runs _seed_drill_hierarchy)"
        )
    region_level, country_level = levels[0], levels[1]

    report = Report(
        name=UX_SHOWCASE_REPORT_NAME,
        description=UX_SHOWCASE_REPORT_DESCRIPTION,
        dataset_id=sales.id,
        org_id=org_id,
    )
    db.add(report)
    await db.flush()

    # ── Pages first, so every button/tooltip/drillthrough wiring below can point at
    # a REAL, already-flushed page id rather than a placeholder resolved later. ──
    start_page = ReportPage(
        report_id=report.id, name=UX_SHOWCASE_PAGE_NAMES["start"],
        title=UX_SHOWCASE_PAGE_NAMES["start"], page_type="normal", position=0,
        # interaction_mode rides in mobile_layout (PagePropertiesPanel.tsx) --
        # "oneway" contrasts with the Drill-down page's "linked" below, so the two
        # pages demonstrate filter-mode vs highlight-mode cross-filtering side by side.
        mobile_layout={"interaction_mode": "oneway"},
    )
    drilldown_page = ReportPage(
        report_id=report.id, name=UX_SHOWCASE_PAGE_NAMES["drilldown"],
        title=UX_SHOWCASE_PAGE_NAMES["drilldown"], page_type="normal", position=1,
        mobile_layout={"interaction_mode": "linked"},
    )
    popup_page = ReportPage(
        report_id=report.id, name=UX_SHOWCASE_PAGE_NAMES["popup"],
        title=UX_SHOWCASE_PAGE_NAMES["popup"], page_type="popup", position=2,
    )
    tooltip_page = ReportPage(
        report_id=report.id, name=UX_SHOWCASE_PAGE_NAMES["tooltip"],
        title=UX_SHOWCASE_PAGE_NAMES["tooltip"], page_type="tooltip", position=3,
    )
    drillthrough_page = ReportPage(
        report_id=report.id, name=UX_SHOWCASE_PAGE_NAMES["drillthrough"],
        title=UX_SHOWCASE_PAGE_NAMES["drillthrough"], page_type="drillthrough", position=4,
    )
    hidden_page = ReportPage(
        report_id=report.id, name=UX_SHOWCASE_PAGE_NAMES["hidden"],
        title=UX_SHOWCASE_PAGE_NAMES["hidden"], page_type="hidden", position=5,
    )
    # The prompt page: prompt_column/prompt_label are real ReportPage columns (unlike
    # interaction_mode above), so this one persists straight onto the row.
    prompt_page = ReportPage(
        report_id=report.id, name=UX_SHOWCASE_PAGE_NAMES["prompt"],
        title=UX_SHOWCASE_PAGE_NAMES["prompt"], page_type="normal", position=6,
        prompt_column="region", prompt_label="Region",
    )
    db.add_all([
        start_page, drilldown_page, popup_page, tooltip_page, drillthrough_page,
        hidden_page, prompt_page,
    ])
    await db.flush()

    # ── Drill-down: two charts over the SAME hierarchy, starting one level apart. ──
    packer = _GridPacker()
    region_chart = ReportWidget(
        page_id=drilldown_page.id, widget_type="bar", title="Revenue by region (top level)",
        config={
            "dimension": region_level.column_name, "measure": "revenue", "aggregation": "sum",
            "limit": 10, "sort": "desc", "sort_by": "value",
            "hierarchyNodeId": region_level.id,
            # Wired straight to the already-flushed tooltip/drillthrough pages -- the
            # "main bar chart" both the hover tooltip and the drill-through reach.
            "tooltipPageId": tooltip_page.id,
            "drillthroughPageId": drillthrough_page.id,
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=packer.place(6, 5),
    )
    country_chart = ReportWidget(
        page_id=drilldown_page.id, widget_type="bar",
        title="Revenue by country (starts one level in)",
        config={
            "dimension": country_level.column_name, "measure": "revenue", "aggregation": "sum",
            "limit": 14, "sort": "desc", "sort_by": "value",
            "hierarchyNodeId": country_level.id,
            "drillthroughPageId": drillthrough_page.id,
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=packer.place(6, 5),
    )
    db.add_all([region_chart, country_chart])

    # ── Start here: the tour text, and the three buttons demonstrating both actions. ──
    start_packer = _GridPacker()
    db.add(ReportWidget(
        page_id=start_page.id, widget_type="text", title="UX Showcase tour",
        config={
            "content": "UX Showcase\n\n"
                       "This report exists to demonstrate the platform's interactive "
                       "facilities, not to analyse anything. Every button, page and "
                       "chart below is real and clickable.\n\n"
                       "Drill into sales walks the same region -> country -> product "
                       "hierarchy the main demo builds, starting at two different "
                       "levels. Open KPIs page — declared page_type 'popup'; in view "
                       "mode it renders as a centred floating overlay over this page "
                       "rather than switching tabs. Read the docs opens an external "
                       "link built from a parameter placeholder.\n\n"
                       "This page's interactions are set to filter-mode; the "
                       "Drill-down page next to it is set to highlight-mode, so "
                       "clicking a bar behaves differently on each.",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=start_packer.place(6, 4),
    ))
    db.add(ReportWidget(
        page_id=start_page.id, widget_type="button", title="Drill into sales",
        # WidgetRenderer.handleButtonClick needs BOTH `action` and `actionPageId` --
        # `action` alone is a button that does nothing when clicked.
        config={
            "label": "Drill into sales", "action": "navigate", "actionPageId": drilldown_page.id,
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=start_packer.place(2, 4),
    ))
    db.add(ReportWidget(
        page_id=start_page.id, widget_type="button", title="Open KPIs page",
        config={
            "label": "Open KPIs page", "action": "navigate", "actionPageId": popup_page.id,
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=start_packer.place(2, 4),
    ))
    db.add(ReportWidget(
        page_id=start_page.id, widget_type="button", title="Read the docs",
        config={
            "label": "Read the docs", "action": "url", "actionUrl": UX_SHOWCASE_DOCS_URL,
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=start_packer.place(2, 4),
    ))

    # ── Popup KPIs: three cards. `page_type='popup'` is declared and configured here,
    # and the product now renders it as a floating overlay in view mode -- opening it
    # (from the Start here button) shows a centred modal over the page you triggered
    # it from rather than switching tabs; closing (Esc, backdrop, or the × button)
    # returns you there unchanged.
    # `profit` (calculated column) and `margin_pct` are both already on `sales` --
    # seed_demo_features set them dataset-wide, so any widget over this dataset can
    # read them, not only the sales-overview report's own. ──
    popup_packer = _GridPacker()
    db.add(ReportWidget(
        page_id=popup_page.id, widget_type="text", title="Popup page notes",
        config={
            "content": "Popup page\n\n"
                       "This page's page_type is 'popup'. In view mode, opening it "
                       "(from the Start here button) renders it as a centred floating "
                       "overlay on top of the page you triggered it from, dimmed "
                       "backdrop and all -- the underlying page stays active "
                       "underneath. Esc, the backdrop, or the × button all close it "
                       "and return you there unchanged.",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=popup_packer.place(12, 3),
    ))
    for title, config in [
        ("Total revenue", {"measure": "revenue", "aggregation": "sum"}),
        ("Total profit", {"measure": "profit", "aggregation": "sum"}),
        ("Average margin %", {"measure": "margin_pct", "aggregation": "avg"}),
    ]:
        db.add(ReportWidget(
            page_id=popup_page.id, widget_type="kpi", title=title,
            config={**config, DEMO_META_KEY: DEMO_MARKER},
            layout=popup_packer.place(4, 4),
        ))

    # ── Hover detail: page_type='tooltip', declared and configured (tooltipPageId on
    # the Drill-down chart, above). The product now triggers this on hover in view
    # mode: hovering the Drill-down page's main chart for ~300ms floats this page's
    # widgets in a small panel near the cursor; moving the mouse away dismisses it. ──
    tooltip_packer = _GridPacker()
    db.add(ReportWidget(
        page_id=tooltip_page.id, widget_type="text", title="Tooltip page notes",
        config={
            "content": "Tooltip page\n\n"
                       "This page's page_type is 'tooltip', and the Drill-down page's "
                       "main chart is wired to it via tooltipPageId. Hover that chart "
                       "in view mode for a moment to see this page appear as a "
                       "floating panel near the cursor.",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=tooltip_packer.place(12, 3),
    ))
    db.add(ReportWidget(
        page_id=tooltip_page.id, widget_type="table", title="Region snapshot",
        config={
            "columns": ["region", "revenue", "margin_pct"],
            "limit": 5, "sort_col": "revenue", "sort": "desc",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=tooltip_packer.place(6, 5),
    ))

    # ── Transaction detail: page_type='drillthrough', declared and configured
    # (drillthroughPageId on both Drill-down charts). The product now triggers
    # drill-through from a click in view mode -- click a bar on Drill-down, then
    # use the "Drill through" button that appears next to the selected point (or
    # right-click it for the same option in a context menu) to land here with the
    # clicked value applied as this page's prompt filter. The raw-transaction table
    # pattern matches _detail_page_specs. ──
    drillthrough_packer = _GridPacker()
    db.add(ReportWidget(
        page_id=drillthrough_page.id, widget_type="text", title="Drillthrough page notes",
        config={
            "content": "Drillthrough page\n\n"
                       "This page's page_type is 'drillthrough', and both Drill-down "
                       "page charts are wired to it via drillthroughPageId. Click a "
                       "bar on Drill-down, then click the \"Drill through\" button "
                       "next to the selected point (or right-click it) to land here "
                       "with the clicked value applied as this page's prompt filter.",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=drillthrough_packer.place(12, 3),
    ))
    db.add(ReportWidget(
        page_id=drillthrough_page.id, widget_type="table", title="Transaction detail",
        config={
            "columns": ["date", "region", "country", "product", "channel", "revenue", "units", "margin_pct"],
            "limit": 100, "sort_col": "revenue", "sort": "desc",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout=drillthrough_packer.place(12, 6),
    ))

    # ── Hidden notes: visible in edit mode, absent from the view-mode tab strip. ──
    db.add(ReportWidget(
        page_id=hidden_page.id, widget_type="text", title="Hidden notes",
        config={
            "content": "Hidden page\n\n"
                       "This page proves the `hidden` page type: it shows up here in "
                       "the editor's page list, but the view-mode tab strip never "
                       "renders a tab for it.",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout={"x": 0, "y": 0, "w": 6, "h": 4},
    ))

    # ── Choose a region: the prompt page, asking for a Region before rendering. ──
    # ReportBuilder builds `promptFilter = {column: prompt_column, value: promptValues[
    # pageId]}` and passes it to EVERY widget on the page (WidgetRenderer folds it into
    # the same `pagePrompt` WHERE-style filter a cross-filter uses), so a plain text
    # widget alone leaves nothing to visibly react when a region is entered. A data
    # widget over `sales` -- which carries a `region` column -- is what makes the
    # prompt's filtering OBSERVABLE: entering a region narrows this table to that
    # region's own transactions.
    db.add(ReportWidget(
        page_id=prompt_page.id, widget_type="text", title="Prompt demo",
        config={
            "content": "Page prompt\n\n"
                       "This page's `prompt_column` is set to region: a viewer is "
                       "asked to pick one before the page renders, and every widget "
                       "on it is filtered to that choice -- including the chart below.",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout={"x": 0, "y": 0, "w": 12, "h": 3},
    ))
    db.add(ReportWidget(
        page_id=prompt_page.id, widget_type="bar", title="Revenue by country (filtered by the prompt)",
        config={
            "dimension": "country", "measure": "revenue", "aggregation": "sum",
            "limit": 14, "sort": "desc", "sort_by": "value",
            DEMO_META_KEY: DEMO_MARKER,
        },
        layout={"x": 0, "y": 3, "w": 12, "h": 5},
    ))

    await db.flush()

    # ── Two bookmarks, each capturing a distinct filter state over real data, on
    # dimensions the Drill-down page's own charts actually carry -- region_chart
    # (dimension=region) and country_chart (dimension=country) -- so restoring either
    # one is visibly observable on that page rather than filtering by a column no
    # widget there charts. ──
    frame = _demo_sales_frame()
    top_region = str(frame.groupby("region")["revenue"].sum().idxmax())
    profit_by_country = (frame["revenue"] - frame["cost"]).groupby(frame["country"]).sum()
    weak_country = str(profit_by_country.idxmin())

    db.add(Bookmark(
        report_id=report.id, name=DEMO_SHOWCASE_BOOKMARK_TOP_REGION, position=0,
        state={
            "pageId": drilldown_page.id,
            "activeFilters": [{
                "column": "region", "value": top_region,
                "label": f"Region = {top_region}",
                "sourceWidgetId": region_chart.id, "sourcePageId": drilldown_page.id,
            }],
            "promptValues": {},
            "hiddenWidgetIds": [],
        },
    ))
    db.add(Bookmark(
        report_id=report.id, name=DEMO_SHOWCASE_BOOKMARK_WEAK_COUNTRY, position=1,
        state={
            "pageId": drilldown_page.id,
            "activeFilters": [{
                "column": "country", "value": weak_country,
                "label": f"Country = {weak_country}",
                "sourceWidgetId": country_chart.id, "sourcePageId": drilldown_page.id,
            }],
            "promptValues": {},
            "hiddenWidgetIds": [],
        },
    ))

    await db.flush()
    return report


# ── The DirectQuery demo ──────────────────────────────────────────────────────
#
# Everything above is import mode: a file loaded into pandas. This section adds the
# other half of the app — a dataset in `mode="directquery"`, whose queries are pushed
# down to a live source as SQL and never materialise locally.
#
# The source is a SQLite FILE written beside the demo CSVs, deliberately not the app's
# own Postgres: "Load demo content" must not fail on a deployment that has no second
# database, and SQLite needs no credentials, no host and no network while exercising
# exactly the same run_direct_query code path (SUPPORTED_DIALECTS includes it, and
# build_sql emits the same trailing LIMIT clause for it as for Postgres).
# Postgres-specific pushdown is covered by test_direct_query_stat_postgres.py.
#
# The data is shaped so the DirectQuery-specific hazards are VISIBLE rather than
# merely present:
#   * 24 cities against a widget limit of 8, so `limit` (pushed into SQL) genuinely
#     truncates and a "Total" that summed the returned page would be plainly wrong;
#   * ~4% of rows with a NULL city carrying real money, so a total that failed to
#     exclude the group nothing renders is a different number, not the same one;
#   * two priorities with exactly equal row counts, so the deterministic tie-break
#     has something to order;
#   * 12,000 rows against DEFAULT_ROW_CAP (10,000), so the raw-table widget really
#     samples and its column totals have to be re-measured in SQL.

DEMO_DIRECTQUERY_SOURCE_NAME = "Demo — Live SQLite"
DEMO_DIRECTQUERY_DATASET_NAME = "Demo — Live Orders (DirectQuery)"
DEMO_DIRECTQUERY_DATASET_DESCRIPTION = (
    "12,000 orders queried live over SQL — nothing is loaded into the app. Grouping, "
    "filtering and totals are pushed down to the source."
)
DEMO_DIRECTQUERY_REPORT_NAME = "Demo — Live Orders (DirectQuery)"
DEMO_DIRECTQUERY_REPORT_DESCRIPTION = (
    "The same widgets over a live SQL source instead of an uploaded file: aggregation "
    "pushed into the query, a sampled detail table, and totals measured over the whole "
    "table rather than the visible page."
)

# The table inside the SQLite file. `source_table`, not `source_query`, so the demo
# exercises the plain table path every DirectQuery query builder wraps.
DEMO_DIRECTQUERY_TABLE = "live_orders"

# Above DEFAULT_ROW_CAP (10,000) by enough that the sample is unmistakably a sample.
DEMO_DIRECTQUERY_ROWS = 12_000

_DQ_SEED = _SEED + 1

# 24 cities: three times the widget limit below, so the top-8 table is visibly a page
# of a larger result.
_DQ_CITIES = [
    "Amsterdam", "Auckland", "Berlin", "Boston", "Chicago", "Copenhagen",
    "Dubai", "Dublin", "Helsinki", "Lisbon", "London", "Madrid",
    "Melbourne", "Milan", "Montreal", "Munich", "Oslo", "Paris",
    "Prague", "Seattle", "Singapore", "Stockholm", "Toronto", "Vienna",
]

# Exact row counts per priority, NOT a random draw: Express and Priority tie at 3,000
# by construction. A tie that depends on chance is a tie that quietly disappears the
# day the generator changes, taking the tie-break assertion with it.
_DQ_PRIORITY_COUNTS: dict[str, int] = {
    "Standard": 4000,
    "Express": 3000,
    "Priority": 3000,
    "Overnight": 2000,
}

# Share of rows whose city is NULL. Whatever renders these rows' money would be
# describing a group no widget shows.
_DQ_NULL_CITY_SHARE = 0.04

# Widget titles are looked up by tests and by any later feature layer, so they are
# constants rather than literals buried in the specs below.
DEMO_DQ_CITY_WIDGET_TITLE = "Revenue by city (top 8 of 24)"
DEMO_DQ_PRIORITY_WIDGET_TITLE = "Orders by priority (top 3 of 4)"
DEMO_DQ_TABLE_WIDGET_TITLE = "Live order detail"

# Deliberately smaller than the group counts they page through. Read by the widget
# specs, so a widget and its "top N of M" title cannot drift apart.
DEMO_DQ_CITY_LIMIT = 8
DEMO_DQ_PRIORITY_LIMIT = 3


def build_demo_directquery_frame(n: int = DEMO_DIRECTQUERY_ROWS) -> pd.DataFrame:
    """The rows that go into the demo's SQLite file.

    Its own generator, seeded independently of build_demo_frames(), so changing the
    number of rows here can never shift a single value in the four import frames.
    """
    rng = np.random.default_rng(_DQ_SEED)

    # Every city appears at least once by construction: the first 24 rows cover them
    # one-for-one before the random draw fills the rest. Left to chance the demo would
    # *almost* always show 24 groups, and "almost" is not reproducible.
    n_cities = len(_DQ_CITIES)
    city_idx = np.concatenate([np.arange(n_cities), rng.integers(0, n_cities, size=n - n_cities)])
    cities = np.array(_DQ_CITIES, dtype=object)[city_idx]
    null_city = rng.random(n) < _DQ_NULL_CITY_SHARE
    null_city[:n_cities] = False  # keep the one-of-each block intact
    cities = np.where(null_city, None, cities)

    priorities = np.array(
        [p for p, count in _DQ_PRIORITY_COUNTS.items() for _ in range(count)], dtype=object
    )
    if len(priorities) != n:  # pragma: no cover - guards the constants above
        raise ValueError(f"_DQ_PRIORITY_COUNTS sums to {len(priorities)}, not {n}")
    rng.shuffle(priorities)

    channels = np.array(_CHANNELS, dtype=object)[rng.integers(0, len(_CHANNELS), size=n)]

    day_offset = rng.integers(0, 365, size=n)
    order_date = pd.Timestamp("2025-01-01") + pd.to_timedelta(day_offset, unit="D")

    # Strictly positive, so any page of groups is a strict subset of the total and a
    # page-sum can never coincidentally equal the true one.
    amount = np.round(rng.gamma(shape=5.0, scale=180.0, size=n) + 5.0, 2)
    quantity = rng.integers(1, 25, size=n)

    return pd.DataFrame({
        "order_id": np.arange(1, n + 1),
        # Stored as text: SQLite has no date type, which is part of what a DirectQuery
        # demo should show. `month` is pre-bucketed for the same reason the sales frame
        # pre-buckets its own — the pushdown groups by the raw column (plan_query does
        # not apply `dimension_granularity`), so a monthly axis needs a monthly column
        # to exist in the source.
        "order_date": order_date.strftime("%Y-%m-%d"),
        "month": order_date.strftime("%Y-%m"),
        "city": cities,
        "channel": channels,
        "priority": priorities,
        "quantity": quantity,
        "amount": amount,
    })


def demo_directquery_sqlite_path(org_id: int) -> Path:
    """Beside the demo CSVs, and named per org for the same reason they are: one org's
    re-seed drops this file, and a shared path would empty another org's demo."""
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / f"demo_{org_id}_directquery.db"


def demo_directquery_source_config(path: Path) -> dict:
    """DataSource.config for the demo source: what connections._build_url reads
    (`filepath`) plus the demo marker. `type` is a column on the row, not part of the
    config — the query path adds it back."""
    return {"filepath": str(path), DEMO_META_KEY: DEMO_MARKER}


def _connection_cfg(config: dict | None, source_type: str) -> dict:
    """The dict routers/widget_data.py hands run_direct_query. Reproduced here so the
    engine-registry key this module disposes is the very key the query path created —
    a key built any other way would dispose nothing and leave the file open."""
    cfg = dict(config or {})
    cfg["type"] = source_type
    return cfg


def is_demo_data_source(source: DataSource) -> bool:
    """True if `source` was created by the demo loader.

    Identified by the marker inside its config JSON, never by name — a user is
    entitled to a connection of their own called "Demo — Live SQLite", and a re-seed
    must not delete it (and with it, their credentials). The marker rides in `config`
    because that is the only free-form column on the row; the query path copies the
    config verbatim and ignores keys it does not know.
    """
    return (source.config or {}).get(DEMO_META_KEY) == DEMO_MARKER


def _write_demo_sqlite(path: Path) -> None:
    """(Re)create the demo's SQLite file from the frame.

    The engine is disposed before the file is touched: a pooled connection from an
    earlier seed in this process would make the unlink fail on Windows, and on POSIX
    would go on answering from the deleted inode.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    dispose_engine(_connection_cfg(demo_directquery_source_config(path), "sqlite"))
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        build_demo_directquery_frame().to_sql(
            DEMO_DIRECTQUERY_TABLE, conn, index=False, if_exists="replace",
        )
        conn.commit()
    finally:
        conn.close()


async def _remove_existing_demo_directquery(db: AsyncSession, org_id: int) -> None:
    """Delete this org's previously seeded DirectQuery demo: the report over it, the
    dataset, the DataSource, and the SQLite file the source pointed at.

    Every match is on the demo marker, never on a name — the same rule the dataset and
    report cleanups follow. Scoped to `org_id` in each query, so a re-seed in one org
    cannot reach into another's.

    Order matters: the report goes first, because Dataset -> Report is ON DELETE SET
    NULL, so dropping the dataset first would leave a demo report pointing at nothing
    instead of removing it.
    """
    datasets = (await db.execute(
        select(Dataset).where(Dataset.org_id == org_id)
    )).scalars().all()
    dq_ids = {d.id for d in datasets if is_demo_dataset(d) and d.mode == "directquery"}

    if dq_ids:
        reports = (await db.execute(
            select(Report)
            .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
            .where(Report.org_id == org_id)
        )).scalars().unique().all()
        for report in reports:
            if report.dataset_id in dq_ids and is_demo_report(report):
                await db.delete(report)

        for ds in datasets:
            if ds.id in dq_ids:
                await db.delete(ds)

    sources = (await db.execute(
        select(DataSource).where(DataSource.org_id == org_id)
    )).scalars().all()
    for source in sources:
        if not is_demo_data_source(source):
            continue
        filepath = (source.config or {}).get("filepath")
        if filepath:
            # Close the pool before unlinking, for the reasons in dispose_engine.
            dispose_engine(_connection_cfg(source.config, source.type))
            Path(filepath).unlink(missing_ok=True)
        await db.delete(source)

    await db.flush()


def _directquery_specs() -> list[tuple[str, str, int, int, dict]]:
    """Widget specs for the DirectQuery report — every one of them a shape
    direct_query.py can actually push down.

    That allowlist is narrow and deliberate (AGGREGATE_STRATEGY_WIDGET_TYPES /
    ROW_CAPPED_WIDGET_TYPES), and a widget outside it does not degrade gracefully: the
    endpoint answers DirectQueryUnsupported with a 400 and the tile renders an error.
    So: no second dimension (crosstab pivots are not pushed down), no running totals,
    no calculated columns or measures, and time is grouped by a real `month` column
    rather than by `dimension_granularity`, which plan_query does not apply.

    `crosstab` with a dimension but no dimension2 is the deliberate choice for the two
    totalled widgets: it shapes as a grouped series and the renderer draws it as a
    two-column table WITH a totals row (WidgetRenderer.tsx builds its columns from the
    row keys). A bar chart's renderer never draws `totals`, so the invariant this demo
    exists to show would be computed and then thrown away.
    """
    return [
        # ── The totals invariant, in the two shapes that compute it differently ──
        # With a measure: the aggregate pushdown, whose grand total comes from
        # build_group_total_sql re-running the same GROUP BY unlimited.
        ("crosstab", DEMO_DQ_CITY_WIDGET_TITLE, 6, 6,
         {"dimension": "city", "measure": "amount", "aggregation": "sum",
          "limit": DEMO_DQ_CITY_LIMIT, "sort": "desc", "sort_by": "value",
          "show_totals": True, "table_row_lines": True}),
        # Without one: _run_count_series, which builds its rows itself and totals with
        # the same builder in count_only mode.
        ("crosstab", DEMO_DQ_PRIORITY_WIDGET_TITLE, 6, 6,
         {"dimension": "priority", "limit": DEMO_DQ_PRIORITY_LIMIT, "sort": "desc",
          "sort_by": "value", "show_totals": True, "table_row_lines": True}),

        # ── Ordinary pushed-down visuals ──
        ("line", "Revenue by month", 8, 5,
         {"dimension": "month", "measure": "amount", "aggregation": "sum",
          "limit": 24, "sort": "asc", "sort_by": "name"}),
        ("donut", "Revenue by channel", 4, 5,
         {"dimension": "channel", "measure": "amount", "aggregation": "sum",
          "limit": 10, "sort": "desc", "sort_by": "value"}),

        # ── The row-capped path: a sample, honestly labelled, with true totals ──
        ("table", DEMO_DQ_TABLE_WIDGET_TITLE, 8, 6,
         {"columns": ["order_date", "city", "channel", "priority", "quantity", "amount"],
          "limit": 100, "show_totals": True, "table_banding": True}),
        ("text", "About this report", 4, 6,
         {"content": "Demo — Live Orders (DirectQuery)\n\n"
                     "This report queries a live SQL source. Nothing is loaded into the "
                     "app: each tile is a query, pushed down and aggregated at the "
                     "source.\n\n"
                     "The two tables show 8 of 24 cities and 3 of 4 priorities — and "
                     "their Total rows cover every group, not the rows on screen.\n\n"
                     "The detail table is a 10,000-row sample of 12,000 orders, labelled "
                     "as one, and its totals are measured over all 12,000."}),
    ]


async def seed_demo_directquery(db: AsyncSession, org_id: int) -> dict[str, object]:
    """Seed the DirectQuery half of the demo: a SQLite source, a dataset in
    `mode="directquery"` over it, and a small report.

    Returns {"source", "dataset", "report"}.

    Runs as its own pass rather than inside seed_demo_datasets/seed_demo_reports:
    those two return an import-mode dataset per frame and a report per widget family,
    and folding in a fifth dataset with no file (and a report whose widgets can only be
    answered by a live connection) would change what both of them return.

    Call it AFTER seed_demo_datasets — that seeder removes every demo dataset in the
    org, this one included, so seeding in the other order leaves the org with no
    DirectQuery dataset and a DataSource pointing at nothing.

    Idempotent, cleaning up by the demo marker in the same way and for the same reason
    the other seeders do. Does NOT commit: the caller owns one transaction across all
    of them. The SQLite write is not transactional and a rollback therefore strands the
    file — the same deliberate trade seed_demo_datasets makes for its CSVs: an orphaned
    file is referenced by nothing and is overwritten by the next seed.
    """
    await _remove_existing_demo_directquery(db, org_id)

    path = demo_directquery_sqlite_path(org_id)
    _write_demo_sqlite(path)

    source = DataSource(
        name=DEMO_DIRECTQUERY_SOURCE_NAME,
        type="sqlite",
        config=demo_directquery_source_config(path),
        org_id=org_id,
    )
    db.add(source)
    await db.flush()

    # The same schema probe routers/data_sources.py runs when a user creates a
    # DirectQuery dataset by hand — a preview through the app's own connection layer,
    # typed by the app's own detection — rather than a column list written out here.
    # DirectQuery validates every column it interpolates into SQL against these rows,
    # so a list that drifted from the source would not be cosmetic: the widget would
    # raise "unknown column" instead of drawing.
    preview = preview_table(
        _connection_cfg(source.config, source.type), DEMO_DIRECTQUERY_TABLE, None, limit=50,
    )
    probe = pd.DataFrame(preview["rows"], columns=preview["columns"])
    type_map = detect_types(probe) if len(probe) else {}

    dataset = Dataset(
        name=DEMO_DIRECTQUERY_DATASET_NAME,
        description=DEMO_DIRECTQUERY_DATASET_DESCRIPTION,
        # No file, no row count, no size: nothing has been imported. row_count stays 0
        # exactly as the DirectQuery import path leaves it.
        filename=None, row_count=0, col_count=len(preview["columns"]), file_size=0,
        column_meta={DEMO_META_KEY: DEMO_MARKER},
        data_source_id=source.id,
        source_table=DEMO_DIRECTQUERY_TABLE,
        mode="directquery",
        org_id=org_id,
    )
    db.add(dataset)
    await db.flush()

    for col_name in preview["columns"]:
        db.add(DatasetColumn(
            dataset_id=dataset.id, name=col_name,
            dtype=type_map.get(col_name, "unknown"), stats={},
        ))

    report = Report(
        name=DEMO_DIRECTQUERY_REPORT_NAME,
        description=DEMO_DIRECTQUERY_REPORT_DESCRIPTION,
        dataset_id=dataset.id,
        org_id=org_id,
    )
    db.add(report)
    await db.flush()

    page = ReportPage(
        report_id=report.id, name="Page 1", title=DEMO_DIRECTQUERY_REPORT_NAME, position=0,
    )
    db.add(page)
    await db.flush()

    packer = _GridPacker()
    for widget_type, title, w, h, config in _directquery_specs():
        db.add(ReportWidget(
            page_id=page.id,
            widget_type=widget_type,
            title=title,
            config={**config, DEMO_META_KEY: DEMO_MARKER},
            layout=packer.place(w, h),
        ))

    await db.flush()
    return {"source": source, "dataset": dataset, "report": report}


async def remove_demo_content(db: AsyncSession, org_id: int) -> dict[str, int]:
    """Remove every trace of the demo from one org, and nothing else.

    Composed from the same per-pass cleanups the seeders run, so unloading follows
    exactly the rules loading does: every match is on the demo marker rather than a
    name, and every query is scoped to `org_id`. A user's own dataset called
    "Demo — Sales" survives this, which is the case that separates a correct
    implementation from a plausible one.

    Order mirrors the reverse of seeding. The DirectQuery pass goes first because it
    owns a report whose dataset is also its own; the import reports go next, before
    their datasets, because Dataset -> Report is ON DELETE SET NULL and dropping a
    dataset first would strand its report rather than removing it.

    Flushes rather than commits: the caller owns the transaction, as with the seeders.
    Returns what was removed, so the endpoint can report it and a test can assert it.
    """
    before_reports = len((await db.execute(
        select(Report).where(Report.org_id == org_id)
    )).scalars().all())
    before_datasets = len((await db.execute(
        select(Dataset).where(Dataset.org_id == org_id)
    )).scalars().all())
    before_sources = len((await db.execute(
        select(DataSource).where(DataSource.org_id == org_id)
    )).scalars().all())

    await _remove_existing_demo_directquery(db, org_id)
    # The use-case layer first: its relationship cleanup identifies demo
    # datasets structurally, so it has to run while those datasets still exist.
    # Imported here rather than at module scope -- demo_use_cases imports THIS
    # module for the marker and the grid packer.
    from .demo_use_cases import (_remove_demo_workspace,
                                 _remove_existing_use_cases)
    await _remove_demo_workspace(db, org_id)
    await _remove_existing_use_cases(db, org_id)
    await _remove_existing_demo_reports(db, org_id)
    await _remove_existing_demo_datasets(db, org_id)
    await db.flush()

    after_reports = len((await db.execute(
        select(Report).where(Report.org_id == org_id)
    )).scalars().all())
    after_datasets = len((await db.execute(
        select(Dataset).where(Dataset.org_id == org_id)
    )).scalars().all())
    after_sources = len((await db.execute(
        select(DataSource).where(DataSource.org_id == org_id)
    )).scalars().all())

    return {
        "datasets": before_datasets - after_datasets,
        "reports": before_reports - after_reports,
        "data_sources": before_sources - after_sources,
    }
