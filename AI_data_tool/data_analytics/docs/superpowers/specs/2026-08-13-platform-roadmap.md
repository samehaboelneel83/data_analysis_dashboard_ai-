# Platform Roadmap — Remaining SAS VA Feature Parity Sub-Projects

**Date:** 2026-08-13
**Status:** Draft — decomposition only, no implementation yet

## Overview

`COURSE_1_narrations.txt` (SAS Visual Analytics 1: Basics) and `COURSE_2_narrations.txt` (SAS Visual Analytics 2: Advanced) are the full transcripts of the two training courses this rebuild draws its feature list from — together ~150 distinct product features. `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md` decomposed the chart-type portion into its own sub-project (now **complete** — all 28 chart types shipped across Phases 0–3) and named the remaining sub-projects in its "Out of Scope" section: *geo maps, data joins, the expression/calculation engine, interactivity & navigation, display rules & alerts, containers & object templates, advanced analytics/ML, and sharing/export*.

This document is the same kind of decomposition, one level down: it maps every remaining topic in `COURSE_2_narrations.txt` (91 topics across 5 lessons) plus the newly-requested **Row-Level Security** feature onto those named sub-projects (adding two the original list didn't need: Row-Level Security itself, and Custom Graph Builder), gives each a rough scope and a build-order recommendation, and flags what's genuinely SAS-Viya-platform infrastructure rather than an app feature this rebuild should reproduce. Each sub-project below gets its **own** design spec + phased plan + SDD implementation cycle when its turn comes, exactly like chart-type-expansion did — this doc is the index, not the spec.

## Already Delivered

COURSE_2's Lesson 1 "Relationship Plots" topics — Bubble Plots, Correlation Matrices, Fit Lines, Heat Maps, Numeric Series Plots, Parallel Coordinates Plots, Scatter Plots — are **fully shipped** (Phase 2 of chart-type-expansion). Nothing further needed there.

## What Already Exists in This Codebase (don't rebuild)

- **Expression engine core**: `backend/app/services/widget_data.py`'s `_build_safe_ns`/`_eval_expr`/`apply_calculated_columns` already implement `IF`/`SWITCH`, simple aggregation functions (`SUM`/`AVG`/`MEDIAN`/`COUNT`/`COUNTD`/`STDEV`/`VARIANCE`/`PCT_TOTAL`/`NORMALIZE`/`ZSCORE`), running/window functions (`CUMSUM`/`CUMPCT`/`RANK`/`DIFF`/`LAG`/`LEAD`), and group-by window functions (`GROUPSUM`/`GROUPAVG`/`GROUPCOUNT`/`GROUPRANK`/`GROUPMIN`/`GROUPMAX`/`GROUPPCT`). Sub-project 2 below is an *extension* of this (text functions, date/time functions, periodic functions, `IFELSE`-as-syntax, aggregated data sources, scope), not a from-scratch build.
- **Filtering/cross-filter/prompts**: `CrossFilterContext`, per-widget `filters` config, page prompts (`promptFilter`), sort/rank (`running`, `sort_col`) already exist and cover a meaningful slice of what COURSE_2 calls "interactivity."
- **No auth/user system at all**: confirmed by reading `backend/app/models/models.py` (no `User`/`Role` model) and `backend/requirements.txt` (no `passlib`/`python-jose`/`authlib`/similar). Every current router is unauthenticated. This is the real gap Row-Level Security sits on top of.

## Sub-Projects

### 1. Row-Level Security (+ Auth/User foundation) — **not from either course transcript, explicitly requested**

**Scope:** This has no existing foundation to build on, so it's two layers in one sub-project:
- **Auth foundation**: `User`/`Role` models, password hashing + login (JWT or session cookie), a `get_current_user` FastAPI dependency, protecting existing routers.
- **Row-level security proper**: per-dataset (or per-report) row-filter rules keyed to user attributes (e.g. "Sales Rep can only see rows where `region == user.region`"), enforced server-side in `get_widget_data`/`shape_*` so it can't be bypassed by editing widget config client-side — this is the part SAS VA calls "row-level permissions," typically driven by a mapping table (user/group → filter expression) evaluated at query time.

**Not in scope**: SAS's actual RLS implementation lives in CAS authorization (`caslib` ACLs, `IDENTITY_*` macros) — platform infrastructure specific to SAS Viya, not something this FastAPI/Postgres rebuild would reproduce 1:1. The *outcome* (a viewer only sees rows they're authorized for) is the target; the mechanism will be this app's own.

**Recommended build order: 1st.** Nothing else on this list strictly depends on it, but it's the most architecturally invasive (every router gains an auth dependency) and the most likely to reshape assumptions in later sub-projects (e.g. "Sharing Reports" and "Viewer Capabilities" below are meaningless without a user system already existing).

### 2. Expression / Calculation Engine — Advanced (extends existing engine)

**COURSE_2 topics:** Adding Scope to an Aggregated Measure, Advanced Functions (`CoefVar`/`CSS`/`Kurtosis`/`PvalT`/`Skewness`/`First`/`Last`/`Suppress`), Aggregated Simple Functions (`Count`/`Distinct`/`Sum` — mostly already have equivalents), AggregateTable Function, Create/Extract Times and Dates, Difference from Previous Parallel Period, Periodic Functions (`CumulativePeriod`/`ParallelPeriod`/`Period`/`PeriodWithDate`/`RelativePeriod`), Tabular Functions (`AggregateCells`), Text Functions (`Substring`/`FindChar`/`RemoveChars`/`RemoveWord`/`RemoveBlanks`/`Replace`/`ReplaceWord`/`Concatenate`/`FindString`/`GetLength`/`GetWord`/`Reverse`/`URLEncode`), The IFELSE Operator (already have `IF`, this formalizes nested if/else), What is an Aggregated Data Source / Creating an Aggregated Data Source, Data Joins (left/right/inner/full).

**Recommended build order: 2nd** (or 3rd, swappable with #3) — most self-contained, no UI/auth dependency, high leverage (every other sub-project below that touches calculated columns benefits).

### 3. Interactivity & Navigation

**COURSE_2 topics:** Types of Parameters, Using Character/Date/Expression-Based/Numeric Parameters, Links, Page Links, Report Links, External URL Links, Linking from Text Objects, Data Source Mappings, Set Prompt Bar Values.

**Scope:** Parameters (a named, typed, viewer-adjustable value that flows into calc items/display rules/filters), and Links (page/report/URL navigation with optional data-source mapping and prompt-bar-value propagation instead of filtering).

**Recommended build order: 3rd.**

### 4. Display Rules & Alerts

**COURSE_2 topics:** Working with Display Rules, Report-Level/Graph-Level/Table-Level/Gauge-Level Display Rules, Alert with Display Rules.

**Scope:** Conditional styling (color-mapped values, expression-based color/background/icon) at report/object/cell granularity. Alerts (email notification when a data condition is met) needs an email-sending capability this app doesn't have yet — scope that as an explicit decision point in that sub-project's own spec (e.g. SMTP config vs. in-app notification only, no email).

**Recommended build order: 4th** — benefits from Parameters (sub-project 3) existing first, since display-rule expressions can reference parameters.

### 5. Containers & Object Templates

**COURSE_2 topics:** Containers (overview), Precision/Prompt/Scrolling/Stacking/Standard Container, Object Templates, Sharing Object Templates.

**Scope:** Layout containers (the report canvas currently has no grouping/nesting concept beyond the widget grid) and reusable object templates (save a configured widget's options for reuse).

**Not in scope**: "Sharing Object Templates" as described (SAS Environment Manager export/import, CLI transfer plug-in, SAS Infrastructure Data Server) is entirely SAS-Viya-platform-specific — no analog needed in a single-deployment app. If a "reuse this widget config elsewhere" need exists, it's just copy/paste or a template library within this app, not cross-environment JSON export.

**Recommended build order: 5th.**

### 6. Sharing & Managing Reports

**COURSE_2 topics:** Distributing Reports and Generating Alerts, Exporting and Saving Images, Localizing Reports, Managing Reports, Modifying Threshold and Data Limit Options, Report Review Pane, Saving Reports, Sharing and Managing Reports, Sharing Reports, Viewer Capabilities.

**Scope:** Report/image export (PNG/PDF snapshot), i18n/localization, a lightweight review/approval workflow, viewer permission levels (view-only vs. edit vs. admin — this is where "Viewer Capabilities" and general report-sharing permissions live, distinct from but complementary to Row-Level Security's *data*-level restriction).

**Recommended build order: 6th** — depends on the auth/user system from sub-project 1 for anything permission-related.

### 7. Advanced Analytics / ML

**COURSE_2 topics:** Automated Explanation, Automated Prediction, Decision Tree (+ Data Roles and Options, Results), Forecasting, Network Analysis (+ Data Requirements, Examples and Features), Path Analysis, Text Topics, Underlying Factors and What-If Analysis, plus generic "Data Requirements and Examples/Options" for these analytic objects.

**Scope:** This is the largest single remaining sub-project — real ML/stats (likely `scikit-learn` + `statsmodels` for regression/decision-tree/forecasting, `networkx` for network/path analysis, an NLP library for text topics) behind new analytic-object widget types, each running actual model training/inference server-side rather than just shaping/aggregating existing data like every chart type has.

**Recommended build order: 7th** — largest new dependency surface, most valuable done last once the data/interactivity/security foundation is solid.

### 8. Custom Graph Builder

**COURSE_2 topics:** Introducing SAS Graph Builder, Advanced Layouts, Creating Custom Templates.

**Scope:** A visual chart-type designer (build a custom chart composition from primitive marks, save as a reusable template) — distinct from the 28 pre-built chart types already shipped. Lowest-priority/most speculative item on this list; candidate to defer indefinitely or drop, similar to how Vector Plot was flagged low-ROI in the chart-type-expansion spec.

**Recommended build order: 8th, or drop.**

### Explicitly Out of Scope (pure documentation/guidance content, not a feature)

COURSE_2's final lesson — Accessibility Tips, Choose the Best Chart, Choose the Best Control, Consider the Layout, Draft a Plan, Focus on What's Important, Test Test and Test Again — is report-*design* pedagogy (best-practice guidance for report authors), not application functionality to implement. No code deliverable is implied by this content. If ever useful, it could become in-editor tooltips/tips content in a future polish pass, not a sub-project.

### Geo Maps (named in the original spec's out-of-scope list, not found as a COURSE_2 topic)

No dedicated COURSE_2 section covers geo maps directly (it's referenced only in passing, e.g. Automated Explanation's relationship-plot type selection). Treat as its own small sub-project (geo region map, geo coordinate map, geo network map — needs a geography reference dataset and a mapping library) whenever it's prioritized; not otherwise ordered above since neither course gives it a dedicated lesson.

## Suggested Overall Order

1. Row-Level Security (+ Auth) — explicitly requested, foundational
2. Expression/Calculation Engine — Advanced
3. Interactivity & Navigation (Parameters, Links)
4. Display Rules & Alerts
5. Containers & Object Templates
6. Sharing & Managing Reports
7. Advanced Analytics / ML
8. Custom Graph Builder (or drop)
9. Geo Maps (unordered — slot in wherever convenient)

Each item becomes its own `docs/superpowers/specs/<date>-<name>-design.md` + phased plan(s) in `docs/superpowers/plans/`, executed via Subagent-Driven Development exactly like chart-type-expansion — this roadmap doc is not itself a plan and contains no tasks to execute directly.
