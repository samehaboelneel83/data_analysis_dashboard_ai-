# Workspaces: a navigable folder tree for reports

**Date:** 2026-08-28
**Goal:** Group an org's reports into nested folders, shown as a tree in the left-hand
menu, so a report — or a specific page of one — is one click away.

**Status:** plan only. No code written; awaiting approval.

---

## What already exists (measured, not assumed)

The Power BI workflow in the brief is: build → publish to a workspace → share/embed →
sign in to view. **Four of those five steps already ship in Datalytics:**

| Power BI step | Datalytics equivalent | Status |
|---------------|----------------------|--------|
| Sign in | `Login.tsx`, JWT + SAML/OIDC SSO | **Exists** |
| Publish to service | Reports live server-side already — there is no desktop/cloud split | **N/A by design** |
| Store in a workspace | — | **This plan** |
| Generate embed code | `EmbedConfig`, `routers/embed.py`, origin allow-listing | **Exists** |
| Embed into a website | `EmbeddedReport.tsx`, token-addressed | **Exists** |
| Share a link | `ShareLink`, `SharedReport.tsx`, expiry + revocation | **Exists** |

`docs/DEMO_WALKTHROUGH.md` already drives share-link and embed creation.

**So the actual gap is one thing: reports are flat.** A `Report` row has `org_id` and
nothing else positional — no folder, no ordering, no tree. `Reports.tsx` lists them.

Two adjacent concepts exist and are **not** this:

- **`Organization`** is the tenancy boundary. Workspaces live *inside* one org.
- **`OrgParent`** is an org→parent edge for multi-tenant grouping, explicitly
  "structural only" and not an access path. Unrelated to report foldering.

The GitHub `.pbix` upload step in the brief has no Datalytics equivalent — report
definitions are rows, versioned by `revision`, not files a user exports.

---

## Design

### One table, following `HierarchyNode`

The codebase already has a self-referential tree with a router and a React component:
`hierarchy_nodes` (the per-dataset data-view tree). Copying that shape is cheaper than
inventing one and gives reviewers something familiar.

```
workspace_nodes
  id          int  PK
  org_id      int  FK organizations.id  CASCADE   -- tenancy scope
  parent_id   int  FK workspace_nodes.id CASCADE  -- null = root
  node_type   str  'folder' | 'report'
  name        str                                 -- folder label; report nodes read through
  report_id   int  FK reports.id CASCADE, nullable, unique
  position    int                                 -- ordering among siblings
```

**A new table, not a `folder_id` column on `reports`.** `OrgParent`'s docstring states
the constraint: *"Its own table because Organization predates it and create_all never
ALTERs a live table to add a column."* A column would appear on fresh installs and be
missing on every existing database.

**One table for both node kinds**, so folders and reports interleave under a single
`position` — a menu where reports always sort below folders is not the menu anyone
drew.

**Naming is deliberately distinct** — `WorkspaceNode`, `routers/workspace.py`,
`WorkspaceTree.tsx`. "Hierarchy" is taken by the data-view tree and conflating the two
would cost more than the keystrokes saved.

### Pages are derived, never stored

The tree shows folders → reports → **pages**, but only folders and report attachments
are persisted. `ReportPage` rows already exist with their own `position`; the tree
endpoint joins them at serialize time.

Storing page nodes would create a sync problem with no upside: add a page in the
builder and the menu goes stale, and every page rename needs two writes.

### Deleting a folder must not delete its reports

`hierarchy.py`'s `delete_node` already solves this, and its comment records why:

> Removing a node HEALS the chain: its children re-parent to its parent […] Without
> this, the parent_id CASCADE silently destroyed every level beneath the deleted one.

Workspaces adopt the same contract: **deleting a folder re-parents its children to that
folder's parent** (root if it had none). Deleting a *report* node removes the node, not
the report — the report reappears at root.

This is the highest-stakes decision here. The lazy alternative — cascade down the tree —
destroys user work on a misclick.

### Cycles must be rejected

`hierarchy.py`'s `update_node` does a blind `setattr` over the patch body, and
`parent_id` is patchable — **so it does not guard against moving a node into its own
descendant.** Dataset hierarchies are small and hand-built, so it has not bitten.

A workspace tree is the navigation menu: a cycle hangs the renderer for everyone in the
org. `PATCH` must walk the ancestor chain and reject a move that would close a loop.

### Every report stays reachable

A report with no node appears at **root**. The tree is navigation, not an optional tag —
a report that exists but cannot be reached from the menu is worse than a flat list.

### Scope fence

- Authenticated UI only. `SharedReport.tsx` and `EmbeddedReport.tsx` show one report to
  someone outside the org and must **not** gain the tree.
- No change to sharing, embedding, RLS or capabilities.

---

## Open question for you

**Who may manage folders?**

| Option | |
|--------|--|
| **A (recommended)** | Any org member creates/renames/moves; **admins only** delete a non-empty folder |
| **B** | Everything capability-gated, matching report edit (`require_capability`) |

A matches how teams actually use folders — anyone tidies, only an admin does something
destructive. B is stricter and costs one dependency per endpoint. **Say which; I've
assumed A below.**

---

## Phases

### Phase 0 — model (S)

| # | Task |
|---|------|
| 0.1 | `WorkspaceNode` in `models.py`, with the FK/cascade shape above |
| 0.2 | Alembic revision (9th) creating `workspace_nodes` |
| 0.3 | Note in `main.py`'s startup block: brand-new table, `create_all` provisions it, no ALTER |

**Acceptance:** table created on a fresh DB and by migration on an existing one.

### Phase 1 — API (M)

| # | Task |
|---|------|
| 1.1 | `routers/workspace.py`: `GET /workspace/tree` (whole org tree, pages joined in) |
| 1.2 | `POST /workspace/nodes` — create folder, or attach a report |
| 1.3 | `PATCH /workspace/nodes/{id}` — rename, move, reorder; **cycle-guarded** |
| 1.4 | `DELETE /workspace/nodes/{id}` — re-parents children, never deletes a report |
| 1.5 | Pydantic schemas; `check_org` on every endpoint |

**Acceptance, one test each:**
- deleting a folder leaves its reports, re-parented
- moving a node into its own descendant returns 400
- a report with no node appears at root
- another org's tree is invisible (the isolation case every router here has)

### Phase 2 — UI (M)

| # | Task |
|---|------|
| 2.1 | `WorkspaceTree.tsx`, modelled on `HierarchyTree.tsx` |
| 2.2 | Mount in `Layout.tsx` as the left-hand menu |
| 2.3 | Click a report → open it; click a page → open at that page |
| 2.4 | Create/rename/delete folder, drag to move |

**Acceptance:** a report filed two folders deep opens from the menu in one click, and
the tree survives a page reload.

### Phase 3 — demo and docs (S)

| # | Task |
|---|------|
| 3.1 | Demo seeder creates a small folder structure over the nine demo reports |
| 3.2 | Line in `test_demo_action_coverage.py` — its docstring says a new feature adds one |
| 3.3 | `ARCHITECTURE.md` + `.html`: table count 62→63, router modules 18→19, a Layer 6 section |
| 3.4 | `LAYER_MAP` entry if any logic lands in `services/` (likely thin enough for the router) |

**These are not optional.** `test_architecture_doc.py` fails on the stale counts and
`test_layer_conformance.py` on an unmapped module — the guards built earlier this
session will catch this feature, which is the point of them.

---

## Verification

```bash
python -m pytest tests/test_workspace.py -q
python -m pytest -q                                     # full suite
DATALYTICS_TEST_DUCKDB_PUSHDOWN=1 python -m pytest -q    # sweep
```

---

## Effort

Phase 0 is three small tasks, Phase 1 five, Phase 2 four, Phase 3 four. No data
migration of existing rows — reports simply start at root, which is exactly what the
"unfiled reports appear at root" rule already specifies.