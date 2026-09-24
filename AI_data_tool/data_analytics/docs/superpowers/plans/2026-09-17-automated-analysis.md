# Automated Analysis → Widget Suggestions — Implementation Plan

> **For agentic workers:** steps use checkbox (`- [ ]`) syntax. Tick a step only after its
> command has been RUN and its output read.

**Goal:** the analytics engine runs itself. A person should not have to know that
`key_influencers` exists, pick a target column for it, and read a lift table — the system
should run what is worth running, on a trigger or a schedule, and turn what it finds into
charts they can accept with one click.

---

## The thing to know before planning anything

**The orchestrator for this already exists and has never run in production.**

`services/automation_runner.py` — 1,800 lines, called "Power Pi" in its own docstring — is a
seven-step chain: `profile → describe → scan → propose → review → compose → notify`. It has
advisory locking so N workers cannot run the same step, `output_ref` as a resume marker so a
restart redoes nothing, per-step backoff, artifact cleanup, and the creator's identity as a
*precondition* rather than a parameter (a headless step would read an unfiltered frame and
build a dashboard from rows the creator may not see — and it would look like success).

`refresh_scheduler.py:887` already ticks it — one step of one run per tick, so a slow chain
cannot starve dataset refreshes.

And `create_run()` is called **only from `tests/test_automation_runner.py`**. There is no
router, no UI, no scheduled creation. The scheduler has been ticking a queue that nothing on
earth can fill.

So the first task below is not "build automation". It is "let a run be created".

## The second thing: what `scan` actually scans

`_scan_step` calls `generate_insights` — the six deterministic detectors in `insights.py`
(trend, standout, laggard, correlation, outlier_impact, data_quality). That is all.

Meanwhile `services/analysis/registry.py` holds **24 registered analyses**: segmentation,
association rules, key influencers, three anomaly detectors, four forecasters, decision
trees, automated prediction, text topics, and nine inferential tests. None of them runs
unless a person opens `StatisticsPanel`, chooses one from a dropdown, fills in its column
parameters, and presses Run.

And `_FINDING_CHART` maps **five** finding kinds to widgets, out of 70 widget types.

That is the gap, stated precisely: *the automation chain runs 6 of 24 techniques and turns 5
kinds of finding into 5 kinds of chart.*

## The seams that make this cheap

Three, all verified in-tree:

1. **`_propose_step` reads the SCAN ARTIFACT**, not the insights engine. It takes `scan.json`
   and runs either `suggest_from_insights` (deterministic) or `suggest_for_dataset` (model).
   **So a new step that appends findings to that artifact flows into proposals, review,
   composition and notification with no changes to any of them.**
2. **`registry.run_analysis(name, df, params)`** is a uniform execution seam, and
   `analysis_contract.AnalysisContract{kind, columns, rows, meta}` is a uniform *result*
   shape. Adapters key off `kind`; they never import an analysis module.
3. **`AnalysisSpec.params_schema`** is JSON Schema with `"format": "column"` markers and a
   `required` list — enough to tell which analyses can run with no parameters at all.
   `segment` and `association_rules` already document "omitted/null means every usable
   column"; they are auto-runnable today, untouched.

**Tech stack:** Python 3.12, FastAPI, SQLAlchemy async, pandas, scikit-learn/pyod (lazily
imported), pytest; React 18, TypeScript, Vitest.

---

## Which analyses may run unattended — and which must not

This list is a design decision, not a configuration. It belongs in the plan because getting
it wrong is how an analytics product becomes untrustworthy.

**Auto-run, no parameters needed** — the spec already defaults every column:
`full_profile`, `segment`, `association_rules`, `anomaly_iqr`, `anomaly_iforest`,
`anomaly_ecod`.

**Auto-run once the profile chooses for them** — a `default_params(profile)` hook per
analysis, driven by roles the profile already computes:
- `key_influencers` — target from `is_flag` columns, then low-cardinality categoricals.
  "What drives X" is the question; the spec already defaults `target_value` to the *rarest*
  value, which is the right default for churn-shaped questions.
- `forecast_ets` / `forecast_simple` — need `structure.date_range` and a measure.
- `text_topics` — needs a text column of sufficient cardinality.
- `decision_tree`, `automated_prediction` — need a target, same rule as key influencers.

**Never auto-run.** Two distinct reasons, and both must be stated in the UI, not just here:

- **They need a question nobody asked.** `goal_seek`, `forecast_goal`, `forecast_scenario`,
  `explain_response` take a *target outcome* or a *scenario*. There is no defensible default
  for "what would it take to reach the goal" when no goal was given.
- **Running them unprompted is p-hacking by machine.** `compare_groups`, `test_independence`,
  `correlation_test`, `regression`, `glm_logistic`, `mixed_model`, `survival`,
  `pairwise_comparisons`. Sweeping nine significance tests across every column pair and
  surfacing the ones that came back p < 0.05 manufactures false findings at exactly the rate
  the threshold promises — on a 40-column dataset that is dozens of confident, wrong
  sentences. These stay user-invoked, where a person has a hypothesis first.

  If they are ever automated, it must be with a multiple-comparison correction applied across
  the whole sweep and the family size stated on every finding. That is a separate piece of
  work and should not be smuggled into this one.

---

## Global constraints

- Analyses run on the **creator's secured frame** from step 1 — never re-read the dataset.
  The frame is already RLS-filtered with the creator's predicate and has their denied columns
  dropped; a second read is a second path to the same rows.
- `apply_rls_filter` call sites are allowlisted by `tests/test_rls_base_frame_choke_point.py`.
  Do not add one.
- Services never import FastAPI (`tests/test_layer_conformance.py`).
- The registry stays import-light: `registry.py` imports no analysis module, because it is
  imported by `main.py`'s router wiring *and* by every agent prompt build. Adapters must not
  break this — they live in a new module the registry does not import.
- **One step per tick.** The `analyse` step must bound its own wall time or it starves dataset
  refreshes and alerts sharing that loop. See Task 3's substep design.
- Adding an analysis has four pins (`test_registry.py` single-source, the agent prompt block,
  `test_step_and_analysis_contracts.py`, the doc-count audit). Adding a finding KIND has its
  own: `_FINDING_CHART`, `suggest_widgets_from_findings`, and the widget-role validator.
- Never propose a widget type the renderer does not have. The 70 real types are in
  `services/widget_roles.py`.
- Doc-count audit: a new test FILE or migration bumps `ARCHITECTURE.md` **and** `.html`.
  Prefer adding to existing test modules.
- Line endings: the index is LF. `git diff --stat` after each edit; only intended lines move.

---

## Task 0: Column metadata the engines can act on — DONE (2026-09-19)

Requested as four fields. It was two new, one widened, one already there — and widening
the existing one uncovered a bug.

**`analytic_role` → widened the existing `column_meta.role`.** It already existed with
`{measure, category, geography}`. But `insights._ROLE_TO_ANALYSIS_KIND` — the map every
engine reads — already understood `timestamp` and `identifier`, which
`routers/datasets._VALID_ROLES` refused on write. **Two classifications the engine acted on
that no endpoint could set:** an author could watch `student_id` charted as a measure with
no way to say it was an identifier. Vocabulary is now `{measure, category, temporal,
geography, freetext, identifier}`, with aliases (`dimension`, `categorical`, `timestamp`,
`datetime`, `geo`, `numeric`, `text`) accepted on write and canonicalised so storage holds
one spelling per concept.

`freetext` fixes a real defect: `detect_types` emits only `numeric | categorical | datetime`,
so a 3,000-distinct-value comments column arrives labelled `categorical` and is a candidate
for a bar chart with 3,000 bars. `freetext → "text"` matches no consumer's equality check,
so it leaves the dimension pickers — and it is how `text_topics` will find its column.

`geography` is deliberately absent from the reader map, so it still falls through to
detection: a country name detects categorical and a latitude numeric, and both are right.

**`hidden_column` → reused `hidden`.** Already exists and is already enforced —
`effective_roles` drops hidden columns from the analysis entirely. A second field with
overlapping meaning is the drift the knowledge layer exists to prevent.

**`eligible_for_suggestion` → new, `column_meta` only, defaults true.** Per-dataset, because
the same column can be worth suggesting in one dataset and noise in another. Distinct from
`hidden` and the distinction is the whole point: hidden removes a column from the pickers and
the analysis; this leaves it fully usable and only stops the platform *volunteering* it.
Enforced at two sites — `suggest_widgets_from_findings` (one ineligible column disqualifies
the whole suggestion, because a chart is about the relationship between its columns) and
`describe_for_prompt` (marked `[do not chart this column - usable as a filter only]`, not
removed: the model may still need it to narrow a chart).

**`target_candidate_priority` → new, on BOTH.** `SourceColumn` (migration `0034`) so it
resolves through provenance like descriptions — `patient_outcome` is an outcome in every
dataset built from that table — with a `column_meta` override per dataset. Resolved by
`knowledge.ColumnKnowledge.target_priority`; `DatasetKnowledge.targets()` returns them
strongest-first, and an ineligible column is never offered as a target.

**What this buys Task 2:** `default_params` stops being a heuristic. Target = highest
`target_priority` among eligible columns. Forecasters need a `temporal` role or a detected
datetime. `text_topics` needs `freetext`. The user turned a guess into a declaration.

Surfaced on the **Meaning** tab (`ColumnMeaningPanel`), which merges into the whole
`column_meta` map before PUTting it — the endpoint replaces wholesale, so a panel sending
only its own column would delete every format and label set elsewhere.

Evidence: 12 new tests (`test_insights.py` 20 green, `test_knowledge_resolver.py` 24 green);
963 passed across the affected backend surface; frontend 129 green on the dataset components;
doc counts bumped to 34 revisions.

## Task 1: Let a run be created

Nothing else in this plan is reachable until this exists.

**Files:** `backend/app/routers/analysis.py` (or a new `routers/automation.py`),
`backend/app/services/automation_runner.py`, `backend/app/services/refresh_scheduler.py`,
`backend/tests/test_automation_runner.py`, `frontend/src/services/api.ts`

- [ ] 1.1 `POST /datasets/{id}/automation` — creates a run for this dataset as the caller,
      returns the run id. Refuses a second run while one is live, the way the metadata sync
      refuses (409 with the honest reason, never a queue position).
- [ ] 1.2 `GET /datasets/{id}/automation` and `GET /automation/runs/{id}` — status, the seven
      steps, which one it is on, what each produced or refused.
- [ ] 1.3 Auto-create on import, at the four commit sites in `routers/data_sources.py` —
      `trigger="on_import"`, created_by the importer.
- [ ] 1.4 Auto-create on scheduled refresh, in `refresh_scheduler` — `trigger="on_refresh"`,
      **created_by the dataset's `created_by`**, because RLS here is per-user and a run with
      no identity has no defensible frame to read. A dataset whose creator is gone does not
      get an automatic run; that is correct, and must be recorded rather than silent.
- [ ] 1.5 Org-level opt-out setting, defaulting ON for import and OFF for refresh — the first
      is a one-off, the second recurs and costs money on every dataset in the org.
- [ ] 1.6 Tests: creation, the 409, org scoping, that an auto-created run carries the right
      creator, that a creatorless dataset records a skip rather than running headless.

## Task 2: Auto-parameterisation from the profile

**Files:** `backend/app/services/analysis/auto_params.py` (new),
`backend/app/services/analysis/registry.py`, `backend/tests/test_registry.py`

- [ ] 2.1 `AUTO_RUNNABLE: dict[str, AutoRule]` — one entry per auto-runnable analysis, naming
      how its parameters come out of a profile **and the column metadata from Task 0**.
      Targets come from `DatasetKnowledge.targets()`, not from a flag heuristic; forecasters
      require a `temporal` role or a detected datetime; `text_topics` requires `freetext`.
      Analyses absent from this map never auto-run, and that absence is the documentation.
- [ ] 2.2 `default_params(name, profile, knowledge) -> dict | None` — `None` means "cannot
      run on this data", which is a normal answer (no date column, nobody has said what is
      worth explaining, no free-text column) and must be recorded by name, not swallowed.
      **"No target declared" is the commonest `None` and the most useful**: it tells the user
      exactly which checkbox turns three analyses on.
- [ ] 2.3 A test that every `AUTO_RUNNABLE` key is a real registered analysis and every
      non-auto-runnable analysis is absent — so adding an analysis forces a decision rather
      than defaulting to silence.
- [ ] 2.4 Tests per rule against a realistic profile (hospital fixture): the declared target
      wins over any heuristic, an ineligible column never becomes a target, a dataset with no
      date yields `None` for the forecasters, and a `freetext` column is what `text_topics`
      finds.

## Task 3: The `analyse` step

**Files:** `backend/app/services/automation_runner.py`, `backend/app/models/models.py`
(a `substep` cursor on `AutomationStep`), a migration, `backend/tests/test_automation_runner.py`

Inserted between `scan` and `propose`, so it inherits the secured frame and the roles and
feeds the artifact `propose` already reads.

- [ ] 3.1 `_analyse_step`: walk `AUTO_RUNNABLE`, resolve params, run each via
      `registry.run_analysis` on a worker thread, adapt to findings, **append to the scan
      artifact's `findings`**, record per-analysis outcome (`ok` / `skipped: no date column`
      / `failed: <exception type>`).
- [ ] 3.2 **Bound the tick.** One analysis per tick, with `AutomationStep.substep` as the
      cursor: the step returns "still going" until the list is exhausted. A single step that
      ran a KMeans sweep and three anomaly detectors over a million rows would hold the shared
      scheduler loop for minutes. Resume semantics come free — the cursor is the same shape as
      `output_ref`.
- [ ] 3.3 A row-count budget from the profile: skip (by name, visibly) an analysis whose cost
      class exceeds what this dataset's size allows, rather than starting it and timing out.
- [ ] 3.4 Never fatal. An analysis that raises is one recorded failure among N, exactly like a
      metadata sync stage; the chain continues to `propose`.
- [ ] 3.5 Tests: findings land in the artifact; the cursor resumes after a simulated restart;
      a raising analysis does not fail the run; a skip names itself.

## Task 4: Finding adapters — the real work

**Files:** `backend/app/services/analysis/findings.py` (new),
`backend/tests/test_analysis_findings.py` (new FILE — bump both doc counts)

`AnalysisContract{kind, columns, rows, meta} -> list[finding]` in `insights.py`'s shape
(`kind`, `score` 0-1, `title`, `columns`, plus the figures the sentence states). One adapter
per `result_kind`; dispatch on `kind`, never on the analysis name.

- [ ] 4.1 `segment` → "your rows fall into N groups; the largest is X% and differs most on Y"
- [ ] 4.2 `key_influencers` → "A is 2.4× more likely when B — 1,240 rows", carrying lift and
      support, and the not-causation caveat the analysis already writes
- [ ] 4.3 `association_rules` → "customers on premium also choose express, 3.1× chance"
- [ ] 4.4 `anomaly_*` → "N rows sit outside the expected range and carry X% of the total"
- [ ] 4.5 `forecast_*` → "at the current trend, X reaches Y by <date>"
- [ ] 4.6 `text_topics` → "the free text divides into N themes; the largest is …"
- [ ] 4.7 `decision_tree` / `automated_prediction` → the dominant split, in words
- [ ] 4.8 Every adapter uses `col_label`/`val_label` (the knowledge layer, shipped
      2026-09-17) so findings read in the business's words, not the schema's
- [ ] 4.9 **Scores must be comparable.** They rank against the six detectors' scores in one
      list; an adapter returning 0.9 for every rule drowns everything else. Each adapter
      documents what its score means, and a test asserts no adapter's median exceeds the
      engine's.

## Task 5: Findings become charts

**Files:** `backend/app/services/insights.py`, `backend/app/services/suggest_from_insights.py`,
`backend/tests/test_insights.py`, `backend/tests/test_suggest_from_insights.py`

Every mapping below names a widget type that exists in `widget_roles.py`.

- [ ] 5.1 `_FINDING_CHART` gains: `segment → scatter` (cluster as series) and
      `parallel_coordinates` as the alternate; `influencer → bar` of lift per factor;
      `association → heatmap`, `sankey` for the strong rules; `anomaly → line` with the
      outlying points marked, `box_plot` as the alternate; `forecast → forecast` (the
      renderer already exists); `topic → word_cloud`; `tree → tree`.
- [ ] 5.2 `suggest_widgets_from_findings` builds a valid config for each new kind — required
      roles present, no arithmetic on identifiers, no personal column as a dimension. The
      existing `_is_id_like_column` correction applies to all of them.
- [ ] 5.3 **Probe before offering.** Every suggested widget is executed and dropped if the
      shaper reports nothing to draw — the rule `suggest_dataset_dashboard.py` already
      enforces, and the reason 92 of 92 widgets once "worked" while six drew blank.
- [ ] 5.4 Tests assert on executed ROWS, never on a config dict.

## Task 6: Surfaces — where the effort actually disappears

**Files:** `frontend/src/pages/InsightsHub.tsx`, `frontend/src/components/StatisticsPanel.tsx`,
`frontend/src/pages/DatasetDetail.tsx`, `frontend/src/services/api.ts`, their tests

- [ ] 6.1 **StatisticsPanel gets "Run everything worth running"** — creates a run instead of
      demanding an analysis name and its columns. The manual path stays: a person with a
      hypothesis must still be able to run one test deliberately, and that is the only way
      the never-auto-run family can be reached.
- [ ] 6.2 **InsightsHub shows automated findings** grouped by technique, each with its
      one-click chart, and each saying which analysis produced it. A finding whose provenance
      is invisible cannot be judged.
- [ ] 6.3 **A status strip on DatasetDetail**: which step the run is on, what it has found so
      far, what it skipped and why. "Not run" must be as legible as "found nothing" — they
      mean different things and only one of them is about the data.
- [ ] 6.4 The never-auto-run family is visibly *offered*, not hidden — with the reason ("needs
      a question first") beside it, so the manual path reads as a capability rather than an
      omission.

## Task 7: Honesty about what was run

**Files:** `backend/app/services/automation_runner.py`, `frontend`, tests

- [ ] 7.1 The run record carries the full roster: every analysis considered, and for each one
      `ran` / `skipped: <reason>` / `failed: <type>`.
- [ ] 7.2 The notify step's message says what was found *and* what could not be looked at —
      a summary that reports only successes trains people to over-trust it.
- [ ] 7.3 A finding never states more than the analysis licenses: correlational analyses keep
      their not-causation caveat through the adapter and onto the chart's note.

---

## Verification before "done"

- [ ] `test_layer_conformance.py`, `test_architecture_doc.py`, `test_registry.py`,
      `test_step_and_analysis_contracts.py` pass
- [ ] `test_rls_base_frame_choke_point.py` passes — no new `apply_rls_filter` call site
- [ ] A run created through the ENDPOINT completes all eight steps against a real dataset and
      produces a report; the service layer being right has repeatedly not meant the endpoint
      was
- [ ] The scheduler tick stays bounded: a run over a large dataset does not delay a dataset
      refresh sharing the loop (measure it, do not assume it)
- [ ] Full backend and frontend suites green
- [ ] `git diff --stat` shows no file rewritten wholesale

## Sequencing note

Tasks 1–3 are the wiring and are worth doing as one unit — they turn an unreachable engine
into a running one, and at the end of Task 3 the existing six detectors plus the six
zero-parameter analyses already flow into proposals. Task 4 is where the time goes. Task 5
is small once 4 defines the shapes. Task 6 is what the user actually sees.
