"""The demo must keep demonstrating the product as the product grows.

`demo_content.py` covers all 57 widget types, and a test already asserts every
one of them renders. Nothing covered the *actions* -- sharing, row-level
security, preparation, parameters, alerting -- and when this was first measured,
5 of 18 appeared anywhere in the demo content. A demo that shows every chart and
none of the platform's behaviour undersells it in exactly the way a screenshot
would.

This asserts against the SEEDED DATABASE, not against source text. Grepping the
seeder for a class name proves someone typed it; querying the org proves a user
opening the demo will actually find the feature there. The difference matters:
an import left behind by a deleted feature still greps.

The list is a deliberate inventory, not a derived one. Deriving "every feature"
from the codebase would either miss things with no obvious marker (cross-filter
modes live in a JSON blob) or drown the test in internals. A hand-kept list that
fails loudly when a feature is dropped is more honest than an automatic one that
quietly measures the wrong thing -- but it does mean ADDING a feature to the
product should add a line here, and the docstring says so on purpose.
"""
import pytest
from sqlalchemy import select

from app.models.models import (Bookmark, ColumnSecurityRule, DataAlert,
                               EmbedConfig, HierarchyNode, Organization,
                               Relationship, Report, ReportPage,
                               ReportParameter, ReportSchedule,
                               RowSecurityRule, ShareLink, User,
                               WorkspaceFolderRole, WorkspaceNode)
from app.services.demo_content import (seed_demo_datasets, seed_demo_features,
                                       seed_demo_reports,
                                       seed_demo_ux_showcase)
from app.services.demo_use_cases import (seed_demo_use_cases,
                                         seed_demo_workspace)


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, tmp_path):
    """Give every test its own upload directory.

    The demo seeder writes its CSVs to settings.upload_dir keyed by org_id, and
    org ids restart at 1 in each test file. Without this, one test file seeds
    demo_1_sales.csv and another test file deletes it on teardown -- so a test
    that passes alone fails in the full suite with EmptyDataError, which is
    exactly what happened before this fixture existed. test_demo_reports.py
    carries the same fixture for the same reason.
    """
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path / "uploads"))


@pytest.fixture
async def org_id(db_session):
    org = Organization(name="Coverage Co")
    db_session.add(org)
    await db_session.flush()
    return org.id


@pytest.fixture
async def fully_seeded(db_session, org_id):
    """Everything the seed endpoint creates, in the order it creates it.

    DirectQuery seeding is left out: it needs a live source file and is covered
    by its own tests. Every other pass runs, because the point is to check what
    a user actually gets.
    """
    datasets = await seed_demo_datasets(db_session, org_id)
    reports = await seed_demo_reports(db_session, org_id, datasets)
    await seed_demo_features(db_session, org_id, datasets, reports)
    await seed_demo_ux_showcase(db_session, org_id, datasets)
    await seed_demo_use_cases(db_session, org_id, datasets)
    await seed_demo_workspace(db_session, org_id)
    return org_id


async def _any_widget_config_has(db, org_id: int, key: str) -> bool:
    """True when some seeded widget carries this config key with a real value."""
    widgets = (await db.execute(
        select(ReportPage, Report).join(Report, ReportPage.report_id == Report.id)
        .where(Report.org_id == org_id)
    )).all()
    page_ids = [page.id for page, _ in widgets]
    if not page_ids:
        return False

    from app.models.models import ReportWidget
    rows = (await db.execute(
        select(ReportWidget).where(ReportWidget.page_id.in_(page_ids))
    )).scalars().all()
    return any((w.config or {}).get(key) for w in rows)


#: (feature, how to prove a user would find it). Row-level features are checked
#: by querying their table; widget-level ones by looking for their config key.
ROW_FEATURES = [
    ("row-level security", RowSecurityRule),
    ("column denial", ColumnSecurityRule),
    ("share links", ShareLink),
    ("embed configs", EmbedConfig),
    ("scheduled delivery", ReportSchedule),
    ("data alerts", DataAlert),
    ("report parameters", ReportParameter),
    ("dataset relationships", Relationship),
    ("data-view hierarchy", HierarchyNode),
    ("bookmarks", Bookmark),
    ("workspace folders", WorkspaceNode),
    ("workspace folder grants", WorkspaceFolderRole),
]

CONFIG_FEATURES = [
    ("cross-filter interaction", "interaction"),
    ("prep pipelines", "prep_steps"),
    ("calculated columns", "calculated_columns"),
    # Post-aggregation measures are NOT a config key: a widget's own
    # `measure_defs` is overwritten by the server by design, so its presence
    # certified a chart that drew row counts. See the dedicated test below.
    ("display rules", "display_rules"),
]


@pytest.mark.parametrize("label,model", ROW_FEATURES, ids=[f[0] for f in ROW_FEATURES])
@pytest.mark.asyncio
async def test_the_demo_shows_this_feature(label, model, db_session, fully_seeded):
    rows = (await db_session.execute(select(model))).scalars().all()
    assert rows, (
        f"the seeded demo contains no {label}. Someone opening the demo would "
        f"never see that this product has it -- add it to a use case in "
        f"services/demo_use_cases.py, or remove this line if the feature is gone."
    )


@pytest.mark.parametrize("label,key", CONFIG_FEATURES, ids=[f[0] for f in CONFIG_FEATURES])
@pytest.mark.asyncio
async def test_the_demo_uses_this_widget_feature(label, key, db_session, fully_seeded):
    assert await _any_widget_config_has(db_session, fully_seeded, key), (
        f"no seeded widget uses {label} (config key {key!r}). The demo renders "
        f"but stops demonstrating this."
    )


@pytest.mark.asyncio
async def test_the_demo_charts_a_post_aggregation_measure(db_session, fully_seeded):
    """Some seeded widget's `measure` names a measure defined on its DATASET --
    the only place the server reads measures from."""
    from app.models.models import Dataset, Report, ReportPage, ReportWidget
    rows = (await db_session.execute(
        select(ReportWidget.config, Report.dataset_id)
        .join(ReportPage, ReportPage.id == ReportWidget.page_id)
        .join(Report, Report.id == ReportPage.report_id))).all()
    measures = {d.id: {m.get("name") for m in d.measures or []}
                for d in (await db_session.execute(select(Dataset))).scalars()}
    assert any((cfg or {}).get("measure") in measures.get((cfg or {}).get("dataset_id") or rds, set())
               for cfg, rds in rows), (
        "no seeded widget charts a dataset measure. The demo renders but stops "
        "demonstrating post-aggregation measures.")


class TestIdentities:
    @pytest.mark.asyncio
    async def test_the_demo_has_two_logins_to_compare(self, db_session, fully_seeded):
        """RLS is only demonstrable with two identities: a rule nobody can be
        compared against is indistinguishable from a filter."""
        from app.services.demo_use_cases import DEMO_USER_EMAILS

        users = (await db_session.execute(
            select(User).where(User.email.in_(list(DEMO_USER_EMAILS.values())))
        )).scalars().all()
        assert len(users) == 2


class TestNothingSeededCanFire:
    """Re-asserted here, over the FULL seed rather than the use-case layer alone.

    The narrow version lives in test_demo_use_cases.py. This one would catch a
    schedule or alert seeded by any OTHER pass -- including one added later by
    someone who never read that file.
    """

    @pytest.mark.asyncio
    async def test_no_seeded_schedule_or_alert_is_ever_due(self, db_session, fully_seeded):
        from datetime import datetime

        from app.services.refresh_scheduler import is_due, schedule_is_due

        now = datetime.utcnow()
        for sched in (await db_session.execute(select(ReportSchedule))).scalars().all():
            assert schedule_is_due(sched, now) is False, (
                "a seeded schedule is due and would be RUN by refresh_scheduler")
        for alert in (await db_session.execute(select(DataAlert))).scalars().all():
            assert is_due(alert.interval_minutes, alert.last_checked_at, now) is False, (
                "a seeded alert is due and would be RUN by refresh_scheduler")
