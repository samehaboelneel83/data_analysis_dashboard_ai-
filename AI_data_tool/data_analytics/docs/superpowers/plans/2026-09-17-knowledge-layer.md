# Knowledge Layer + Journey Wiring — Implementation Plan

> **For agentic workers:** steps use checkbox (`- [ ]`) syntax. Tick a step only after its
> command has been RUN and its output read. Evidence before assertions.

**Goal:** Everything the platform learns about a database reaches every place that draws a
chart, so the app stops choosing widgets from column *shapes* and starts choosing them from
column *meaning*. Then wire the first-run journey — connect → understand → discuss → dataset →
dashboard — so a user who does not know what is in their database is carried through it.

**The defect this closes.** Knowledge is written into two stores by two pipelines with no
bridge between them:

| | live connection | uploaded file |
|---|---|---|
| pipeline | `run_catalog_sync` | `run_sync` |
| writes | `source_objects` / `source_columns` / `source_relationships` (+ `entities`, `glossary_terms`) | `datasets.description`, `dataset_columns.description` / `.semantic_type` |

Every `DatasetColumn(...)` construction site writes `name, dtype, missing_pct, stats={}` and
nothing else — so a dataset imported from a richly-described table is born blind, and the
dataset side is the side every chart reads. `SchemaContext.render()` already proves what a
good prompt looks like (descriptions, enum labels, canonical markers, glossary, entities); it
is reachable only from connection scope.

**The fix is a resolver, not a new store.** The source catalog stays the single truth. A
nullable `dataset_columns.source_column_id` records provenance; `services/knowledge.py`
resolves meaning through it at read time; every blind consumer calls the resolver. Copying
descriptions into `DatasetColumn` at import is rejected on purpose — that manufactures the
same drift that already exists between `Relationship` and `SourceRelationship`.

**Tech stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, pandas, DuckDB, pytest;
React 18, TypeScript, Vite, Vitest.

**Prior analysis:** conversation of 2026-09-17; file references verified in-tree.

## Global constraints

- Services never import FastAPI (`tests/test_layer_conformance.py`). `services/knowledge.py`
  raises plain exceptions and takes a session, never a `Depends`.
- `apply_rls_filter` call sites are allowlisted by `tests/test_rls_base_frame_choke_point.py`.
  Do not add one. The resolver returns *metadata*, never rows.
- Column security: a column the viewer may not see must not gain a description in a prompt.
  The resolver takes the already-computed denied set and drops those columns, matching
  `SchemaContext.denied_columns`.
- The doc-count audit (`tests/test_architecture_doc.py`) pins backend test-module,
  frontend test-file and Alembic revision counts in BOTH `ARCHITECTURE.md` and
  `ARCHITECTURE.html`. Adding a test FILE or a migration bumps both in the same commit.
  Prefer adding to existing test modules.
- Line endings: the index is LF for every file touched here (`git ls-files --eol`). Write LF.
  After each edit run `git diff --stat <path>` and confirm only intended lines moved.
- The working tree carries ~132 files of unrelated in-flight UX work. Never revert or
  reformat a file this plan does not name.
- New migration follows `0029_aggregate_datasets`: `batch_alter_table` + a NAMED foreign key,
  because `tests/test_alembic_migrations.py` runs `upgrade head` on SQLite.
- Backend tests run with `cd backend && .venv/Scripts/python -m pytest <file> -q -p no:cacheprovider`.
- A test that asserts on generated SQL text proves nothing. Assert on executed rows, or on
  the prompt string a consumer actually builds.

---

## Phase A — the knowledge layer

### Task 1: Provenance column + the resolver — DONE
> 13 tests green (`test_knowledge_resolver.py`); a sabotage that ignores the link
> fails 3 of them. `test_alembic_migrations.py` + `test_layer_conformance.py` green
> (18). Doc counts bumped to 33 revisions / 360 modules in both documents.

**Files:**
- Create: `backend/alembic/versions/0033_dataset_column_provenance.py`
- Create: `backend/app/services/knowledge.py`
- Modify: `backend/app/models/models.py` (`DatasetColumn`)
- Modify: `backend/tests/test_alembic_migrations.py`
- Create: `backend/tests/test_knowledge_resolver.py` (new FILE — bump both doc counts)

**Interfaces produced (every later task consumes these):**
- `ColumnKnowledge(name, dtype, description, description_source, semantic_type, enum_labels, comment, is_personal)`
- `ObjectKnowledge(name, description, is_canonical, is_deprecated, business_name, grain)`
- `DatasetKnowledge(object, columns: dict[str, ColumnKnowledge], glossary, joins)`
- `async def for_dataset(db, dataset, *, denied: set[str] | None = None) -> DatasetKnowledge`
- `async def link_columns(db, dataset) -> int` — fills `source_column_id` by name against the
  dataset's `SourceObject`; returns how many linked.

**Precedence ladder** (highest first), mirroring `metadata/store.py`:
`source column confirmed` → `dataset column confirmed` → `source column comment (declared)`
→ `source column inferred` → `dataset column inferred` → none.

- [x] Step 1.1: migration `0033`, batch mode, named FK `fk_dataset_columns_source_column_id_source_columns`, `ondelete="SET NULL"`, plus index
- [x] Step 1.2: `DatasetColumn.source_column_id` on the model
- [x] Step 1.3: `services/knowledge.py` — dataclasses, `for_dataset`, `link_columns`
- [x] Step 1.4: tests — resolves through the link; falls back to the dataset's own row for an upload; confirmed beats inferred; denied columns absent
- [x] Step 1.5: migration round-trip test; run `test_alembic_migrations.py`
- [x] Step 1.6: bump revision + backend-test-module counts in `ARCHITECTURE.md` and `.html`

### Task 2: Fill provenance at every dataset-creation site — DONE
> Linked at all four import commit sites; carried across a re-import beside
> `semantic_type`. Search is tiered (primary table, then tables the SQL names,
> then the catalog) so a join cannot make the base table's columns ambiguous.
> 3 new endpoint tests in `test_query_builder_api.py` (14 green). `dataflows.py`
> needs no call: its outputs derive from datasets, never from a source.

**Files:** `backend/app/routers/data_sources.py` (import + re-import), `backend/app/routers/datasets.py` (`_create_dataset`), `backend/app/routers/dataflows.py`, `backend/tests/test_dataset_provenance.py` (new FILE)

- [x] Step 2.1: call `link_columns` after the `DatasetColumn` rows are flushed, for any dataset with `data_source_id` + `source_table`
- [x] Step 2.2: QueryBuilder datasets — resolve each output column through `query_model` to its origin table before the name fallback
- [x] Step 2.3: re-import preserves links the way it already preserves `semantic_type`
- [x] Step 2.4: hand-written SQL — name match only, and `NULL` when ambiguous. A wrong link is worse than none
- [x] Step 2.5: tests — table import links every column; upload links none; re-import keeps them
- [x] Step 2.6: a plain table import never reaches past its own table (a column its
      catalog lacks stays NULL rather than matching a same-named column elsewhere)
- [x] Step 2.7: `stage_link_datasets` — the sync adopts datasets imported BEFORE it
      ran, which is the ordinary first-run order; reports the count in the run

### Task 3: The dashboard designer reads meaning — DONE
> `describe_for_prompt(profile, knowledge=None)`; a pinned regression test proves
> `None` is byte-identical to the old prompt. 7 new prompt tests in
> `test_dataset_profile.py` (29 green) and 3 endpoint tests in
> `test_suggest_dashboards_endpoint.py` (19 green) proving the catalog's sentences,
> the grain, the canonical marker and the glossary reach the model -- and that a
> DENIED column's description does not. 127 green across the four suggester suites.

`describe_for_prompt` is the *entire* prompt the designer sees. This is the user's exact
complaint.

**Files:** `backend/app/services/dataset_profile.py`, `backend/app/routers/datasets.py`, `backend/app/services/suggest_dataset_dashboard.py`, `backend/tests/test_dataset_profile.py`, `backend/tests/test_suggest_dataset_dashboard.py`

- [x] Step 3.1: `describe_for_prompt(profile, knowledge=None)` — additive; `None` renders byte-identical to today
- [x] Step 3.2: emit per column `— <description>`, `means: 1=new, 2=paid`, and the semantic type when it is not obvious from the role
- [x] Step 3.3: emit an object header — business name, grain, canonical/deprecated markers
- [x] Step 3.4: emit matching glossary terms
- [x] Step 3.5: thread `knowledge` from the suggest-dashboards endpoint
- [x] Step 3.6: tests — a described column appears with its sentence; `knowledge=None` is unchanged; a denied column never appears

### Task 4: The dataset-mode agent and the copilot get the same context — DONE
> `ObjectInfo.descriptions` added and rendered in PASS 2 only, so the skeleton pass
> that guarantees every object is named is untouched. Source mode fills it too --
> column descriptions had never reached any prompt in either mode. Dataset mode now
> also carries canonical markers, enum labels, entities and the glossary. The
> denied-column strip in graph.py now clears `enum_labels`/`descriptions` as well.
> 7 new tests in `test_agent_dataset_context.py` (14 green); 827 green across the
> whole agent/context/suggest/catalog surface.
> Step 4.4 (source joins between datasets from one table) deferred: dataset
> `Relationship` rows already cover it and inventing joins the user never confirmed
> would widen what V3 accepts.

**Files:** `backend/app/services/agent/context.py` (`load_dataset_context`), `backend/app/routers/report_copilot.py`, `backend/tests/test_agent_dataset_context.py`, `backend/tests/test_agent_dataset_mode.py`

- [x] Step 4.1: `load_dataset_context` populates column descriptions, semantic types and enum labels through the resolver
- [x] Step 4.2: glossary is no longer empty in dataset mode — scope to the datasets' sources, plus org-wide terms
- [x] Step 4.3: entities populated for datasets that map to one
- [~] Step 4.4 (deferred, see note): joins — dataset `Relationship` rows keep priority; add source joins between datasets from the same table where no dataset relationship exists
- [x] Step 4.5: confirm `render()` needs no change; pin the two-pass budget still holds with descriptions present

### Task 5: Coded values read as words — BACKEND DONE, frontend next
> `DatasetOut` now carries `column_descriptions`, `value_labels`, `grain` and
> `business_name`, resolved ONCE per dataset read (never per widget request, and
> never on the list). 3 tests in `test_datasets_org_scoping.py` (10 green).
> Rows are NOT rewritten: the raw value stays, because a cross-filter click sends
> it back as a filter and "paid" matches no stored 2. The frontend maps at display.

**Files:** `backend/app/services/widget_data.py`, `backend/app/services/display_rules.py`, `backend/tests/test_widget_data_enum_labels.py` (new FILE)

- [x] Step 5.1: resolved once per DATASET read and carried on the payload — not per
      widget request, which is the hottest path in the app
- [~] Step 5.2: DEFERRED, and deliberately. The mapping belongs in `axisOptions.ts`
      and the chart renderers, which are 185 lines into an unrelated in-flight axis
      rewrite in this same working tree. Editing them now would tangle two changes
      that want separate review. The backend half is done and the payload carries
      `value_labels`, so this is a contained follow-up: read them in the renderer
      and format the tick, never the row.
- [ ] Step 5.3: leave the raw value on the row for cross-filtering; the label is presentation only
- [ ] Step 5.4: tests assert on executed ROWS, not on config

### Task 6: Insights speak the business's words — DONE
> `generate_insights(..., labels=, value_labels=)`, wired at the dataset insights
> endpoint (a parameter with no caller is the same defect as an endpoint with no
> caller). Helpers are `col_label`/`val_label`, NOT `n`/`v` -- the detectors bind
> `v` to a numeric Series and a one-letter helper is shadowed into a TypeError.
> 4 new tests (13 green), including that the numbers are untouched.

**Files:** `backend/app/services/insights.py`, `backend/tests/test_insights.py`

- [x] Step 6.1: findings take an optional label map (column → business name, value → label)
- [x] Step 6.2: narrative and finding sentences use it; numbers unchanged
- [x] Step 6.3: tests — a described column's finding names it in words

### Task 7: Write-through confirmation + the glossary screen — DONE
> `GlossaryPanel` + a Business terms tab on SourceReview; the three endpoints have
> a caller at last, so the BUSINESS TERMS block in the designer's prompt and the
> agent's glossary can finally be non-empty. 7 tests. Admin-gated for writes only.
> Write-through: `PATCH /datasets/{id}/columns/{column}/description` writes a LINKED
> column's sentence to the source catalog at `confirmed`, so describing it once
> describes it for every dataset from that table; an unlinked column writes to its
> own row. The response names where it landed and the UI says so -- a sentence that
> travels further than the box it was typed into must not do so silently. Denied
> columns 404 rather than 403. Its caller is the new Meaning tab on DatasetDetail
> (`ColumnMeaningPanel`), which is also the first place in the product a dataset
> column could be described at all. 4 endpoint + 6 component tests.

**Files:** `backend/app/routers/datasets.py`, `backend/app/routers/metadata.py`, `frontend/src/components/review/GlossaryPanel.tsx` (new), `frontend/src/pages/SourceReview.tsx`, `frontend/src/services/api.ts`

- [x] Step 7.1: PATCH a dataset column's description → writes to the linked `SourceColumn` with `description_source='confirmed'`; unlinked columns write to the dataset row as today
- [x] Step 7.2: `metadataApi.glossary` / `addGlossaryTerm` / `deleteGlossaryTerm` — the three endpoints have had no caller since they shipped
- [x] Step 7.3: a Glossary tab on SourceReview
- [x] Step 7.4: tests both sides — service and HTTP endpoint

## Phase B — the journey

### Task 8: Connecting a database starts understanding it — DONE
> `POST /data-sources` starts a detached sync and returns `sync_run_id`; the
> Connections page sends a NEW connection straight to its review page, where the
> run is already on screen. Never fatal: a sync that cannot start costs a
> convenience, not the connection. 3 tests (16 green).

- [x] Step 8.1: `POST /data-sources` starts a metadata sync for connections that can be introspected
- [x] Step 8.2: the Connections page lands the user on `/connections/:id/review` after a create
- [x] Step 8.3: SourceReview FOLLOWS a sync it did not start. It read the run once
      and froze; now that a create sends people here mid-sync, that snapshot was a
      page with no hint it needed reloading. Guarded on `syncing`/`pollTimer` so it
      cannot race or duplicate the timer `runSync` owns.
- [x] Step 8.4: tests — create returns before the sync finishes; a failed sync leaves a readable state

### Task 9: "Suggest dashboards" from a connection — DONE
> `SuggestFromSourceDialog` on SourceReview calls the endpoint that had zero
> callers. Creation stays client-side (import + report + widgets), keeping the
> backend's "proposes, never creates" contract true. Uses `useModalDialog` --
> `overlayCoverage.test.ts` structurally refuses a hand-rolled Escape handler.
> 6 tests.

`POST /data-sources/{id}/suggest-dashboard` is complete, probe-validated and has zero callers.

- [x] Step 9.1: `dataSourcesApi.suggestDashboard`
- [x] Step 9.2: a dialog on SourceReview — role prefilled from the user's role, free-text goal
- [x] Step 9.3: reuse `DashboardProposals` for the result, so accepting builds dataset + report + widgets by the one existing path
- [x] Step 9.4: refuses clearly when the source has never been synced

### Task 10: A chat answer can become a dataset — DONE
> "Save as dataset" on a connection-scoped answer, composed from the same
> `dataSourcesApi.import` the AI proposals use -- the agent still creates nothing
> on its own, a person pressed a button. Runs the similar-dataset check first and
> honours "no". Absent in dataset mode, where DuckDB frames have no source to
> import from (a dead control is worse than a missing one). 4 tests (50 green).
> Provenance comes free from Task 2: the SQL names its tables, so the new
> dataset resolves its meaning immediately.

- [x] Step 10.1: "Save as dataset" on a chat result that carries SQL and a source
- [x] Step 10.2: reuses `dataSourcesApi.import` — the same call `DashboardProposals` makes
- [x] Step 10.3: the new dataset gets provenance from Task 2 for free

### Task 11: "You already have a dataset like this" — DONE
> `knowledge.similar_datasets` + `POST /data-sources/{id}/similar-datasets`,
> compared on SOURCE COLUMN IDENTITY where provenance exists and on names (marked
> `by_name`) where it does not. Shown in the suggest dialog beside the Create
> button, never instead of it. A test caught the coverage denominator counting
> only RESOLVED columns, which made any 5-column proposal with one catalogued
> column read as a perfect match. 5 service + 2 endpoint tests.

- [x] Step 11.1: `knowledge.similar_datasets(db, source_id, tables, columns, org_id)` — same source, overlapping source columns, ranked by overlap
- [x] Step 11.2: the AI proposal and the save-as-dataset flow show the match and let the user pick reuse or create
- [x] Step 11.3: never blocks — it informs and the user decides

### Task 12: The dashboard suggester asks when it does not know — DONE
> `clarifying_question()` turns a refusal into one short question offering the
> choices the data supports; the endpoint returns it as `question` and the dialog
> renders it with an "Answer this" that keeps the goal already typed. Returns None
> -- and the plain refusal stands -- when there is no model, when the reason IS
> that there is no model, or when the model declines: an invented question would
> be worse than the refusal it replaced. 4 endpoint + 2 dialog tests.

- [x] Step 12.1: reuse `nodes/clarify.py` from the suggest path
- [x] Step 12.2: `SuggestDashboardsDialog` renders the question and sends the answer back
- [x] Step 12.3: still one-shot when nothing is ambiguous

---

## Verification before "done"

- [x] `test_layer_conformance.py` and `test_architecture_doc.py` pass
- [x] Every test file named above runs green. Frontend: 2,402 passed / 0 failed.
      Backend, FULL suite: 4,990 passed, 2 skipped, 0 failed (31 min).
- [~] A live check against a running backend for each new/changed ENDPOINT. NOT DONE
      here: every new endpoint is instead covered by an HTTP-level test through the
      ASGI client (`similar-datasets`, the column-description PATCH, the dataset
      payload, auto-sync on create, the clarifying question), which is the same
      seam a live check exercises. Worth one manual pass against a real Postgres
      before release, because `link_columns` and `stage_link_datasets` have only
      met SQLite here.
- [x] `git diff --stat` shows no file rewritten wholesale
