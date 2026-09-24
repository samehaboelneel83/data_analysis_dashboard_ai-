"""The org's report-navigation tree: folders, filed reports, and their pages.

Reports are otherwise flat -- a Report row carries `org_id` and nothing
positional. This turns "every report in the org" into a menu.

Three contracts here are load-bearing, and each has a test:

  * **Deleting a folder never deletes a report.** `parent_id` cascades, so a
    naive delete would take the whole subtree. Children are re-parented to the
    deleted node's parent first -- the same fix `hierarchy.py::delete_node`
    already carries, whose comment records the bug that taught it.

  * **A node cannot be moved into its own subtree.** `hierarchy.py` does a blind
    `setattr` over the patch body and has no such guard; dataset hierarchies are
    small and hand-built, so it has not bitten. This tree is the navigation menu
    for the whole org, and a cycle in it hangs the renderer for everyone.

  * **Every report is reachable.** Reports with no node come back under
    `unfiled`, so a report can never exist without a way to open it.

Pages are joined in at read time and never stored as nodes: ReportPage rows
already have their own ordering, and persisting copies would leave the menu
stale the moment somebody adds a page in the builder.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import folder_grant_levels
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import (OrgUnit, Report, ReportPage, ReportUserGrant,
                             Role, User, WorkspaceFolderGrant,
                             WorkspaceFolderRole, WorkspaceNode)
from ..schemas.schemas import (WorkspaceGrantIn, WorkspaceGrantOut,
                               WorkspaceNodeCreate, WorkspaceNodeOut,
                               WorkspaceNodeUpdate, WorkspacePageOut,
                               WorkspaceTreeOut)
from ..services.audit import record as audit

router = APIRouter(prefix="/workspace", tags=["workspace"])

NODE_TYPES = ("folder", "report")


async def _org_nodes(db: AsyncSession, org_id: int) -> list[WorkspaceNode]:
    return list((await db.execute(
        select(WorkspaceNode)
        .where(WorkspaceNode.org_id == org_id)
        .order_by(WorkspaceNode.position, WorkspaceNode.id)
    )).scalars().all())


def _may_manage(node: WorkspaceNode, user: User) -> bool:
    """An org admin, or whoever created this node.

    Anyone in the org may CREATE folders and file reports -- that is how a tree
    gets organised at all. Changing or removing what someone else put there is
    the part that needs an owner, so it is limited to the author and to admins,
    who need a way to tidy up after people who have left.

    `created_by` is nullable: rows that predate the column, and everything the
    demo seeder makes, have no author. Those are admin-only rather than
    everyone-editable, because "nobody owns it" should not read as "anybody may
    delete it".
    """
    if user.role.is_org_admin:
        return True
    return node.created_by is not None and node.created_by == user.id


async def _get_node(node_id: int, db: AsyncSession, user: User) -> WorkspaceNode:
    node = await db.get(WorkspaceNode, node_id)
    check_org(node, user, "Node not found")
    return node


def _would_cycle(nodes: list[WorkspaceNode], node_id: int,
                 new_parent_id: int | None) -> bool:
    """True when re-parenting `node_id` under `new_parent_id` closes a loop.

    Walks UP from the proposed parent: if the node itself is an ancestor of its
    own new parent, the move would detach that whole branch from the root and
    the tree would render as an infinite descent.

    The walk is bounded by the node count rather than trusting termination --
    if the tree is ALREADY cyclic (a row edited directly in the database, say),
    an unbounded walk here would hang the request that was trying to fix it.
    """
    if new_parent_id is None:
        return False
    if new_parent_id == node_id:
        return True

    by_id = {n.id: n for n in nodes}
    seen: set[int] = set()
    cursor = new_parent_id
    for _ in range(len(nodes) + 1):
        if cursor is None or cursor in seen:
            return False
        if cursor == node_id:
            return True
        seen.add(cursor)
        parent = by_id.get(cursor)
        cursor = parent.parent_id if parent else None
    return False


async def _visible_nodes(db: AsyncSession, nodes: list[WorkspaceNode],
                         user: User,
                         granted: set[int] | None = None) -> list[WorkspaceNode]:
    """Drop the folders this user may not see, and everything beneath them.

    NO GRANTS ON A FOLDER = VISIBLE TO EVERYONE. Grants restrict; they are not a
    licence that must first be issued. Any other default would empty every
    non-admin menu the day this shipped -- the same reasoning PageRoleVisibility
    and ReportCapability record.

    Restriction is SUBTREE-EFFECTIVE: a report filed inside a folder the viewer
    cannot see is absent from their tree entirely, not relocated to `unfiled`.
    "Show me only my workspaces" means the menu stops mentioning the rest.

    `granted` (node ids a WorkspaceFolderGrant reaches for this user) OVERRIDES
    the role filter from that node down: access implies visibility. A share
    that opened a report the menu still refused to mention would be the old
    visibility!=security confusion, inverted — so a granted folder surfaces
    even when the role restriction above it would have hidden the branch, and
    it surfaces as a ROOT in that viewer's tree when its ancestors stay hidden.

    Filtering happens HERE, server-side. Sending the whole tree and hiding parts
    in React would make the response itself the leak.
    """
    granted = granted or set()
    grants: dict[int, set[int]] = {}
    for row in (await db.execute(select(WorkspaceFolderRole))).scalars().all():
        grants.setdefault(row.node_id, set()).add(row.role_id)
    if not grants:
        return nodes

    is_admin = bool(user.role and user.role.is_org_admin)

    def allowed(node: WorkspaceNode) -> bool:
        roles = grants.get(node.id)
        if not roles:
            return True
        if is_admin or node.created_by == user.id:
            # An admin locked out could not administer the lock; an author who
            # cannot see what they filed would just make another copy.
            return True
        return user.role_id in roles

    by_id = {n.id: n for n in nodes}
    visible: list[WorkspaceNode] = []
    for node in nodes:
        cursor, ok = node, True
        # Walk to the root: one restricted ancestor hides the whole branch —
        # unless a granted folder is hit first, which ends the question in the
        # viewer's favour. Bounded, for the same reason the cycle walk is.
        for _ in range(len(nodes) + 1):
            if cursor is None:
                break
            if cursor.id in granted:
                ok = True
                break
            if not allowed(cursor):
                ok = False
                break
            cursor = by_id.get(cursor.parent_id) if cursor.parent_id else None
        if ok:
            visible.append(node)
    return visible


def _report_is_mine(author_id: int | None, user: User) -> bool:
    """NULL author (every report from before 0013) is unowned -- never mine."""
    return author_id is not None and author_id == user.id


def _serialize(nodes: list[WorkspaceNode],
               pages_by_report: dict[int, list[ReportPage]],
               names_by_report: dict[int, str],
               user: User,
               grants: dict[int, set[int]],
               authors_by_report: dict[int, int | None],
               caps_by_report: dict[int, str],
               shared_ids: set[int] | None = None,
               granted_reports: set[int] | None = None) -> list[WorkspaceNodeOut]:
    """Build the nested tree from the flat node list.

    Children are attached in the order the query returned (position, then id),
    so folders and reports interleave under one sequence rather than reports
    always sorting after folders.
    """
    shared_ids = shared_ids or set()
    granted_reports = granted_reports or set()
    out: dict[int, WorkspaceNodeOut] = {}
    for n in nodes:
        # Draft privacy: a report node this viewer resolves to 'none' on (an
        # unpublished dashboard someone else authored, no grant) is not
        # serialized -- the menu must not advertise what /reports/{id} 404s.
        if (n.report_id is not None
                and caps_by_report.get(n.report_id, "data") == "none"):
            continue
        is_mine = ((n.created_by is not None and n.created_by == user.id)
                   if n.node_type == "folder"
                   else _report_is_mine(authors_by_report.get(n.report_id or -1), user))
        pages = pages_by_report.get(n.report_id or -1, [])
        out[n.id] = WorkspaceNodeOut(
            id=n.id,
            parent_id=n.parent_id,
            node_type=n.node_type,
            # A report node's label comes from the report, so a rename shows up
            # in the menu without a second write.
            name=n.name if n.node_type == "folder" else names_by_report.get(n.report_id or -1),
            report_id=n.report_id,
            position=n.position,
            pages=[WorkspacePageOut.model_validate(p) for p in pages],
            # Computed server-side: the UI showing or hiding a control must not
            # depend on it re-implementing the ownership rule. Same stance as
            # the cycle guard -- one place owns each rule.
            can_manage=_may_manage(n, user),
            # Ownership, not permission. An admin may manage every node in the
            # org, so can_manage cannot tell a user which folders are theirs --
            # which is the whole point of the My workspaces grouping. A report
            # node answers with the REPORT's author, not the node's creator:
            # filing someone else's report into a folder does not make the
            # work yours.
            is_mine=is_mine,
            # Sharing, from the viewer's side, and ONLY sharing: somebody
            # deliberately gave this to me -- a folder grant over this node or
            # an ancestor, or (for a report) a per-report grant naming me.
            #
            # Merely "not mine" is NOT shared. A demo folder the whole org can
            # see, or any colleague's folder an admin can see because they are
            # an admin, was given to nobody in particular; filing those under
            # "Shared with me" would claim a privilege that was never granted.
            shared_with_me=((n.id in shared_ids
                             or (n.report_id is not None and n.report_id in granted_reports))
                            and not is_mine),
            my_capability=caps_by_report.get(n.report_id or -1, "data"),
            published=bool(n.published) if n.node_type == "folder" else False,
            # Only disclosed to someone who could change it anyway; to everyone
            # else the restriction is simply invisible.
            role_ids=sorted(grants.get(n.id, set())) if _may_manage(n, user) else [],
            children=[],
        )

    roots: list[WorkspaceNodeOut] = []
    for n in nodes:
        if n.id not in out:          # dropped above: a draft hidden from this viewer
            continue
        node = out[n.id]
        parent = out.get(n.parent_id) if n.parent_id else None
        # A node whose parent is missing (or outside this org) is treated as a
        # root rather than dropped: an unreachable report is worse than an
        # oddly-placed one.
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


@router.get("/tree", response_model=WorkspaceTreeOut)
async def get_tree(db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """The whole org tree, plus any report that has not been filed."""
    org_id = current_user.org_id
    all_nodes = await _org_nodes(db, org_id)

    # Workspace sharing: the folders whose grants reach this viewer (self),
    # and every node under one of them (subtree) — the first set punches
    # through the role-visibility filter, the second wears "Shared with me".
    grant_levels = await folder_grant_levels(db, current_user)
    by_id_all = {n.id: n for n in all_nodes}
    shared_ids: set[int] = set()
    if grant_levels:
        for n in all_nodes:
            cur, seen = n, set()
            while cur is not None and cur.id not in seen:
                seen.add(cur.id)
                if cur.id in grant_levels:
                    shared_ids.add(n.id)
                    break
                cur = by_id_all.get(cur.parent_id) if cur.parent_id else None

    nodes = await _visible_nodes(db, all_nodes, current_user,
                                 set(grant_levels))

    reports = list((await db.execute(
        select(Report).where(Report.org_id == org_id).order_by(Report.name)
    )).scalars().all())
    names_by_report = {r.id: r.name for r in reports}

    pages = list((await db.execute(
        select(ReportPage)
        .where(ReportPage.report_id.in_([r.id for r in reports] or [-1]))
        .order_by(ReportPage.position, ReportPage.id)
    )).scalars().all())
    pages_by_report: dict[int, list[ReportPage]] = {}
    for p in pages:
        pages_by_report.setdefault(p.report_id, []).append(p)

    grants: dict[int, set[int]] = {}
    for row in (await db.execute(select(WorkspaceFolderRole))).scalars().all():
        grants.setdefault(row.node_id, set()).add(row.role_id)

    # Authorship + capability per report, so every report entry (filed or
    # unfiled) can say "mine vs granted" and "view-only vs designable" without
    # the client fetching each report.
    from ..core.capability import effective_capabilities
    authors_by_report = {r.id: r.created_by for r in reports}
    caps_by_report = await effective_capabilities(
        db, current_user, [r.id for r in reports])

    # The OTHER way a thing is genuinely shared with you: the dashboard's
    # author named you on it. Without this a report someone shared directly
    # would sit among the org's general furniture, which is the same lie in
    # the other direction.
    granted_reports = set((await db.execute(
        select(ReportUserGrant.report_id)
        .where(ReportUserGrant.user_id == current_user.id)
    )).scalars().all())

    roots = _serialize(nodes, pages_by_report, names_by_report, current_user,
                       grants, authors_by_report, caps_by_report, shared_ids,
                       granted_reports)

    # A report filed inside a folder this viewer cannot see is NOT surfaced as
    # unfiled -- that would defeat the restriction by relocating the entry
    # rather than hiding it. `all_filed` counts every node in the org, visible
    # or not; `unfiled` therefore means "filed nowhere", not "filed somewhere I
    # cannot see".
    all_filed = {
        n.report_id for n in all_nodes if n.report_id is not None
    }
    filed = all_filed
    unfiled = [
        WorkspaceNodeOut(
            id=0,                      # synthetic: no node row exists yet
            node_type="report",
            name=r.name,
            report_id=r.id,
            position=0,
            pages=[WorkspacePageOut.model_validate(p)
                   for p in pages_by_report.get(r.id, [])],
            is_mine=_report_is_mine(r.created_by, current_user),
            # An unfiled report reaches a non-author only by a grant, a folder
            # share, or publication -- and only the first two were GIVEN to
            # this person.
            shared_with_me=(r.id in granted_reports
                            and not _report_is_mine(r.created_by, current_user)),
            my_capability=caps_by_report.get(r.id, "data"),
        )
        for r in reports
        if r.id not in filed and caps_by_report.get(r.id, "data") != "none"
    ]
    return WorkspaceTreeOut(roots=roots, unfiled=unfiled)


@router.post("/nodes", response_model=WorkspaceNodeOut, status_code=201)
async def create_node(body: WorkspaceNodeCreate,
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    org_id = current_user.org_id
    if body.node_type not in NODE_TYPES:
        raise HTTPException(400, f"node_type must be one of {NODE_TYPES}")

    if body.node_type == "folder":
        if not (body.name or "").strip():
            raise HTTPException(400, "a folder needs a name")
        report_id = None
    else:
        if body.report_id is None:
            raise HTTPException(400, "a report node needs a report_id")
        report = await db.get(Report, body.report_id)
        check_org(report, current_user, "Report not found")
        existing = (await db.execute(
            select(WorkspaceNode).where(WorkspaceNode.report_id == body.report_id)
        )).scalars().first()
        if existing is not None:
            # Unique in the schema too; refused here so the caller gets an
            # explanation rather than an integrity error.
            raise HTTPException(409, "that report is already filed in the tree")
        report_id = body.report_id

    if body.parent_id is not None:
        parent = await _get_node(body.parent_id, db, current_user)
        if parent.node_type != "folder":
            raise HTTPException(400, "only a folder can contain other nodes")

    node = WorkspaceNode(
        org_id=org_id,
        parent_id=body.parent_id,
        node_type=body.node_type,
        name=body.name if body.node_type == "folder" else None,
        report_id=report_id,
        created_by=current_user.id,
        position=body.position,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return WorkspaceNodeOut.model_validate(node)


@router.patch("/nodes/{node_id}", response_model=WorkspaceNodeOut)
async def update_node(node_id: int, body: WorkspaceNodeUpdate,
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    node = await _get_node(node_id, db, current_user)
    if not _may_manage(node, current_user):
        raise HTTPException(
            403, "Only an admin or the person who created this can change it")
    fields = body.model_dump(exclude_unset=True)

    if "parent_id" in fields:
        new_parent_id = fields["parent_id"]
        if new_parent_id is not None:
            parent = await _get_node(new_parent_id, db, current_user)
            if parent.node_type != "folder":
                raise HTTPException(400, "only a folder can contain other nodes")
        nodes = await _org_nodes(db, current_user.org_id)
        if _would_cycle(nodes, node.id, new_parent_id):
            raise HTTPException(400, "a node cannot be moved inside itself")
        node.parent_id = new_parent_id

    if "name" in fields:
        if node.node_type != "folder":
            # A report node's label is the report's name. Renaming here would
            # create a second, divergent title for the same thing.
            raise HTTPException(400, "rename the report itself, not its node")
        node.name = fields["name"]

    if "position" in fields and fields["position"] is not None:
        node.position = fields["position"]

    if "published" in fields and fields["published"] is not None:
        if node.node_type != "folder":
            # Publishing a single dashboard is the report's own act
            # (POST /reports/{id}/publish); the node flag is for WORKSPACES.
            raise HTTPException(400, "publish the report itself, not its node")
        node.published = bool(fields["published"])

    await db.commit()
    await db.refresh(node)
    return WorkspaceNodeOut.model_validate(node)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(node_id: int, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Remove a node. Reports are never deleted.

    Children are re-parented to this node's parent BEFORE the delete, because
    `parent_id` is ON DELETE CASCADE -- letting it run would take the whole
    subtree, and with it every report filed anywhere beneath the folder someone
    just tidied away. `hierarchy.py::delete_node` carries the same fix, and its
    comment records the bug that produced it.
    """
    node = await _get_node(node_id, db, current_user)

    children = (await db.execute(
        select(WorkspaceNode).where(WorkspaceNode.parent_id == node.id)
    )).scalars().all()

    # Removing what somebody else put in the tree needs an owner's say-so: the
    # author, or an admin. Creating is deliberately open to everyone -- that is
    # how a tree gets organised at all -- but a member cannot tidy away a
    # colleague's folder, and an admin can always clean up after someone who has
    # left.
    if not _may_manage(node, current_user):
        raise HTTPException(
            403, "Only an admin or the person who created this can remove it")

    for child in children:
        child.parent_id = node.parent_id
    await db.flush()

    await db.delete(node)
    await db.commit()


@router.get("/nodes/{node_id}/roles", response_model=list[int])
async def get_node_roles(node_id: int, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Roles this folder is restricted to. Empty means everyone in the org."""
    node = await _get_node(node_id, db, current_user)
    if not _may_manage(node, current_user):
        raise HTTPException(403, "Only an admin or the creator can see this")
    rows = (await db.execute(
        select(WorkspaceFolderRole).where(WorkspaceFolderRole.node_id == node.id)
    )).scalars().all()
    return sorted(r.role_id for r in rows)


@router.put("/nodes/{node_id}/roles", response_model=list[int])
async def set_node_roles(node_id: int, role_ids: list[int],
                         db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Restrict a folder to these roles. An EMPTY list removes the restriction.

    Grants live on folders only. A report node's visibility is its ancestors'
    -- giving it its own grants would create a second, quietly disagreeing
    answer to "who sees this report", when `ReportCapability` already owns the
    access question.
    """
    node = await _get_node(node_id, db, current_user)
    if not _may_manage(node, current_user):
        raise HTTPException(
            403, "Only an admin or the person who created this can change it")
    if node.node_type != "folder":
        raise HTTPException(400, "only a folder can be restricted to roles")

    valid = {r.id for r in (await db.execute(
        select(Role).where(Role.org_id == current_user.org_id)
    )).scalars().all()}
    unknown = [rid for rid in role_ids if rid not in valid]
    if unknown:
        # Scoped to this org: granting to another tenant's role would be a
        # restriction nobody in this org could ever satisfy.
        raise HTTPException(400, f"unknown role(s): {unknown}")

    for row in (await db.execute(
        select(WorkspaceFolderRole).where(WorkspaceFolderRole.node_id == node.id)
    )).scalars().all():
        await db.delete(row)
    await db.flush()

    for rid in sorted(set(role_ids)):
        db.add(WorkspaceFolderRole(node_id=node.id, role_id=rid))
    await db.commit()
    return sorted(set(role_ids))


# ── Workspace sharing ────────────────────────────────────────────────────────
# The folder-role rows above RESTRICT the menu; these grants OPEN access.
# Sharing a folder is the publish act for its subtree: `core.capability`
# resolves a grant on any ancestor into report capability, live and
# interactive, with the grantee's own row/column security applied by the data
# pipeline. Levels are view|edit only — 'data' (dataset authoring) is not a
# folder's to give.

GRANT_LEVELS = ("view", "edit")


async def _grants_out(db: AsyncSession, node_id: int,
                      org_id: int) -> list[WorkspaceGrantOut]:
    """The folder's share list with names resolved server-side, so the dialog
    never needs the admin-only user/role/unit surfaces to render an email."""
    rows = (await db.execute(
        select(WorkspaceFolderGrant)
        .where(WorkspaceFolderGrant.node_id == node_id)
        .order_by(WorkspaceFolderGrant.id)
    )).scalars().all()
    user_ids = [g.user_id for g in rows if g.user_id is not None]
    emails = dict((await db.execute(
        select(User.id, User.email).where(User.id.in_(user_ids))
    )).all()) if user_ids else {}
    role_names = dict((await db.execute(
        select(Role.id, Role.name).where(Role.org_id == org_id))).all())
    unit_names = dict((await db.execute(
        select(OrgUnit.id, OrgUnit.name).where(OrgUnit.org_id == org_id))).all())
    return [WorkspaceGrantOut(
        id=g.id, level=g.level,
        user_id=g.user_id, user_email=emails.get(g.user_id),
        role_id=g.role_id, role_name=role_names.get(g.role_id),
        org_unit_id=g.org_unit_id, org_unit_name=unit_names.get(g.org_unit_id),
    ) for g in rows]


@router.get("/share-options")
async def share_options(db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """The names any member may need to ADDRESS a share: this org's roles and
    org units, id + name only. Role names are already non-secret via
    /reports/roles/lite; unit names get the same treatment here because a
    NON-ADMIN folder author may share and cannot read /admin/org-units.
    Members are deliberately not listed — they are typed as emails, so
    sharing never hands every member a browsable directory of the org.
    """
    roles = (await db.execute(
        select(Role).where(Role.org_id == current_user.org_id)
        .order_by(Role.name))).scalars().all()
    units = (await db.execute(
        select(OrgUnit).where(OrgUnit.org_id == current_user.org_id)
        .order_by(OrgUnit.position, OrgUnit.id))).scalars().all()
    return {
        "roles": [{"id": r.id, "name": r.name} for r in roles],
        # `level_name` travels with each unit: the org chart is Country >
        # Region > Department > Team, and a picker that calls every one of
        # them "team" hides three quarters of the chart. The share dialog
        # groups on it.
        "org_units": [{"id": u.id, "name": u.name, "parent_id": u.parent_id,
                       "level_name": u.level_name}
                      for u in units],
    }


@router.get("/nodes/{node_id}/grants", response_model=list[WorkspaceGrantOut])
async def get_node_grants(node_id: int, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Who this folder is shared with. Manager-only, like the roles pair:
    the share list is the author's ledger, not a grantee's directory."""
    node = await _get_node(node_id, db, current_user)
    if not _may_manage(node, current_user):
        raise HTTPException(403, "Only an admin or the creator can see this")
    return await _grants_out(db, node.id, current_user.org_id)


@router.put("/nodes/{node_id}/grants", response_model=list[WorkspaceGrantOut])
async def set_node_grants(node_id: int, body: list[WorkspaceGrantIn],
                          db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Replace this folder's share list. An EMPTY list unshares it.

    Grants live on FOLDERS only, same as the roles pair and for the same
    reason: a report's audience is its ancestors' plus its own per-user
    grants, and a second per-report answer here would quietly disagree with
    `ReportUserGrant`. Each entry names exactly one subject — a member (by
    email or id), a role, or a team (org unit) — at 'view' or 'edit'.
    """
    node = await _get_node(node_id, db, current_user)
    if not _may_manage(node, current_user):
        raise HTTPException(
            403, "Only an admin or the person who created this can share it")
    if node.node_type != "folder":
        raise HTTPException(400, "share a folder — a report inherits its folder's audience")

    valid_roles = {r.id for r in (await db.execute(
        select(Role).where(Role.org_id == current_user.org_id))).scalars().all()}
    valid_units = {u.id for u in (await db.execute(
        select(OrgUnit).where(OrgUnit.org_id == current_user.org_id))).scalars().all()}

    # (kind, id) -> level; a subject named twice keeps its widest level, so a
    # sloppy dialog cannot narrow by accident — grants open, never restrict.
    resolved: dict[tuple[str, int], str] = {}
    for entry in body:
        named_user = entry.user_id is not None or bool((entry.user_email or "").strip())
        subjects = int(named_user) + int(entry.role_id is not None) \
            + int(entry.org_unit_id is not None)
        if subjects != 1:
            raise HTTPException(
                400, "each share names exactly one of: a member, a role, or a team")
        if entry.level not in GRANT_LEVELS:
            raise HTTPException(400, f"level must be one of {GRANT_LEVELS}")

        if named_user:
            if entry.user_id is not None:
                u = await db.get(User, entry.user_id)
                if u is None or u.org_id != current_user.org_id:
                    raise HTTPException(400, "unknown member")
            else:
                email = (entry.user_email or "").strip()
                u = (await db.execute(
                    select(User).where(
                        func.lower(User.email) == email.lower(),
                        User.org_id == current_user.org_id)
                )).scalars().first()
                if u is None:
                    # Scoped to this org — another tenant's address must read
                    # as unknown, not as confirmation it exists somewhere.
                    raise HTTPException(400, f"no member with email {email}")
            key = ("user", u.id)
        elif entry.role_id is not None:
            if entry.role_id not in valid_roles:
                raise HTTPException(400, f"unknown role: {entry.role_id}")
            key = ("role", entry.role_id)
        else:
            if entry.org_unit_id not in valid_units:
                raise HTTPException(400, f"unknown team: {entry.org_unit_id}")
            key = ("org_unit", entry.org_unit_id)

        have = resolved.get(key)
        if have is None or GRANT_LEVELS.index(entry.level) > GRANT_LEVELS.index(have):
            resolved[key] = entry.level

    for row in (await db.execute(
        select(WorkspaceFolderGrant).where(WorkspaceFolderGrant.node_id == node.id)
    )).scalars().all():
        await db.delete(row)
    await db.flush()

    for (kind, sid), level in resolved.items():
        db.add(WorkspaceFolderGrant(
            org_id=current_user.org_id, node_id=node.id,
            user_id=sid if kind == "user" else None,
            role_id=sid if kind == "role" else None,
            org_unit_id=sid if kind == "org_unit" else None,
            level=level, created_by=current_user.id,
        ))
    await audit(db, current_user, "workspace.share", "workspace_node", node.id,
                f"{node.name}: {len(resolved)} grant(s)")
    await db.commit()
    return await _grants_out(db, node.id, current_user.org_id)
