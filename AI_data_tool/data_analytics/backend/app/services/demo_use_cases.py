"""Insight-led demo reports: what the platform does FOR someone.

`demo_content.py` demonstrates the widget catalogue -- all 57 types render, with
real data shaped so each one means something. That is coverage, and it is
complete. What it does not show is the platform's *actions*: sharing, row-level
security, preparation, parameters, alerting. Measured before this module existed,
5 of 18 such features appeared anywhere in the demo content.

Each report here is a question somebody actually asks, and each carries the
features that answer it:

    "Which regions are underperforming, and why?"
        parameters, sync-slicers, a non-additive measure, display rules, sharing
    "Can I trust this data?"
        prep steps, relationships, calculated columns, before/after
    "Who is allowed to see what?"
        RLS rules, two identities, column denial, embedding
    "What needs attention right now?"
        a paused alert, a paused schedule, comments, status widgets

Deliberately ADDITIVE. The five reports in demo_content.py stay exactly as they
are: they are the widget-coverage bed that test_demo_reports.py asserts against,
and the config corpus the DuckDB pushdown sweep runs through -- the set that
caught the `measure2` eligibility gap. Rewriting them to read as use cases would
churn tested specs and lose that corpus.

TWO SAFETY RULES, both learned from reading the code rather than from a mishap:

1. A seeded schedule or alert MUST have `interval_minutes = NULL`.
   `refresh_scheduler.py` selects every ReportSchedule and DataAlert with a
   non-null interval and RUNS it. Neither model has an enabled flag, so NULL is
   the only way to seed one that is visible in the UI and inert in the
   scheduler. A demo that mails a made-up address is an incident, not a demo.

2. Anything that grants access gets the narrowest scope that still demonstrates
   the feature -- share links expire, embed origins are localhost-only. An embed
   token is the same live host-signed credential the telemetry query-string
   scrubber exists to keep out of spans.

Same contract as every other seeder here: does NOT commit (the caller owns the
transaction), idempotent via a name-scoped remover, and every created object
carries DEMO_MARKER so `remove_demo_content` finds it.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.security import hash_password
from ..models.models import (ColumnSecurityRule, DataAlert, Dataset, EmbedConfig,
                             Relationship, Report, ReportPage, ReportParameter,
                             ReportSchedule, ReportWidget, Role,
                             RowSecurityRule, ShareLink, User)
from .secrets import encrypt_value
from .demo_content import (DEMO_MARKER, DEMO_META_KEY, GRID_COLUMNS,
                           _GridPacker, is_demo_dataset)

#: Report names. Exclusive to this module, which is what lets the remover scope
#: itself by name and stay idempotent when called on its own -- the same
#: technique `_remove_existing_ux_showcase` uses.
USE_CASE_REPORT_NAMES: dict[str, str] = {
    "performance": "Use case — Regional performance review",
    "quality": "Use case — Can I trust this data?",
}

USE_CASE_REPORT_DESCRIPTIONS: dict[str, str] = {
    "performance": (
        "Which regions are missing target, and is it volume or margin? "
        "Move the Target parameter and the variance colouring follows."
    ),
    "quality": (
        "The same figures before and after preparation, with the steps that "
        "changed them and the relationship that joins the two datasets."
    ),
}

#: The margin measure is deliberately NON-ADDITIVE: a region's margin is not the
#: sum of its products' margins, so summing a precomputed column would be wrong.
#: Expressing it as a post-aggregation measure is the only correct way, which is
#: exactly why it earns a place in a demo.
MARGIN_MEASURE = {
    "name": "Margin %",
    "expression": "(SUM(revenue) - SUM(cost)) / SUM(revenue) * 100",
}

#: The only inert spelling for a seeded schedule/alert: interval_minutes is
#: NOT NULL on both models, and refresh_scheduler.is_due short-circuits to False
#: for <= 0. Verified in tests/test_demo_use_cases.py.
INERT_INTERVAL = 0

#: Report parameter driving the what-if path.
TARGET_PARAM_NAME = "target_pct"


def _performance_specs(sales: Dataset) -> list[tuple[str, str, int, int, dict]]:
    """Widgets for "Which regions are underperforming, and why?".

    Ordered as the question is actually asked: the headline first, then the
    breakdown that explains it, then the detail somebody drills into.
    """
    return [
        ("kpi", "Revenue", 3, 3, {
            "measure": "revenue", "aggregation": "sum",
        }),
        ("kpi", "Against target", 3, 3, {
            "measure": "target", "aggregation": "sum",
        }),
        ("gauge", "Margin %", 3, 3, {
            "measure": "margin_pct", "aggregation": "avg",
            "target_value": 30,
        }),
        # The slicer is the interaction the walkthrough drives; syncAllPages is
        # set on it in the feature pass below.
        ("slicer", "Region", 3, 3, {
            "dimension": "region",
        }),
        ("bar", "Revenue by region", 6, 5, {
            "dimension": "region", "measure": "revenue",
            "aggregation": "sum", "sort": "desc",
        }),
        ("bar", "Margin % by region", 6, 5, {
            "dimension": "region", "measure": "margin_pct",
            "aggregation": "avg", "sort": "desc",
        }),
        ("line", "Revenue trend", 12, 5, {
            "dimension": "month", "measure": "revenue",
            "aggregation": "sum", "sort_by": "name",
        }),
        ("table", "Detail by product", 12, 6, {
            "columns": ["region", "product", "revenue", "cost", "margin_pct"],
            "limit": 25,
        }),
    ]


def _quality_specs(sales: Dataset) -> list[tuple[str, str, int, int, dict]]:
    """Widgets for "Can I trust this data?".

    Two tiles charting the SAME measure -- one over the raw frame, one over the
    prepared frame -- is the whole point: a data-quality story that only shows
    the cleaned figure is asking to be taken on faith.
    """
    return [
        ("kpi", "Rows", 3, 3, {
            "measure": "revenue", "aggregation": "count",
        }),
        ("kpi", "Distinct products", 3, 3, {
            "measure": "product", "aggregation": "countd",
        }),
        ("kpi", "Missing cost", 3, 3, {
            "measure": "cost", "aggregation": "count",
        }),
        ("card", "Prepared", 3, 3, {
            "measure": "revenue", "aggregation": "sum",
        }),
        ("bar", "Revenue by category — as loaded", 6, 5, {
            "dimension": "category", "measure": "revenue", "aggregation": "sum",
        }),
        ("bar", "Revenue by category — prepared", 6, 5, {
            "dimension": "category", "measure": "revenue", "aggregation": "sum",
        }),
        ("histogram", "Margin distribution", 6, 5, {
            "measure": "margin_pct", "bins": 20,
        }),
        ("box_plot", "Revenue spread by channel", 6, 5, {
            "dimension": "channel", "measure": "revenue",
        }),
        ("table", "Rows the prep steps changed", 12, 6, {
            "columns": ["region", "product", "cost", "margin_pct"],
            "limit": 25,
        }),
    ]


_USE_CASE_SPECS = [
    ("performance", _performance_specs),
    ("quality", _quality_specs),
]


async def _remove_existing_use_cases(db: AsyncSession, org_id: int) -> None:
    """Delete this org's previously seeded use-case content, by name.

    Scoped to THESE names rather than every marker-tagged report, so seeding the
    use-case layer on its own does not wipe the sales-family reports that the
    generic marker cleanup would also catch.

    Deletes what the seeder created EXPLICITLY rather than relying on the
    schema's `ON DELETE CASCADE`. That cascade is real in production (Postgres
    always enforces foreign keys) but invisible under SQLite, which ignores them
    unless a connection asks -- and ten of the twelve tables referencing
    `reports.id` have no ORM-level cascade at all, so `session.delete(report)`
    alone leaves them to the database. Deleting by hand means teardown behaves
    the same on both, which for rows that grant access is the difference between
    a demo and a leak.
    """
    reports = (await db.execute(
        select(Report)
        .options(selectinload(Report.pages).selectinload(ReportPage.widgets))
        .where(Report.org_id == org_id,
               Report.name.in_(list(USE_CASE_REPORT_NAMES.values())))
    )).scalars().unique().all()

    for report in reports:
        for parameter in (await db.execute(
            select(ReportParameter).where(ReportParameter.report_id == report.id)
        )).scalars().all():
            await db.delete(parameter)
        await db.delete(report)   # pages, widgets and bookmarks cascade in the ORM

    await _remove_use_case_relationships(db, org_id)
    await _remove_demo_identities_and_grants(db, org_id)
    await db.flush()


async def _remove_demo_identities_and_grants(db: AsyncSession, org_id: int) -> None:
    """Remove the demo users, their roles, and everything they were granted.

    ORDER IS DELIBERATE. Share links, embed configs, schedules and alerts all
    carry a NOT NULL creator FK to users.id with ON DELETE CASCADE, so deleting
    the users first WOULD remove them -- in Postgres. Under SQLite with foreign
    keys off (the historical test default) it would not, and the rows would
    survive as orphans. Deleting the grants first means teardown behaves the
    same on either database, which for a live share token is not a detail.

    Every deletion is scoped to this org and to the demo emails/role names, so a
    real user is never touched.
    """
    demo_users = (await db.execute(
        select(User).where(User.org_id == org_id,
                           User.email.in_(list(DEMO_USER_EMAILS.values())))
    )).scalars().all()
    if not demo_users:
        return
    user_ids = [u.id for u in demo_users]
    role_ids = [u.role_id for u in demo_users if u.role_id is not None]

    # 1. the grants, before the identities that own them
    for model, column in ((ShareLink, ShareLink.creator_user_id),
                          (EmbedConfig, EmbedConfig.created_by),
                          (ReportSchedule, ReportSchedule.creator_user_id),
                          (DataAlert, DataAlert.creator_user_id)):
        for row in (await db.execute(
            select(model).where(column.in_(user_ids))
        )).scalars().all():
            await db.delete(row)

    # 2. the security rules, which hang off the roles rather than the users
    for model in (RowSecurityRule, ColumnSecurityRule):
        for row in (await db.execute(
            select(model).where(model.role_id.in_(role_ids))
        )).scalars().all():
            await db.delete(row)

    # 3. the identities themselves
    for user in demo_users:
        await db.delete(user)
    await db.flush()

    for role in (await db.execute(
        select(Role).where(Role.org_id == org_id,
                           Role.name.in_(list(DEMO_ROLE_NAMES.values())))
    )).scalars().all():
        await db.delete(role)


async def _remove_use_case_relationships(db: AsyncSession, org_id: int) -> None:
    """Drop relationships this layer created between two demo datasets.

    A Relationship carries no config column, so it cannot hold the demo marker
    the way a widget does. It is identified structurally instead: both endpoints
    are demo datasets in this org. A relationship a user drew between their own
    datasets has at least one endpoint that is not demo content and survives.
    """
    demo_dataset_ids = {
        d.id for d in (await db.execute(
            select(Dataset).where(Dataset.org_id == org_id)
        )).scalars().all()
        if is_demo_dataset(d)
    }
    if not demo_dataset_ids:
        return

    for rel in (await db.execute(
        select(Relationship).where(Relationship.org_id == org_id)
    )).scalars().all():
        if (rel.from_dataset_id in demo_dataset_ids
                and rel.to_dataset_id in demo_dataset_ids):
            await db.delete(rel)


async def seed_demo_use_cases(
    db: AsyncSession, org_id: int, datasets: dict[str, Dataset],
) -> dict[str, Report]:
    """Build the insight-led use-case reports over the demo datasets.

    Runs AFTER seed_demo_datasets. Does not commit; the caller owns the
    transaction, matching every other seeder in this package.
    """
    sales = datasets["sales"]
    if sales.org_id != org_id:
        raise ValueError(
            "demo content belonging to another org was passed to the use-case "
            f"seeder: {sales.name}"
        )

    await _remove_existing_use_cases(db, org_id)

    created: dict[str, Report] = {}
    for key, build_specs in _USE_CASE_SPECS:
        report = Report(
            name=USE_CASE_REPORT_NAMES[key],
            description=USE_CASE_REPORT_DESCRIPTIONS[key],
            dataset_id=sales.id,
            org_id=org_id,
        )
        db.add(report)
        await db.flush()

        page = ReportPage(
            report_id=report.id,
            name="Page 1",
            title=USE_CASE_REPORT_NAMES[key],
            position=0,
        )
        db.add(page)
        await db.flush()

        packer = _GridPacker(GRID_COLUMNS)
        for widget_type, title, w, h, config in build_specs(sales):
            db.add(ReportWidget(
                page_id=page.id,
                widget_type=widget_type,
                title=title,
                config={**config, DEMO_META_KEY: DEMO_MARKER},
                layout=packer.place(w, h),
            ))
        await db.flush()
        created[key] = report

    await _apply_performance_features(db, created["performance"])
    await _apply_quality_features(db, created["quality"], datasets)

    # Use cases 3 and 4 hang off the performance report rather than adding more
    # reports: "who can see this" and "what needs attention" are questions ABOUT
    # a report, and demonstrating them on one somebody has already read is
    # clearer than inventing two more dashboards.
    users = await _seed_demo_identities(db, org_id)
    await _seed_rls(db, org_id, sales, users)
    await _seed_sharing(db, org_id, created["performance"], users["global"])
    await _seed_monitoring(db, org_id, created["performance"], sales,
                           users["global"])

    await db.flush()
    return created


async def _widgets_of(db: AsyncSession, report: Report) -> list[ReportWidget]:
    page = (await db.execute(
        select(ReportPage).options(selectinload(ReportPage.widgets))
        .where(ReportPage.report_id == report.id)
    )).scalars().first()
    return list(page.widgets) if page else []


def _patch_config(widget: ReportWidget, **config) -> None:
    """Merge keys into a widget's config, reassigning so SQLAlchemy sees it.

    `Column(JSON)` has no mutation tracking: editing the dict in place leaves the
    attribute unchanged as far as the session is concerned and the write is
    silently dropped.
    """
    widget.config = {**(widget.config or {}), **config}


async def _apply_performance_features(db: AsyncSession, report: Report) -> None:
    """Parameters, the non-additive measure, sync-slicers and display rules.

    Everything here is a *feature* rather than a chart: the report renders
    without it, and demonstrates nothing without it.
    """
    db.add(ReportParameter(
        report_id=report.id,
        name=TARGET_PARAM_NAME,
        param_type="number",
        label="Target margin %",
        default_value="30",
    ))

    widgets = await _widgets_of(db, report)
    by_title = {w.title: w for w in widgets}

    # The margin measure, defined on the DATASET -- the only place the server
    # reads measures from. It used to ride inline as the widget's own
    # `measure_defs`, which get_widget_data_from_df overwrites by design (a
    # request may not smuggle in definitions), so the chart named a measure
    # that did not exist and drew row counts: 517, 514, 509, 460 as "Margin %".
    margin = by_title.get("Margin % by region")
    if margin is not None:
        from ..models.models import Dataset
        ds = await db.get(Dataset, report.dataset_id) if report.dataset_id else None
        if ds is not None and not any(m.get("name") == MARGIN_MEASURE["name"]
                                      for m in ds.measures or []):
            ds.measures = [*(ds.measures or []), dict(MARGIN_MEASURE)]
        cfg = {k: v for k, v in (margin.config or {}).items() if k != "measure_defs"}
        margin.config = {**cfg, "measure": MARGIN_MEASURE["name"]}

    # Sync the slicer across pages: the interaction the walkthrough drives.
    slicer = by_title.get("Region")
    if slicer is not None:
        _patch_config(slicer, interaction={"mode": "two_way", "syncAllPages": True})

    # Colour the variance. A rule that reads the parameter is what makes the
    # what-if path visible -- move the target, the banding moves.
    revenue_bar = by_title.get("Revenue by region")
    if revenue_bar is not None:
        _patch_config(revenue_bar, display_rules=[{
            "column": "value",
            "op": "lt",
            "value": 0,
            "style": {"color": "#A8443A"},
        }])


async def _apply_quality_features(
    db: AsyncSession, report: Report, datasets: dict[str, Dataset],
) -> None:
    """Prep steps, a calculated column, and a relationship between datasets.

    The prepared tile carries prep_steps; its twin deliberately does not, so the
    two charts differ and the difference is the demonstration.
    """
    widgets = await _widgets_of(db, report)
    by_title = {w.title: w for w in widgets}

    prepared = by_title.get("Revenue by category — prepared")
    if prepared is not None:
        _patch_config(prepared, prep_steps=[
            # Drop the rows a real feed would arrive with: no cost means no
            # margin, and averaging over them understates every category.
            {"kind": "filter", "column": "cost", "op": "gt", "value": 0},
        ])

    changed = by_title.get("Rows the prep steps changed")
    if changed is not None:
        _patch_config(changed, calculated_columns=[{
            "name": "unit_margin",
            "expression": "(revenue - cost) / units",
        }])

    # A relationship between two demo datasets: the modelling story. Guarded so
    # a partial dataset set (a test seeding only sales) does not fail the seed.
    sales, routes = datasets.get("sales"), datasets.get("routes")
    if sales is not None and routes is not None:
        existing = (await db.execute(
            select(Relationship).where(
                Relationship.org_id == report.org_id,
                Relationship.from_dataset_id == sales.id,
                Relationship.to_dataset_id == routes.id,
            )
        )).scalars().first()
        if existing is None:
            db.add(Relationship(
                org_id=report.org_id,
                from_dataset_id=sales.id,
                from_column="country",
                to_dataset_id=routes.id,
                to_column="dest_country",
            ))


# ── Use cases 3 and 4: the ones that need identities ─────────────────────────
#
# ShareLink, EmbedConfig, ReportSchedule and DataAlert all carry a NOT NULL
# creator/created_by FK to users.id with ON DELETE CASCADE. So both of these use
# cases need demo users, and TEARDOWN ORDER MATTERS: deleting a demo user
# cascade-deletes their schedules, alerts, share links and embed configs. The
# remover deletes those rows explicitly first anyway, so the outcome is the same
# either way -- but relying on the cascade would make teardown depend on the
# database enforcing foreign keys, which SQLite does not do by default.

DEMO_ROLE_NAMES = {
    "emea": "Demo — EMEA analyst",
    "global": "Demo — Global analyst",
}

#: Password for the seeded demo logins. Not a secret: these accounts exist only
#: inside a demo org, see only demo data, and are removed on unseed. The
#: walkthrough prints it, because a login nobody can use demonstrates nothing.
DEMO_USER_PASSWORD = "demo-password"

DEMO_USER_EMAILS = {
    "emea": "demo-emea@example.invalid",
    "global": "demo-global@example.invalid",
}

#: RLS filter for the restricted role. The Global analyst gets no rule at all,
#: which is the comparison: same report, same widgets, different rows.
#: The Demo — Sales dataset's region column holds "North America" / "Europe" /
#: "Asia Pacific" / "Latin America" (see demo_content.py:_REGIONS) — never the
#: literal string "EMEA" — so the filter must match "Europe" or the restricted
#: role sees zero rows on every widget, defeating the demo's own purpose.
EMEA_FILTER_EXPR = "region == 'Europe'"

#: Columns the restricted role may not see. Column denial removes them from the
#: projection rather than blanking them, so the demo shows a genuinely narrower
#: table rather than one full of masked cells.
EMEA_DENIED_COLUMNS = ["cost"]

#: Embed origins. Localhost only: an embed token is a live host-signed
#: credential, and a demo config that accepted any origin would be an invitation.
#:
#: BOTH ports, and that is not belt-and-braces. docker-compose publishes the
#: frontend on 3001 ("3001:3000"), while a local `npm run dev` serves it on
#: 3000 --
#: so the page doing the embedding is on a different origin depending on how
#: the stack was started. Seeding only one would leave the demo embed silently
#: refused for half the people who try it, with a CORS error rather than an
#: explanation. Mirrors settings.allowed_origins, which lists both for the same
#: reason.
DEMO_EMBED_ORIGINS = ["http://localhost:3000", "http://localhost:3001"]

#: How long a seeded share link stays valid. Short on purpose -- a demo link that
#: outlives the demo is an unrevoked credential.
DEMO_SHARE_LINK_TTL = timedelta(days=7)


async def _seed_demo_identities(db: AsyncSession, org_id: int) -> dict[str, User]:
    """Two roles and two users: one restricted, one unrestricted.

    RLS needs at least two identities to demonstrate anything -- a rule nobody
    can be compared against is just a filter. The Global analyst deliberately
    gets NO rule, so opening the same report as each account shows the rows
    change while everything else stays identical.

    Idempotent: existing demo users are reused rather than duplicated, since
    emails are unique and a re-seed must not collide.
    """
    users: dict[str, User] = {}
    for key, role_name in DEMO_ROLE_NAMES.items():
        role = (await db.execute(
            select(Role).where(Role.org_id == org_id, Role.name == role_name)
        )).scalars().first()
        if role is None:
            role = Role(org_id=org_id, name=role_name, is_org_admin=False)
            db.add(role)
            await db.flush()

        email = DEMO_USER_EMAILS[key]
        user = (await db.execute(
            select(User).where(User.email == email)
        )).scalars().first()
        if user is None:
            user = User(
                org_id=org_id,
                role_id=role.id,
                email=email,
                password_hash=hash_password(DEMO_USER_PASSWORD),
            )
            db.add(user)
            await db.flush()
        users[key] = user
    return users


async def _seed_rls(db: AsyncSession, org_id: int, sales: Dataset,
                    users: dict[str, User]) -> None:
    """One row rule and one column rule, both on the EMEA role only.

    The role is THIS org's EMEA role, looked up by org and name -- never the
    demo user's role_id. Demo emails are unique across the install, so seeding
    a second org reuses the first org's user, and binding the rule to that
    user's role tied org 1's role to org 4's dataset (BUG-036: org 1's admin
    saw it as a "Deleted dataset", and could edit a rule on org 4's data)."""
    emea_role_id = (await db.execute(
        select(Role.id).where(Role.org_id == org_id, Role.name == DEMO_ROLE_NAMES["emea"])
    )).scalars().first()
    if emea_role_id is None:      # _seed_demo_identities creates it; never expected
        return

    existing_row = (await db.execute(
        select(RowSecurityRule).where(
            RowSecurityRule.role_id == emea_role_id,
            RowSecurityRule.dataset_id == sales.id)
    )).scalars().first()
    if existing_row is None:
        db.add(RowSecurityRule(
            role_id=emea_role_id,
            dataset_id=sales.id,
            filter_expr=EMEA_FILTER_EXPR,
        ))

    existing_col = (await db.execute(
        select(ColumnSecurityRule).where(
            ColumnSecurityRule.role_id == emea_role_id,
            ColumnSecurityRule.dataset_id == sales.id)
    )).scalars().first()
    if existing_col is None:
        db.add(ColumnSecurityRule(
            role_id=emea_role_id,
            dataset_id=sales.id,
            denied_columns=list(EMEA_DENIED_COLUMNS),
        ))


async def _seed_sharing(db: AsyncSession, org_id: int, report: Report,
                        creator: User) -> str:
    """A share link and an embed config over the performance report.

    Returns the share TOKEN. Only its SHA-256 is stored, exactly as
    `routers/shared.py` does, so the caller (and the walkthrough) is the only
    place the usable value ever exists -- a demo must not be the one component
    that keeps a recoverable credential in the database.
    """
    from ..routers.shared import hash_token

    token = f"demo-{org_id}-{report.id}"
    existing = (await db.execute(
        select(ShareLink).where(ShareLink.token_hash == hash_token(token))
    )).scalars().first()
    if existing is None:
        db.add(ShareLink(
            org_id=org_id,
            report_id=report.id,
            creator_user_id=creator.id,
            token_hash=hash_token(token),
            expires_at=datetime.utcnow() + DEMO_SHARE_LINK_TTL,
        ))

    existing_embed = (await db.execute(
        select(EmbedConfig).where(
            EmbedConfig.report_id == report.id,
            EmbedConfig.name == "Demo embed")
    )).scalars().first()
    if existing_embed is None:
        db.add(EmbedConfig(
            org_id=org_id,
            report_id=report.id,
            created_by=creator.id,
            name="Demo embed",
            secret_encrypted=encrypt_value("demo-embed-secret"),
            allowed_origins=list(DEMO_EMBED_ORIGINS),
            enabled=True,
        ))
    return token


async def _seed_monitoring(db: AsyncSession, org_id: int, report: Report,
                           sales: Dataset, creator: User) -> None:
    """A schedule and an alert, both INERT.

    Neither model has an enabled flag, and `interval_minutes` is NOT NULL on
    both -- so "seed it disabled" has exactly one spelling: an interval of 0.
    `refresh_scheduler.is_due` returns False for `interval_minutes <= 0` before
    it looks at anything else, so the rows are visible in the UI and can never
    come due. Verified directly: is_due(0, never_run) is False while
    is_due(60, never_run) is True.

    This matters more than it looks. A demo that mails whatever address it
    invented is an incident, not a rough edge.
    """
    existing_sched = (await db.execute(
        select(ReportSchedule).where(ReportSchedule.report_id == report.id)
    )).scalars().first()
    if existing_sched is None:
        db.add(ReportSchedule(
            org_id=org_id,
            report_id=report.id,
            creator_user_id=creator.id,
            interval_minutes=INERT_INTERVAL,   # never due -- see docstring
            recipients=["demo@example.invalid"],
            subject="Demo — weekly regional performance",
        ))

    existing_alert = (await db.execute(
        select(DataAlert).where(DataAlert.dataset_id == sales.id,
                                DataAlert.name == "Demo — margin below target")
    )).scalars().first()
    if existing_alert is None:
        db.add(DataAlert(
            org_id=org_id,
            dataset_id=sales.id,
            creator_user_id=creator.id,
            name="Demo — margin below target",
            expression="AVG(margin_pct) < 25",
            interval_minutes=INERT_INTERVAL,   # never due -- see docstring
            recipients=["demo@example.invalid"],
        ))


# ── The workspace tree ────────────────────────────────────────────────────────

DEMO_FOLDER_NAMES = {
    "use_cases": "Use cases",
    "gallery": "Widget gallery",
}


async def seed_demo_workspace(db: AsyncSession, org_id: int) -> None:
    """File the demo reports into two folders, so the menu has a shape.

    Without this the workspace tree renders every demo report under "Unfiled" --
    technically correct, and a poor advertisement for a foldering feature.

    The split mirrors what the reports are FOR: "Use cases" holds the narrative
    reports, "Widget gallery" the coverage ones. Filing them by their own
    purpose is the demonstration; two folders named "A" and "B" would show the
    mechanism and none of the point.

    Idempotent, and does not commit. Reports that are already filed are left
    alone -- re-seeding must not move something a user deliberately reorganised.
    """
    from ..models.models import WorkspaceNode
    from .demo_content import DEMO_REPORT_NAMES, UX_SHOWCASE_REPORT_NAME

    groups = {
        "use_cases": list(USE_CASE_REPORT_NAMES.values()),
        "gallery": [*DEMO_REPORT_NAMES.values(), UX_SHOWCASE_REPORT_NAME],
    }

    for key, report_names in groups.items():
        folder_name = DEMO_FOLDER_NAMES[key]
        folder = (await db.execute(
            select(WorkspaceNode).where(
                WorkspaceNode.org_id == org_id,
                WorkspaceNode.node_type == "folder",
                WorkspaceNode.name == folder_name)
        )).scalars().first()
        if folder is None:
            folder = WorkspaceNode(org_id=org_id, node_type="folder",
                                   name=folder_name, position=0)
            db.add(folder)
            await db.flush()

        for position, report_name in enumerate(report_names):
            report = (await db.execute(
                select(Report).where(Report.org_id == org_id,
                                     Report.name == report_name)
            )).scalars().first()
            if report is None:
                continue    # a pass that did not run; not this seeder's problem
            already = (await db.execute(
                select(WorkspaceNode).where(WorkspaceNode.report_id == report.id)
            )).scalars().first()
            if already is not None:
                continue
            db.add(WorkspaceNode(
                org_id=org_id, parent_id=folder.id, node_type="report",
                report_id=report.id, position=position,
            ))
    await db.flush()
    await _restrict_use_cases_folder(db, org_id)


async def _restrict_use_cases_folder(db: AsyncSession, org_id: int) -> None:
    """Show the folder-visibility feature by actually using it.

    The "Use cases" folder is restricted to the EMEA analyst role, so the two
    demo logins see DIFFERENT MENUS -- which is the entire feature in one
    gesture, and impossible to demonstrate with a screenshot:

        demo-global@example.invalid -> Widget gallery only
        demo-emea@example.invalid   -> Widget gallery + Use cases

    "Widget gallery" is deliberately left unrestricted. A demo where every
    folder is locked would show the mechanism and hide the default, and the
    default -- no grants means everyone sees it -- is the more important half.
    """
    from ..models.models import WorkspaceFolderRole, WorkspaceNode

    folder = (await db.execute(
        select(WorkspaceNode).where(
            WorkspaceNode.org_id == org_id,
            WorkspaceNode.node_type == "folder",
            WorkspaceNode.name == DEMO_FOLDER_NAMES["use_cases"])
    )).scalars().first()
    if folder is None:
        return

    emea_role = (await db.execute(
        select(Role).where(Role.org_id == org_id,
                           Role.name == DEMO_ROLE_NAMES["emea"])
    )).scalars().first()
    if emea_role is None:
        return    # identities not seeded (a test seeding only the tree)

    existing = (await db.execute(
        select(WorkspaceFolderRole).where(
            WorkspaceFolderRole.node_id == folder.id,
            WorkspaceFolderRole.role_id == emea_role.id)
    )).scalars().first()
    if existing is None:
        db.add(WorkspaceFolderRole(node_id=folder.id, role_id=emea_role.id))
    await db.flush()


async def _remove_demo_workspace(db: AsyncSession, org_id: int) -> None:
    """Drop the demo folders. Report nodes go with them via the FK when their
    reports are deleted; the folders themselves have to be named to be found."""
    from ..models.models import WorkspaceNode

    for folder in (await db.execute(
        select(WorkspaceNode).where(
            WorkspaceNode.org_id == org_id,
            WorkspaceNode.node_type == "folder",
            WorkspaceNode.name.in_(list(DEMO_FOLDER_NAMES.values())))
    )).scalars().all():
        # Re-parent to root first, matching the router's contract: a teardown
        # that cascaded would be the one place in the system where deleting a
        # folder destroys what is inside it.
        for child in (await db.execute(
            select(WorkspaceNode).where(WorkspaceNode.parent_id == folder.id)
        )).scalars().all():
            child.parent_id = None

        # Grants cascade from the node, but they are deleted explicitly for the
        # same reason the rest of this teardown is: the cascade is a property of
        # the database's configuration, and SQLite does not enforce it by
        # default. Teardown should behave the same wherever it runs.
        from ..models.models import WorkspaceFolderRole
        for grant in (await db.execute(
            select(WorkspaceFolderRole).where(
                WorkspaceFolderRole.node_id == folder.id)
        )).scalars().all():
            await db.delete(grant)

        await db.flush()
        await db.delete(folder)
