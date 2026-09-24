"""Per-report viewer capability levels — SAS's three additive tiers.

  view  read + interact (filter, drill, bookmark) only
  edit  change the report's structure: widgets, pages, layout, rules, ...
  data  edit PLUS author the dataset's calculated columns, measures and prep

A (report, role) pair with no row defaults to 'view' on unowned / published
dashboards (look and filter) and to the author's 'data' on their own drafts.
Org admins are always 'data'. Folder and per-user grants may widen.

Enforcement lives at two choke points: `_bump_revision` (every report
mutation calls it) requires >= edit, and the dataset-authoring endpoints
(calc columns, measures, prep) require >= data via `max_dataset_capability`.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import (Dataset, DatasetShare, Report, ReportCapability,
                             ReportPage, ReportUserGrant, ReportWidget, User,
                             WorkspaceFolderGrant, WorkspaceNode)

_RANK = {"view": 0, "edit": 1, "data": 2}
# 'none' is a RESOLUTION result, never a settable level: it stays out of _RANK
# so the capability admin endpoint (which validates against LEVELS) cannot
# store it.
LEVELS = tuple(_RANK)


def rank(level: str | None) -> int:
    if level == "none":
        return -1
    return _RANK.get(level or "data", 2)


async def _published_via_folder(db: AsyncSession, org_id: int) -> set[int]:
    """Report ids filed anywhere under a published folder.

    Publishing a folder publishes the WORKSPACE: every authored dashboard in
    its subtree, including ones filed later -- resolved at read time from the
    tree, never copied onto the reports, so refiling a report changes its
    publication with it.
    """
    nodes = (await db.execute(
        select(WorkspaceNode).where(WorkspaceNode.org_id == org_id)
    )).scalars().all()
    by_id = {n.id: n for n in nodes}

    def under_published(n: WorkspaceNode) -> bool:
        seen: set[int] = set()
        cur = by_id.get(n.parent_id) if n.parent_id else None
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            if cur.node_type == "folder" and cur.published:
                return True
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        return False

    return {n.report_id for n in nodes
            if n.report_id is not None and under_published(n)}


async def folder_grant_levels(db: AsyncSession, user: User) -> dict[int, str]:
    """node_id -> the best level a workspace-folder grant gives THIS user.

    A grant matches when it names the user, their role, or an org unit whose
    SUBTREE holds one of the user's placements: a grant to "Sales" reaches
    someone placed in "Sales / EMEA". Membership climbs the org chart upward
    — deliberately the mirror of `core.rls`, whose data scope walks DOWNWARD
    from a placement. Both readings agree that being in EMEA makes you part
    of Sales; they just answer different questions about it.

    This is the ONE matcher for "which folder grants apply to me". The
    workspace tree (visibility, the Shared-with-me marker) and the capability
    resolvers below both consume it — two hand-rolled copies would disagree
    eventually, and this table decides access.
    """
    from ..models.models import OrgUnit, UserOrgUnit

    placements = (await db.execute(
        select(UserOrgUnit.org_unit_id).where(UserOrgUnit.user_id == user.id)
    )).scalars().all()
    my_units: set[int] = set()
    if placements:
        parent_of = dict((await db.execute(
            select(OrgUnit.id, OrgUnit.parent_id)
            .where(OrgUnit.org_id == user.org_id)
        )).all())
        for uid in placements:
            seen: set[int] = set()
            cur: int | None = uid
            # Bounded by `seen`: a hand-edited cyclic chart must not hang the
            # request (same discipline as the tree walks).
            while cur is not None and cur not in seen and cur in parent_of:
                seen.add(cur)
                my_units.add(cur)
                cur = parent_of[cur]

    conds = [WorkspaceFolderGrant.user_id == user.id,
             WorkspaceFolderGrant.role_id == user.role_id]
    if my_units:
        conds.append(WorkspaceFolderGrant.org_unit_id.in_(my_units))
    rows = (await db.execute(
        select(WorkspaceFolderGrant.node_id, WorkspaceFolderGrant.level)
        .where(WorkspaceFolderGrant.org_id == user.org_id, or_(*conds))
    )).all()
    out: dict[int, str] = {}
    for node_id, level in rows:
        if node_id not in out or rank(level) > rank(out[node_id]):
            out[node_id] = level
    return out


async def folder_granted_reports(db: AsyncSession, user: User) -> dict[int, str]:
    """report_id -> best granted level, resolved over ancestor folders.

    Resolved at read time from the tree, exactly like `_published_via_folder`:
    refiling a report into (or out of) a shared workspace changes what the
    grantees can open, with nothing copied onto the report to go stale.
    """
    levels = await folder_grant_levels(db, user)
    if not levels:
        return {}
    nodes = (await db.execute(
        select(WorkspaceNode).where(WorkspaceNode.org_id == user.org_id)
    )).scalars().all()
    by_id = {n.id: n for n in nodes}
    out: dict[int, str] = {}
    for n in nodes:
        if n.report_id is None:
            continue
        best: str | None = None
        seen: set[int] = set()
        cur = by_id.get(n.parent_id) if n.parent_id else None
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            lvl = levels.get(cur.id)
            if lvl is not None and (best is None or rank(lvl) > rank(best)):
                best = lvl
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        if best is not None:
            out[n.report_id] = best
    return out


def _resolve(report: Report, *, is_admin: bool, author_ok: int | None,
             grant: str | None, role_row: str | None,
             folder_published: bool, folder_grant: str | None = None) -> str:
    """One report's capability for one user -- the publish/grant regime.

    'none' means NO ACCESS: the report must not appear in lists or trees, and
    opening it by id 404s. The order below is the contract:

      admin > author > per-user grant > folder grant > (published: role row
      or 'view') > none

    `folder_grant` is workspace sharing: the best WorkspaceFolderGrant level
    over the report's ancestor folders. A folder grant on an UNPUBLISHED
    report opens it — sharing the workspace IS the publish act for its
    subtree. Two precedence choices, both pinned by tests:

      * A PER-REPORT grant beats a folder grant even downward (report 'view'
        under a folder shared 'edit' stays 'view'): the author named this
        person on this report, and the specific instrument stays
        authoritative — same reason the grant rung already beat publication.
      * Against PUBLICATION the folder grant only ever widens (max of the
        two): publication is org-wide and anonymous, so a team share must
        never hand a grantee less than any stranger in the org gets.

    UNOWNED reports (created_by NULL -- demo content and rows from before
    authorship existed) are org furniture, not a studio: they resolve like a
    published dashboard (`role_row` or 'view') so a workspace View share
    cannot be bypassed. Admins still get 'data'. An explicit grant or folder
    share may widen.
    """
    if is_admin:
        return "data"
    if report.created_by is not None and report.created_by == author_ok:
        return "data"
    if grant:
        return grant
    published_level = ((role_row or "view")
                       if (report.published or folder_published
                           or report.created_by is None) else None)
    if folder_grant and published_level:
        return (folder_grant if rank(folder_grant) >= rank(published_level)
                else published_level)
    if folder_grant:
        return folder_grant
    if published_level:
        # An admin-set role row may widen (or narrow) what publication gives
        # this role; without one, published means exactly "look, don't touch".
        return published_level
    return "none"


async def effective_capability(db: AsyncSession, user: User, report_id: int) -> str:
    """This user's capability on one report ('none'|'view'|'edit'|'data').

    Org scoping comes FIRST, before the admin shortcut: an admin of another
    org resolves to 'none' like any stranger.
    """
    report = await db.get(Report, report_id)
    if report is None or report.org_id != user.org_id:
        return "none"
    role_row = (await db.execute(
        select(ReportCapability.level).where(
            ReportCapability.report_id == report_id,
            ReportCapability.role_id == user.role_id)
    )).scalar_one_or_none()
    grant = (await db.execute(
        select(ReportUserGrant.level).where(
            ReportUserGrant.report_id == report_id,
            ReportUserGrant.user_id == user.id)
    )).scalar_one_or_none()
    folder_pub = (not report.published and report.created_by is not None
                  and report_id in await _published_via_folder(db, user.org_id))
    is_admin = bool(user.role and user.role.is_org_admin)
    # The folder-grant lookup (grants + org chart + tree) only runs when the
    # cheaper rungs cannot already decide: admins, authors and per-user
    # grantees never pay for it. `require_capability` sits on every widget-data
    # call, so this gate is the hot path's protection.
    # Folder grants also apply to unowned demo reports: skipping them was how
    # a View share still resolved to the studio.
    folder_grant = None
    if (not is_admin and report.created_by != user.id and not grant):
        folder_grant = (await folder_granted_reports(db, user)).get(report_id)
    return _resolve(report, is_admin=is_admin,
                    author_ok=user.id, grant=grant, role_row=role_row,
                    folder_published=folder_pub, folder_grant=folder_grant)


async def effective_capabilities(
        db: AsyncSession, user: User, report_ids: list[int]) -> dict[int, str]:
    """`effective_capability` for many reports in a fixed number of queries.

    Exists for the list endpoints: per-row calls would be N queries, and the
    historical shortcut -- returning the schema default 'data' for every row --
    made the list payload claim full access on reports the server would then
    refuse to let the user edit. Resolution is `_resolve`, identical to the
    single-report path; a row that resolves to 'none' must be FILTERED OUT by
    the caller, not shown.
    """
    if not report_ids:
        return {}
    reports = (await db.execute(
        select(Report).where(Report.id.in_(report_ids))
    )).scalars().all()
    is_admin = bool(user.role and user.role.is_org_admin)
    role_rows = dict((await db.execute(
        select(ReportCapability.report_id, ReportCapability.level).where(
            ReportCapability.report_id.in_(report_ids),
            ReportCapability.role_id == user.role_id)
    )).all())
    grants = dict((await db.execute(
        select(ReportUserGrant.report_id, ReportUserGrant.level).where(
            ReportUserGrant.report_id.in_(report_ids),
            ReportUserGrant.user_id == user.id)
    )).all())
    folder_pub = await _published_via_folder(db, user.org_id)
    # One batch resolution for the whole list; admins skip it the same way
    # the single resolver's gate does.
    folder_grants = {} if is_admin else await folder_granted_reports(db, user)
    out: dict[int, str] = {rid: "none" for rid in report_ids}
    for r in reports:
        if r.org_id != user.org_id:
            continue
        out[r.id] = _resolve(r, is_admin=is_admin, author_ok=user.id,
                             grant=grants.get(r.id), role_row=role_rows.get(r.id),
                             folder_published=r.id in folder_pub,
                             folder_grant=folder_grants.get(r.id))
    return out


async def require_capability(db: AsyncSession, user: User, report_id: int, min_level: str) -> None:
    level = await effective_capability(db, user, report_id)
    if level == "none":
        # A draft you were not shown does not exist for you. 404, never 403 --
        # the same discipline org scoping uses, for the same reason: a 403
        # confirms the id is real.
        raise HTTPException(404, "Report not found")
    if rank(level) < _RANK[min_level]:
        raise HTTPException(
            403, f"Your access to this report is {level}-level; "
                 f"this action needs {min_level}")


async def max_dataset_capability(db: AsyncSession, user: User, dataset_id: int) -> str:
    """The user's best capability for authoring this dataset's data model.

    Admins: 'data'. Otherwise the MAX capability their role holds across the
    reports whose primary dataset is this one. A report with no capability row
    for the role grants the 'data' default, so a user is only blocked when EVERY
    report using the dataset restricts their role below 'data' -- and a dataset
    no report uses is unrestricted."""
    if user.role and user.role.is_org_admin:
        return "data"
    report_ids = [r for r in (await db.execute(
        select(Report.id).where(Report.dataset_id == dataset_id, Report.org_id == user.org_id)
    )).scalars().all()]
    if not report_ids:
        return "data"
    rows = [lvl for lvl in (await db.execute(
        select(ReportCapability.level).where(
            ReportCapability.report_id.in_(report_ids),
            ReportCapability.role_id == user.role_id)
    )).scalars().all()]
    if len(rows) < len(report_ids):
        return "data"  # at least one report leaves the role unrestricted
    return max(rows, key=rank)


async def require_dataset_capability(db: AsyncSession, user: User, dataset_id: int, min_level: str) -> None:
    if rank(await max_dataset_capability(db, user, dataset_id)) < _RANK[min_level]:
        raise HTTPException(
            403, f"Editing this dataset's data model needs {min_level}-level access to a report that uses it")


# ── Who may READ a dataset ───────────────────────────────────────────────────
# Everything above this line governs AUTHORING (`max_dataset_capability` and
# friends answer "may you change the model", and default OPEN). Reading was not
# governed at all: `check_org` was the only gate, so any member of an org could
# list, query, preview and export EVERY dataset in it by id. RLS and column
# rules narrowed the rows and columns inside a dataset; nothing decided whether
# you could open the dataset at all.
#
# The rule now, in one place:
#
#   admin > owner > explicit DatasetShare > a dashboard you can already open
#
# The last rung is what keeps sharing coherent. A workspace shared 'view'
# hands somebody dashboards; those dashboards have to resolve their data or
# the share is an empty frame. So every dataset a VISIBLE report draws on is
# readable -- and, deliberately, nothing more: the grantee can filter and
# explore that dashboard without the Datasets page turning into the whole
# company's data.
#
# UNOWNED (created_by NULL) datasets stay open. Fixtures and seeders make them,
# and migration 0020 backfills live rows to an org admin so a real install has
# none left to be permissive about.


def _config_dataset_ids(config: object) -> set[int]:
    """Dataset ids a widget config points at.

    A widget may override its report's dataset (`config.dataset_id`), so a
    report's data is NOT just `Report.dataset_id` -- missing this is how a
    shared dashboard ends up with one working chart and one that 404s.
    """
    out: set[int] = set()
    if isinstance(config, dict):
        raw = config.get("dataset_id")
        if isinstance(raw, int):
            out.add(raw)
        elif isinstance(raw, str) and raw.isdigit():
            out.add(int(raw))
    return out


async def report_dataset_ids(db: AsyncSession, report_ids: list[int]) -> set[int]:
    """Every dataset these reports draw on: primary, additional, per-widget."""
    if not report_ids:
        return set()
    ids: set[int] = set()
    for primary, extra in (await db.execute(
        select(Report.dataset_id, Report.additional_dataset_ids)
        .where(Report.id.in_(report_ids))
    )).all():
        if primary is not None:
            ids.add(primary)
        if isinstance(extra, list):
            ids.update(x for x in extra if isinstance(x, int))
    for (config,) in (await db.execute(
        select(ReportWidget.config)
        .join(ReportPage, ReportPage.id == ReportWidget.page_id)
        .where(ReportPage.report_id.in_(report_ids))
    )).all():
        ids |= _config_dataset_ids(config)
    return ids


async def readable_dataset_ids(db: AsyncSession, user: User) -> set[int] | None:
    """Datasets this user may READ. None means "every dataset in the org".

    One resolution for the whole request: a 28-widget page must not re-derive
    it 28 times, so callers that loop should resolve once and reuse.
    """
    if user.role and user.role.is_org_admin:
        return None

    ids = set((await db.execute(
        select(Dataset.id).where(
            Dataset.org_id == user.org_id,
            or_(Dataset.created_by == user.id, Dataset.created_by.is_(None)))
    )).scalars().all())

    ids |= set((await db.execute(
        select(DatasetShare.dataset_id).where(DatasetShare.user_id == user.id)
    )).scalars().all())

    org_report_ids = list((await db.execute(
        select(Report.id).where(Report.org_id == user.org_id)
    )).scalars().all())
    caps = await effective_capabilities(db, user, org_report_ids)
    visible = [rid for rid, level in caps.items() if level != "none"]
    ids |= await report_dataset_ids(db, visible)
    return ids


async def can_read_dataset(db: AsyncSession, user: User, dataset_id: int, *,
                           report_id: int | None = None) -> bool:
    """May this user read this dataset?

    `report_id` is the cheap path AND the share-link path: a widget says which
    report it belongs to, so one capability check on that report answers the
    question without resolving the user's whole readable set. It is not a
    loophole -- the report must itself resolve to something other than 'none'
    for this viewer, and the dataset must actually be one that report draws on.
    """
    if user.role and user.role.is_org_admin:
        return True
    if report_id is not None:
        report = await db.get(Report, report_id)
        if (report is not None and report.org_id == user.org_id
                and await effective_capability(db, user, report_id) != "none"
                and dataset_id in await report_dataset_ids(db, [report_id])):
            return True
    ids = await readable_dataset_ids(db, user)
    return ids is None or dataset_id in ids


async def require_dataset_read(db: AsyncSession, user: User, dataset_id: int, *,
                               report_id: int | None = None) -> None:
    """404, never 403: a dataset you were not given does not exist for you --
    the same discipline org scoping and draft privacy already use."""
    if not await can_read_dataset(db, user, dataset_id, report_id=report_id):
        raise HTTPException(404, "Dataset not found")


# ── Dataflows ────────────────────────────────────────────────────────────────
# A dataflow's permission is its OWN, not inherited. That is the whole point of
# the object: `max_dataset_capability` above ends with "a dataset no report uses
# is unrestricted", so a freshly materialized result -- which by definition no
# report uses yet -- is authorable by every member of the org. A transformation
# somebody scheduled should not work that way.
#
# Same three levels, same default-open stance, deliberately: a parallel
# vocabulary would be one more thing to keep straight, and a default-closed
# table would break every existing workflow on the day it ships.


async def effective_dataflow_capability(db: AsyncSession, user: User, dataflow_id: int) -> str:
    """This user's capability on one dataflow. Admins are always 'data';
    otherwise the level granted to their role, defaulting to 'data' when the
    dataflow carries no grants at all."""
    from ..models.models import DataflowCapability

    if user.role and user.role.is_org_admin:
        return "data"
    row = (await db.execute(
        select(DataflowCapability.level).where(
            DataflowCapability.dataflow_id == dataflow_id,
            DataflowCapability.role_id == user.role_id)
    )).scalar_one_or_none()
    if row:
        return row
    # A dataflow with grants for OTHER roles but none for this one is
    # restricted, not unrestricted -- otherwise granting anybody access would
    # silently grant everybody access, which inverts the intent of the grant.
    any_rows = (await db.execute(
        select(DataflowCapability.id).where(
            DataflowCapability.dataflow_id == dataflow_id).limit(1)
    )).scalar_one_or_none()
    return "view" if any_rows else "data"


async def require_dataflow_capability(db: AsyncSession, user: User, dataflow_id: int,
                                      min_level: str) -> None:
    have = await effective_dataflow_capability(db, user, dataflow_id)
    if rank(have) < _RANK[min_level]:
        raise HTTPException(
            403, f"Your access to this dataflow is {have}-level; this action needs {min_level}")


async def require_dataset_write(db: AsyncSession, user: User, dataset: object,
                                min_level: str) -> None:
    """Gate an action on a dataset, honouring a dataflow's ownership first.

    This is the "independent of any one dataset" part made real. When the dataset
    is a dataflow's output, the DATAFLOW's grants decide -- otherwise deleting or
    rescheduling an output would route around the pipeline's permissions by
    operating on what it produced. Anything else falls back to the historical
    report-inherited rule, so nothing that exists today changes behaviour.
    """
    from ..services.prep import derived_from_of

    flow_id = (derived_from_of(dataset) or {}).get("dataflow_id")
    if isinstance(flow_id, int):
        await require_dataflow_capability(db, user, flow_id, min_level)
        return
    await require_dataset_capability(db, user, dataset.id, min_level)


# ── Why (Phase 7.3: everything explains its own permissions) ─────────────────

async def explain_capability(db: AsyncSession, user: User, report_id: int) -> tuple[str, str]:
    """(level, reason) for one report -- the SAME rungs `_resolve` walks, in
    the same order, each saying in words which one decided."""
    report = await db.get(Report, report_id)
    if report is None or report.org_id != user.org_id:
        return "none", "This report does not exist in your organisation."
    level = await effective_capability(db, user, report_id)
    if user.role and user.role.is_org_admin:
        return level, "You are an organisation admin."
    if report.created_by is not None and report.created_by == user.id:
        return level, "You created this report."
    grant = (await db.execute(select(ReportUserGrant.level).where(
        ReportUserGrant.report_id == report_id, ReportUserGrant.user_id == user.id))).scalar_one_or_none()
    if grant:
        return level, f"The report was shared with you directly at {grant} level."
    folder_grant = (await folder_granted_reports(db, user)).get(report_id)
    role_row = (await db.execute(select(ReportCapability.level).where(
        ReportCapability.report_id == report_id,
        ReportCapability.role_id == user.role_id))).scalar_one_or_none()
    role_name = user.role.name if user.role else "your role"
    published = report.published or report.created_by is None or (
        report_id in await _published_via_folder(db, user.org_id))
    if folder_grant and published:
        return level, (f"A workspace folder holding it is shared with you at {folder_grant} level, "
                       f"and it is published ({role_row or 'view'} for {role_name}); the higher applies.")
    if folder_grant:
        return level, f"A workspace folder holding it is shared with you at {folder_grant} level."
    if published:
        if role_row:
            return level, f"It is published, and an admin set {role_name} to {role_row} on it."
        return level, "It is published to the organisation, which gives everyone view access."
    return level, "It is a private draft: not published and not shared with you."
