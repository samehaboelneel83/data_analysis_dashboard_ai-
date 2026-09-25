"""The insight-led use-case demo layer: seeds, and unseeds completely.

Two properties, and the second matters more than the first:

  1. Seeding produces the reports, with the FEATURES that make them use cases
     rather than more charts -- a parameter, a non-additive measure, prep steps,
     a relationship. A report that renders but demonstrates nothing has failed.

  2. Unseeding leaves nothing. Every object this layer creates must be removable,
     and the test asserts per type rather than counting rows. A leaked share link
     or demo user is a live credential, not clutter -- which is why teardown is
     tested before the layer grows to include either.

Also pinned here: a seeded schedule or alert must never be RUNNABLE.
`refresh_scheduler` selects every ReportSchedule/DataAlert with a non-null
`interval_minutes` and runs it, and neither model has an enabled flag, so NULL is
the only inert seed. Nothing in this layer creates one yet; the guard is written
now so the use case that adds them cannot skip it.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.models import (Organization, Relationship, Report, ReportPage,
                               ReportParameter, ReportWidget)
from app.services.demo_content import (DEMO_MARKER, DEMO_META_KEY,
                                       seed_demo_datasets)
from app.services.demo_use_cases import (MARGIN_MEASURE, TARGET_PARAM_NAME,
                                         USE_CASE_REPORT_NAMES,
                                         _remove_existing_use_cases,
                                         seed_demo_use_cases)


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


@pytest_asyncio.fixture
async def org_id(db_session):
    """A REAL Organization row, not a bare integer.

    Production seeding always runs inside an org (`current_user.org_id`),
    and every demo row carries `org_id` as a foreign key. Passing an id that no
    organization owns only works while the database is not enforcing foreign
    keys -- true of SQLite by default, never true of the Postgres this runs on.
    """
    org = Organization(name="Demo Co")
    db_session.add(org)
    await db_session.flush()
    return org.id


@pytest_asyncio.fixture
async def seeded(db_session, org_id):
    datasets = await seed_demo_datasets(db_session, org_id)
    reports = await seed_demo_use_cases(db_session, org_id, datasets)
    return {"datasets": datasets, "reports": reports}


async def _widgets(db, report):
    page = (await db.execute(
        select(ReportPage).where(ReportPage.report_id == report.id)
    )).scalars().first()
    return (await db.execute(
        select(ReportWidget).where(ReportWidget.page_id == page.id)
    )).scalars().all()


class TestItSeeds:
    @pytest.mark.asyncio
    async def test_both_use_case_reports_are_created(self, org_id, seeded):
        assert set(seeded["reports"]) == {"performance", "quality"}

    @pytest.mark.asyncio
    async def test_every_widget_carries_the_demo_marker(self, org_id, db_session, seeded):
        """Teardown finds reports through this marker on their widgets. A widget
        without it makes its whole report unremovable."""
        for report in seeded["reports"].values():
            widgets = await _widgets(db_session, report)
            assert widgets, f"{report.name} has no widgets"
            for w in widgets:
                assert (w.config or {}).get(DEMO_META_KEY) == DEMO_MARKER, (
                    f"{report.name} / {w.title} is not marked as demo content")

    @pytest.mark.asyncio
    async def test_seeding_twice_leaves_one_copy(self, org_id, db_session):
        """Idempotence, the same contract every seeder in this package keeps."""
        datasets = await seed_demo_datasets(db_session, org_id)
        await seed_demo_use_cases(db_session, org_id, datasets)
        await seed_demo_use_cases(db_session, org_id, datasets)

        for name in USE_CASE_REPORT_NAMES.values():
            found = (await db_session.execute(
                select(Report).where(Report.org_id == org_id, Report.name == name)
            )).scalars().all()
            assert len(found) == 1, f"{name} was seeded {len(found)} times"

    @pytest.mark.asyncio
    async def test_it_refuses_datasets_from_another_org(self, org_id, db_session):
        datasets = await seed_demo_datasets(db_session, org_id)
        datasets["sales"].org_id = org_id + 99
        with pytest.raises(ValueError, match="another org"):
            await seed_demo_use_cases(db_session, org_id + 1, datasets)


class TestTheFeaturesThatMakeItAUseCase:
    """Without these the reports are just more charts."""

    @pytest.mark.asyncio
    async def test_the_target_parameter_exists(self, org_id, db_session, seeded):
        params = (await db_session.execute(
            select(ReportParameter).where(
                ReportParameter.report_id == seeded["reports"]["performance"].id)
        )).scalars().all()
        assert [p.name for p in params] == [TARGET_PARAM_NAME]
        assert params[0].default_value == "30"

    @pytest.mark.asyncio
    async def test_margin_is_a_post_aggregation_measure(self, org_id, db_session, seeded):
        """A region's margin is NOT the sum of its products' margins. Summing a
        precomputed column would be wrong, so this must be a measure."""
        from app.models.models import Dataset
        from app.services.widget_data import get_widget_data
        report = seeded["reports"]["performance"]
        widgets = await _widgets(db_session, report)
        margin = next(w for w in widgets if w.title == "Margin % by region")
        ds = await db_session.get(Dataset, report.dataset_id)
        # On the DATASET, where the server reads measures from. This test used
        # to assert the widget's own `measure_defs` -- which the server
        # overwrites by design, so it passed while the chart drew row counts.
        assert MARGIN_MEASURE["name"] in [m["name"] for m in ds.measures or []]
        assert "measure_defs" not in margin.config
        assert "SUM(revenue)" in MARGIN_MEASURE["expression"]
        # ...and the chart computes margins, not counts: percentages, each
        # under 100, where the old wiring drew hundreds of rows per region.
        result = get_widget_data(ds.filename, margin.config, widget_type=margin.widget_type,
                                 measures=ds.measures, use_cache=False)
        assert result["type"] == "series", result
        values = [r["value"] for r in result["rows"]]
        assert values and all(0 < v < 100 for v in values), values

    @pytest.mark.asyncio
    async def test_the_slicer_syncs_across_pages(self, org_id, db_session, seeded):
        widgets = await _widgets(db_session, seeded["reports"]["performance"])
        slicer = next(w for w in widgets if w.widget_type == "slicer")
        assert slicer.config["interaction"]["syncAllPages"] is True

    @pytest.mark.asyncio
    async def test_only_the_prepared_tile_has_prep_steps(self, org_id, db_session, seeded):
        """The two tiles chart the same measure; the difference between them IS
        the demonstration. If both had prep steps there would be nothing to see."""
        widgets = await _widgets(db_session, seeded["reports"]["quality"])
        prepared = next(w for w in widgets
                        if w.title == "Revenue by category — prepared")
        raw = next(w for w in widgets
                   if w.title == "Revenue by category — as loaded")
        assert prepared.config.get("prep_steps")
        assert not raw.config.get("prep_steps")

    @pytest.mark.asyncio
    async def test_a_relationship_joins_two_demo_datasets(self, org_id, db_session, seeded):
        rels = (await db_session.execute(
            select(Relationship).where(Relationship.org_id == org_id)
        )).scalars().all()
        assert rels, "the modelling story needs a relationship"
        assert rels[0].from_column == "country"
        assert rels[0].to_column == "dest_country"


class TestItUnseeds:
    """The property that matters most: nothing is left behind."""

    @pytest.mark.asyncio
    async def test_removal_leaves_no_use_case_reports(self, org_id, db_session, seeded):
        await _remove_existing_use_cases(db_session, org_id)
        for name in USE_CASE_REPORT_NAMES.values():
            found = (await db_session.execute(
                select(Report).where(Report.org_id == org_id, Report.name == name)
            )).scalars().all()
            assert not found, f"{name} survived removal"

    @pytest.mark.asyncio
    async def test_removal_takes_the_parameters_with_it(self, org_id, db_session, seeded):
        """Parameters hang off the report by FK; if the cascade is ever removed
        this catches the orphan rather than leaving it to accumulate."""
        report_id = seeded["reports"]["performance"].id
        await _remove_existing_use_cases(db_session, org_id)
        params = (await db_session.execute(
            select(ReportParameter).where(ReportParameter.report_id == report_id)
        )).scalars().all()
        assert not params, "report parameters outlived their report"

    @pytest.mark.asyncio
    async def test_removal_takes_the_widgets_with_it(self, org_id, db_session, seeded):
        page_ids = []
        for report in seeded["reports"].values():
            page = (await db_session.execute(
                select(ReportPage).where(ReportPage.report_id == report.id)
            )).scalars().first()
            page_ids.append(page.id)

        await _remove_existing_use_cases(db_session, org_id)
        left = (await db_session.execute(
            select(ReportWidget).where(ReportWidget.page_id.in_(page_ids))
        )).scalars().all()
        assert not left, "widgets outlived their report"

    @pytest.mark.asyncio
    async def test_it_does_not_touch_a_users_own_report(self, org_id, db_session, seeded):
        """A user is entitled to a report named like ours. Removal is scoped to
        the names this module owns, so anything else must survive -- the case
        that separates a correct implementation from a plausible one."""
        mine = Report(name="My own analysis", org_id=org_id)
        db_session.add(mine)
        await db_session.flush()

        await _remove_existing_use_cases(db_session, org_id)
        still = (await db_session.execute(
            select(Report).where(Report.id == mine.id)
        )).scalars().first()
        assert still is not None, "removal deleted a report it does not own"


class TestScheduledObjectsAreInert:
    """Guard written before the use case that needs it.

    `refresh_scheduler.py` selects every ReportSchedule and DataAlert with a
    non-null `interval_minutes` and runs it. Neither model has an enabled flag.
    Any such row this layer seeds must therefore have a NULL interval -- visible
    in the UI, invisible to the scheduler.
    """

    @pytest.mark.asyncio
    async def test_no_runnable_schedule_or_alert_is_seeded(self, org_id, db_session, seeded):
        from app.models.models import DataAlert, ReportSchedule

        for model in (ReportSchedule, DataAlert):
            rows = (await db_session.execute(
                select(model).where(model.org_id == org_id)
            )).scalars().all()
            runnable = [r for r in rows if (r.interval_minutes or 0) > 0]
            assert not runnable, (
                f"{model.__name__} seeded with a positive interval_minutes WILL "
                "come due and be run by refresh_scheduler -- a demo must not "
                "send mail. Seed it with interval_minutes=0."
            )


class TestThePublicTeardownPath:
    """`remove_demo_content` is what the DELETE /demo/seed endpoint calls.

    Testing only `_remove_existing_use_cases` would verify that the remover I
    wrote works while saying nothing about whether anything calls it -- which is
    exactly how a layer ends up seeded by the endpoint and never cleaned up by
    it.
    """

    @pytest.mark.asyncio
    async def test_it_removes_the_use_case_reports(self, org_id, db_session, seeded):
        from app.services.demo_content import remove_demo_content

        await remove_demo_content(db_session, org_id)
        for name in USE_CASE_REPORT_NAMES.values():
            found = (await db_session.execute(
                select(Report).where(Report.org_id == org_id, Report.name == name)
            )).scalars().all()
            assert not found, f"{name} survived remove_demo_content"

    @pytest.mark.asyncio
    async def test_it_removes_the_relationship(self, org_id, db_session, seeded):
        """A Relationship has no config column, so it cannot carry the demo
        marker the marker-based cleanup looks for. It is removed structurally --
        both endpoints being demo datasets -- and that only happens if this
        layer's remover is actually wired in."""
        from app.services.demo_content import remove_demo_content

        await remove_demo_content(db_session, org_id)
        rels = (await db_session.execute(
            select(Relationship).where(Relationship.org_id == org_id)
        )).scalars().all()
        assert not rels, "the demo relationship outlived the demo"

    @pytest.mark.asyncio
    async def test_it_leaves_no_orphaned_parameters(self, org_id, db_session, seeded):
        report_ids = [r.id for r in seeded["reports"].values()]
        from app.services.demo_content import remove_demo_content

        await remove_demo_content(db_session, org_id)
        params = (await db_session.execute(
            select(ReportParameter).where(ReportParameter.report_id.in_(report_ids))
        )).scalars().all()
        assert not params, "report parameters outlived remove_demo_content"


class TestIdentitiesAndGrants:
    """Use cases 3 and 4: RLS, sharing, and monitoring.

    Everything here creates a row that grants something -- a login, a share
    token, an embed secret. Each one is asserted to exist AND to disappear.
    """

    @pytest.mark.asyncio
    async def test_two_demo_identities_exist(self, org_id, db_session, seeded):
        from app.models.models import User
        from app.services.demo_use_cases import DEMO_USER_EMAILS

        users = (await db_session.execute(
            select(User).where(User.email.in_(list(DEMO_USER_EMAILS.values())))
        )).scalars().all()
        assert len(users) == 2, "RLS needs two identities to compare"

    @pytest.mark.asyncio
    async def test_only_the_restricted_role_has_an_rls_rule(self, org_id, db_session, seeded):
        """The comparison IS the demonstration: same report, same widgets, one
        role sees fewer rows. A rule on both roles would show nothing."""
        from app.models.models import Role, RowSecurityRule
        from app.services.demo_use_cases import DEMO_ROLE_NAMES, EMEA_FILTER_EXPR

        rules = (await db_session.execute(select(RowSecurityRule))).scalars().all()
        assert len(rules) == 1
        assert rules[0].filter_expr == EMEA_FILTER_EXPR

        role = await db_session.get(Role, rules[0].role_id)
        assert role.name == DEMO_ROLE_NAMES["emea"]

    @pytest.mark.asyncio
    async def test_a_second_org_gets_rules_on_its_own_role(self, org_id, db_session, seeded):
        """BUG-036. Demo emails are unique install-wide, so seeding a second org
        reuses the first org's demo user. The rules used to take that user's
        role_id, binding org 1's role to org 2's dataset -- org 1's admin then
        listed a "Deleted dataset" rule and could edit a rule on org 2's data."""
        from app.models.models import ColumnSecurityRule, Dataset, Role, RowSecurityRule
        other = Organization(name="Second Demo Co")
        db_session.add(other)
        await db_session.flush()
        await seed_demo_use_cases(db_session, other.id, await seed_demo_datasets(db_session, other.id))

        for model in (RowSecurityRule, ColumnSecurityRule):
            pairs = (await db_session.execute(
                select(Role.org_id, Dataset.org_id).select_from(model)
                .join(Role, Role.id == model.role_id).join(Dataset, Dataset.id == model.dataset_id)
            )).all()
            assert sorted(pairs) == [(org_id, org_id), (other.id, other.id)], model.__name__

    @pytest.mark.asyncio
    async def test_a_second_org_gets_its_own_logins_and_unseeds_them(self, org_id, db_session, seeded):
        """Demo emails are unique install-wide, so a second org used to REUSE
        the first org's demo users: its 'restricted login' logged into org 1.
        The first org keeps the documented addresses; others get +org<N>."""
        from app.models.models import Role, User
        from app.services.demo_use_cases import DEMO_USER_EMAILS, _remove_existing_use_cases
        other = Organization(name="Second Demo Co")
        db_session.add(other)
        await db_session.flush()
        await seed_demo_use_cases(db_session, other.id, await seed_demo_datasets(db_session, other.id))

        rows = (await db_session.execute(
            select(User.email, User.org_id, Role.org_id).join(Role, Role.id == User.role_id)
            .where(User.email.like("demo-%@example.invalid")))).all()
        by_org = {}
        for email, user_org, role_org in rows:
            assert user_org == role_org, email          # a login's role is its own org's
            by_org.setdefault(user_org, set()).add(email)
        assert by_org[org_id] == set(DEMO_USER_EMAILS.values())
        assert by_org[other.id] == {f"demo-emea+org{other.id}@example.invalid",
                                    f"demo-global+org{other.id}@example.invalid"}

        await _remove_existing_use_cases(db_session, other.id)
        left = (await db_session.execute(select(User.email).where(User.org_id == other.id,
                                                                  User.email.like("demo-%")))).scalars().all()
        assert left == []
        still = (await db_session.execute(select(User.email).where(User.org_id == org_id,
                                                                   User.email.like("demo-%")))).scalars().all()
        assert set(still) == set(DEMO_USER_EMAILS.values())       # org 1 untouched

    @pytest.mark.asyncio
    async def test_the_emea_filter_actually_matches_rows(self, org_id, db_session, seeded):
        """A filter that matches nothing is indistinguishable from a filter that
        works perfectly -- both show zero rows. This shipped once: the rule read
        `region == 'EMEA'` while the seeded data only ever contains
        'North America' / 'Europe' / 'Asia Pacific' / 'Latin America', so the
        restricted demo login saw an empty report and the "who is allowed to see
        what" use case demonstrated nothing. Applying the real RLS engine to the
        real seeded file is the only check that would have caught it -- asserting
        against the expression string, as the sibling test above does, cannot."""
        from app.services.demo_use_cases import EMEA_FILTER_EXPR
        from app.services.ingest import load_file
        from app.services.widget_data import apply_rls_filter

        frame = load_file(seeded["datasets"]["sales"].filename)
        filtered = apply_rls_filter(frame, EMEA_FILTER_EXPR)
        assert len(filtered) > 0, (
            f"{EMEA_FILTER_EXPR!r} matched zero of {len(frame)} rows -- "
            "the restricted demo role would see an empty report")
        assert len(filtered) < len(frame), (
            "the filter must actually restrict something, or the two demo "
            "logins show identical data and the comparison demonstrates nothing")

    @pytest.mark.asyncio
    async def test_the_share_link_stores_only_a_hash(self, org_id, db_session, seeded):
        """A demo must not be the one component that keeps a recoverable
        credential in the database."""
        from app.models.models import ShareLink

        links = (await db_session.execute(select(ShareLink))).scalars().all()
        assert len(links) == 1
        assert len(links[0].token_hash) == 64          # sha256 hex
        assert links[0].expires_at is not None, "a demo link must expire"

    @pytest.mark.asyncio
    async def test_the_embed_config_allows_only_localhost(self, org_id, db_session, seeded):
        """An embed token is a live host-signed credential. A demo config that
        accepted any origin would be an invitation."""
        from app.models.models import EmbedConfig

        cfgs = (await db_session.execute(select(EmbedConfig))).scalars().all()
        assert len(cfgs) == 1
        assert all(o.startswith("http://localhost") for o in cfgs[0].allowed_origins)

    @pytest.mark.asyncio
    async def test_the_schedule_and_alert_are_inert(self, org_id, db_session, seeded):
        """The safety property, asserted on the rows this layer actually seeds
        rather than on the absence of rows."""
        from app.models.models import DataAlert, ReportSchedule

        scheds = (await db_session.execute(select(ReportSchedule))).scalars().all()
        alerts = (await db_session.execute(select(DataAlert))).scalars().all()
        assert scheds and alerts, "use case 4 needs both to show anything"
        for row in [*scheds, *alerts]:
            assert row.interval_minutes == 0, (
                f"{type(row).__name__} must be seeded with interval_minutes=0")

        # The property that actually matters, asserted against the scheduler's
        # own predicate rather than against the column: a future change to
        # is_due would break this test rather than silently start mailing.
        from datetime import datetime
        from app.services.refresh_scheduler import is_due, schedule_is_due
        now = datetime.utcnow()
        for row in scheds:
            assert schedule_is_due(row, now) is False
        for row in alerts:
            assert is_due(row.interval_minutes, row.last_checked_at, now) is False


class TestGrantsAreFullyRemoved:
    """A leaked share link or demo login is a live credential, not clutter."""

    @pytest.mark.asyncio
    async def test_remove_demo_content_takes_every_grant(self, org_id, db_session, seeded):
        from app.models.models import (ColumnSecurityRule, DataAlert,
                                       EmbedConfig, ReportSchedule,
                                       RowSecurityRule, ShareLink, User)
        from app.services.demo_content import remove_demo_content
        from app.services.demo_use_cases import DEMO_USER_EMAILS

        await remove_demo_content(db_session, org_id)

        for model in (ShareLink, EmbedConfig, ReportSchedule, DataAlert,
                      RowSecurityRule, ColumnSecurityRule):
            left = (await db_session.execute(select(model))).scalars().all()
            assert not left, f"{model.__name__} survived the unseed"

        users = (await db_session.execute(
            select(User).where(User.email.in_(list(DEMO_USER_EMAILS.values())))
        )).scalars().all()
        assert not users, "demo logins survived the unseed"

    @pytest.mark.asyncio
    async def test_it_does_not_delete_a_real_user(self, org_id, db_session, seeded):
        """Scoped to the demo emails, so a colleague's account in the same org
        is untouched -- the case that separates a correct implementation from a
        plausible one."""
        from app.core.security import hash_password
        from app.models.models import Role, User
        from app.services.demo_content import remove_demo_content

        role = Role(org_id=org_id, name="Real role", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        real = User(org_id=org_id, role_id=role.id, email="real@example.com",
                    password_hash=hash_password("pw"))
        db_session.add(real)
        await db_session.flush()

        await remove_demo_content(db_session, org_id)
        still = await db_session.get(User, real.id)
        assert still is not None, "removal deleted a user it does not own"


class TestTheDemoWorkspace:
    """The demo files its reports, so the tree has a shape worth looking at.

    Without this every demo report lands under "Unfiled" -- correct, and a poor
    advertisement for a foldering feature.
    """

    @pytest.mark.asyncio
    async def test_reports_are_filed_into_named_folders(self, org_id, db_session, seeded):
        from app.models.models import WorkspaceNode
        from app.services.demo_use_cases import (DEMO_FOLDER_NAMES,
                                                 seed_demo_workspace)

        await seed_demo_workspace(db_session, org_id)

        folders = (await db_session.execute(
            select(WorkspaceNode).where(WorkspaceNode.node_type == "folder")
        )).scalars().all()
        assert {f.name for f in folders} == set(DEMO_FOLDER_NAMES.values())

        filed = (await db_session.execute(
            select(WorkspaceNode).where(WorkspaceNode.node_type == "report")
        )).scalars().all()
        assert filed, "no demo report was filed into the tree"
        assert all(n.parent_id is not None for n in filed), (
            "a filed report ended up at root instead of inside its folder")

    @pytest.mark.asyncio
    async def test_seeding_the_workspace_twice_is_idempotent(self, org_id, db_session, seeded):
        from app.models.models import WorkspaceNode
        from app.services.demo_use_cases import seed_demo_workspace

        await seed_demo_workspace(db_session, org_id)
        first = len((await db_session.execute(select(WorkspaceNode))).scalars().all())
        await seed_demo_workspace(db_session, org_id)
        second = len((await db_session.execute(select(WorkspaceNode))).scalars().all())
        assert first == second

    @pytest.mark.asyncio
    async def test_it_does_not_refile_a_report_someone_moved(self, org_id, db_session, seeded):
        """Re-seeding must not undo a user's own organisation."""
        from app.models.models import WorkspaceNode
        from app.services.demo_use_cases import seed_demo_workspace

        await seed_demo_workspace(db_session, org_id)
        node = (await db_session.execute(
            select(WorkspaceNode).where(WorkspaceNode.node_type == "report")
        )).scalars().first()
        node.parent_id = None          # the user dragged it to the root
        await db_session.flush()

        await seed_demo_workspace(db_session, org_id)
        again = await db_session.get(WorkspaceNode, node.id)
        assert again.parent_id is None, "re-seeding moved a report the user had filed"

    @pytest.mark.asyncio
    async def test_unseeding_removes_the_folders(self, org_id, db_session, seeded):
        from app.models.models import WorkspaceNode
        from app.services.demo_content import remove_demo_content
        from app.services.demo_use_cases import seed_demo_workspace

        await seed_demo_workspace(db_session, org_id)
        await remove_demo_content(db_session, org_id)

        left = (await db_session.execute(select(WorkspaceNode))).scalars().all()
        assert not left, "demo workspace nodes survived the unseed"

    @pytest.mark.asyncio
    async def test_the_use_cases_folder_is_restricted_to_the_emea_role(
            self, org_id, db_session, seeded):
        """The point of the demo grant: the two demo logins see different menus.

        A demo where every folder is visible to everyone would ship the
        foldering feature and hide the visibility feature, which is the half
        that is hard to believe without seeing it.
        """
        from app.models.models import Role, WorkspaceFolderRole, WorkspaceNode
        from app.services.demo_use_cases import (DEMO_FOLDER_NAMES,
                                                 DEMO_ROLE_NAMES,
                                                 seed_demo_workspace)

        await seed_demo_workspace(db_session, org_id)

        grants = (await db_session.execute(
            select(WorkspaceFolderRole))).scalars().all()
        assert len(grants) == 1, (
            "expected exactly one demo grant -- 'Widget gallery' is left "
            "unrestricted on purpose, so the demo shows both the grant and "
            "the no-grants-means-everyone default")

        node = await db_session.get(WorkspaceNode, grants[0].node_id)
        assert node.name == DEMO_FOLDER_NAMES["use_cases"]

        role = await db_session.get(Role, grants[0].role_id)
        assert role.name == DEMO_ROLE_NAMES["emea"]

    @pytest.mark.asyncio
    async def test_seeding_twice_does_not_duplicate_the_grant(
            self, org_id, db_session, seeded):
        from app.models.models import WorkspaceFolderRole
        from app.services.demo_use_cases import seed_demo_workspace

        await seed_demo_workspace(db_session, org_id)
        await seed_demo_workspace(db_session, org_id)

        grants = (await db_session.execute(
            select(WorkspaceFolderRole))).scalars().all()
        assert len(grants) == 1

    @pytest.mark.asyncio
    async def test_unseeding_removes_the_grant(self, org_id, db_session, seeded):
        """Teardown deletes grants explicitly rather than trusting the cascade,
        so this has to hold on SQLite too."""
        from app.models.models import WorkspaceFolderRole
        from app.services.demo_content import remove_demo_content
        from app.services.demo_use_cases import seed_demo_workspace

        await seed_demo_workspace(db_session, org_id)
        await remove_demo_content(db_session, org_id)

        left = (await db_session.execute(
            select(WorkspaceFolderRole))).scalars().all()
        assert not left, "a demo folder grant survived the unseed"
