# Guided setup v2 — from "a dashboard" to "the answer"

Date: 2026-10-10 · Branch: `emad` · Follows [PLAN.md](PLAN.md) and [EVALUATION_REPORT.md](EVALUATION_REPORT.md)

## 1. What the owner asked for

1. **Parallel flows.** After a first run (steps 1–4), start again from step 2 with other data and reach a second dashboard, without losing the first. Several flows side by side on one connection.
2. **Step 3 simple.** Clean abnormal things (duplicate rows, …) automatically, tell the user in a short summary what was found and solved, keep every detail and manual edit behind a button, and let the user undo any automatic decision.
3. **Step 4 gives the demand, not "any data, any charts".** If the user said "I need SUV cars", the dashboard is about SUV cars — not all types with a filter to find. Simple charts first; advanced charts only when the data needs them to answer the demand.

## 2. Why it happens today (read from the code)

| # | What the user sees | Cause in the code |
|---|---|---|
| A | A second run from step 2 replaces the first | `SetupJourney` is unique per (user, connection) and holds one `brief`, one `dataset_ids`, one `proposals`, one `designs`, one `report_id` (`models.py`, `uq_setup_journeys_user_source`). `Setup.tsx` `onDone` overwrites `dataset_ids`. |
| B | Step 3 is a list of problems, each waiting for a click | `_check_one` only reports; nothing is applied until `POST …/fix`. A fix appends a prep step with no mark of where it came from, and there is no undo — `fixed` only remembers that the button was pressed. |
| C | "I need SUV cars" → dataset and dashboard hold every type | The demand is never made into a fact. It stays free text in four optional boxes, called "hints, never rules" in every prompt. The dataset prompt tells the model to make the first proposal "the broad one". Nobody checks that "SUV" is a real value of a real column. |
| D | What the user typed in the dataset chat is forgotten | `design_goal()` sends the designer the brief + health lines + insights only. The chosen proposal's `purpose`, `includes`, `leaves_out`, `why` and its chat `history` are **not** sent. The designer does not know what the dataset was made for, or whether it is already narrowed. |
| E | Charts that are varied rather than useful | The designer prompt asks for **3 genuinely different dashboards**, 4–8 widgets each, and says "vary the shapes". Every widget type the data can support is on the menu with equal weight. This pushes toward variety and advanced charts. |
| F | Charts that draw but say nothing | The gate (`suggest_for_dataset.gate`) accepts a chart when it is valid and returns rows. It does not ask "does this answer one of the person's questions?" or "is the result worth reading?" (already item 1 of the evaluation report). |
| G | The user must filter to find their subject | A dashboard has no scope of its own (`Report` has no filter field). The designer adds slicers and leaves the narrowing to the user. |
| H | The user chooses between three lists of chart titles | `DashboardStep` shows titles and reasons, no picture, no answer. The answer only exists after opening the builder and reading the charts. |
| I | "Change it" starts again | `write_design_change` asks for a whole new design (`count=1`) with the request appended to the goal; charts that were fine can disappear. |

One sentence: **every step understands the person, but the understanding is passed forward as loose text and thrown away at each step.** The plan makes it one confirmed object that every step must obey.

## 3. The idea: one confirmed **Demand** per flow

**Any database.** Cars and "SUV" in this document are only the owner's example. Nothing in the design may know a domain: no column names, no word lists, no chart chosen by subject. The subject, its column and its values are always found in the connected data itself (a hospital's "emergency cases", a shop's "returns in the Riyadh branch", a school's "grade 10"), and every phase is tested on databases of different shapes (§4 acceptance, §5 phase 6).

A small structured record, written once by the AI from everything the person said, shown to them in one plain sentence, corrected by them if wrong, then **binding** on steps 2, 3 and 4.

```json
{
  "sentence": "SUV cars for sale: how price changes with year and mileage, and which brands are cheapest.",
  "who": "used-car dealer in Cairo",
  "scope": [
    {"said": "SUV", "column": "body_type", "op": "in", "values": ["SUV", "Crossover"],
     "matched_rows": 4812, "of_rows": 58498, "status": "confirmed"}
  ],
  "questions": [
    {"id": "q1", "text": "What does an SUV cost, typically?", "measure": "price", "agg": "median"},
    {"id": "q2", "text": "Which brands are cheapest?", "measure": "price", "by": "make"},
    {"id": "q3", "text": "How does price fall with age?", "measure": "price", "by": "year"}
  ],
  "exclude": ["seller phone numbers"],
  "cannot": []
}
```

Rules:

* **Sources:** About you, the Understand words, the chosen dataset proposal (purpose / includes / leaves out / why) and every chat message typed in steps 2–4.
* **Scope is verified, not guessed.** Each scope word is matched against the real distinct values of the candidate columns, run as the person (D1 unchanged). "SUV" may be `body_type = 'SUV'`, or `'Sport Utility'`, or two values. Zero matches → the step says so plainly and asks ("We found no 'SUV' in this data. The types are: Sedan, Hatchback, 4x4 … which do you mean?"). No silent broad fallback.
* **Asked once, kept** (owner rule): written when the person presses Create in step 2; rewritten only when they edit it or chat a change.
* **Plain first:** the user sees the sentence and "Not right? Change it". The columns, values and row counts are behind *Show details*.

## 4. Plan

### Part 1 — Parallel flows (steps 2 → 4, many per connection)

**Data.** New table `setup_flows` (migration `0061`): `id, journey_id, org_id, user_id, name, step, demand, brief, dataset_ids, proposals, findings, cleaning, designs, report_id, created_at, updated_at`. The journey keeps what is shared: the Understand `summary` and the person's `work` ("who they are" is asked once for all flows). The migration moves each existing journey's step 2–4 fields into its first flow, so nothing in progress is lost.

**Backend** (`routers/guided_setup.py`):
* Step 2–4 routes take a flow: `/setup/{source_id}/flows/{flow_id}/datasets|check|dashboard…`. The current routes stay and answer for the newest flow, so open pages and Home links keep working.
* `GET/POST /setup/{source_id}/flows` — list, start a new flow (starts at `data`), rename, archive.
* Background job tags and `_failer` use the flow id (`proposals:{flow.id}`), so two flows can work at the same time.
* `findings_for_dataset` and `my_journeys` read flows.

**Frontend:**
* Setup header: a flow strip — "SUV prices ✓ · Sales by branch · step 3 of 4 · **+ New analysis**". Step 1 is shown as done for every flow after the first.
* The Dashboard step's end and the "already made" card offer "Start another analysis from this database".
* Home "Continue setting up" lists unfinished flows by name; a connection's menu shows its finished ones with their dashboards.
* A flow's name is the Demand sentence shortened; editable.

**Done when:** two flows on Cars DB (SUV prices; real-estate prices) both reach their own dashboard, each can be reopened at any step, and creating datasets in one while the other is designing works.

### Part 2 — Step 3: cleaned for you, said in one summary, undo on everything

**What the user sees** (one card per dataset; Next is enabled as soon as cleaning ends):

> **Your data is ready — 9,107 rows.**
> We fixed 3 things for you: removed 212 copied rows · removed extra spaces in "city" · left out 2 columns that were empty.
> 2 things to know: 254 old cars show under 10,000 km (left out of charts) · prices have a few extreme values (charts use the typical price).
> [Show details] [Undo all]

*Show details* opens today's full list (what / why / what to do), each line now showing its state — **Fixed for you · Undo**, or **Fix it**, **Warn me on every refresh** — plus the link to Rules & alerts. Nothing is removed from the app; it moves behind the button (D6, plain-first rule).

**What is done automatically** (proposal — the owner decides the last row, see §6):

| Found | Automatic action | Why it is safe |
|---|---|---|
| Exact copied rows | remove copies | said in the summary with the count; undo |
| Extra spaces | trim | no information lost |
| Numbers stored as text | make it a number | no information lost |
| Column ≥ 90% empty or one value in every row | leave the column out — **unless the Demand uses it** | nothing chartable in it |
| "Unknown" codes (−1, 9999) | leave those values out of calculations | they are not real values |
| Text column with blanks | show blanks as "Unknown" | so they appear as a group |
| Impossible values (negative price, generic rules) | leave those rows out | verified on rows, ≤ 10% |
| Rules the AI proposed across columns (old car with 180 km) | leave those rows out **and list them under "things to know"** | each rule is already verified on the rows; this is the one class that rests on AI judgement |
| Future dates, extreme values | **not** removed; told to the designer (median, not average) | may be true data |

**Backend:**
* `services/guided_setup/cleaning.py`: `plan(items, demand)` picks the automatic actions; `apply()` adds the prep steps in one call, each marked `{"origin": "setup", "flow": id, "item": "<finding id>"}`; then the dataset is checked again so the counts shown and the insights are those of the cleaned data. Kept in `flow.cleaning`: per action — what, rows before/after, the prep step's mark.
* `POST …/check/{dataset}/undo` (one action or all) removes exactly the marked steps through `set_prep_steps` (same permission and validation as by hand) and moves the line back to "Fix it". `POST …/redo` for symmetry.
* Runs once per dataset per flow (owner rule); "Check again" re-plans without re-applying what the person undid (undone items are remembered).
* **Only on datasets this flow created.** An adopted dataset already has dashboards; there, step 3 keeps today's "Fix it" behaviour and says why.
* The model writes the two summary sentences from the action list; every number is checked against the list before it is shown (evaluation item 5). No model → sentences from templates, same content.

**Done when:** on a dataset seeded with copies, spaces, a −1 code and an empty column, the step shows one summary, the dataset's prep steps hold the four marked steps, Undo of one restores its rows, Undo all restores everything, English and Arabic.

### Part 3 — Step 2: write the Demand and make the data match it

* On Create, a background job writes the Demand (§3) and verifies its scope. The step shows the sentence before moving on: **"You want: SUV cars for sale — … [Yes, continue] [Change]"**. This is the single extra confirmation in the journey; it is where "I said SUV" becomes a fact.
* Dataset prompt change (`datasets._rules`): when the person named a subject, **the first proposal is that subject**, and says so in *Leaves out* ("Other body types — 53,686 rows"). The broad dataset becomes the second option ("All cars, to compare SUVs with the rest"). Today it is the reverse.
* After the test run, each proposal is compared with the scope: `scope.status = "in_data"` when the dataset holds only matching rows, `"in_dashboard"` when it is broader. Step 4 reads this instead of guessing.
* Missing column for a question → `demand.cannot` gets a plain line and the existing **Change the data** is offered right there ("Your question needs the seller's city; add it?").

### Part 4 — Step 4: one dashboard that answers the Demand

**4a. Design from questions, not from columns.** New `services/guided_setup/answer.py`, used by the setup only (the Dashboards page's designer is untouched):

1. Take the Demand's questions in order (most important first; 3–6).
2. For each, the model picks measure / breakdown / time from the dataset's columns — a small, strict output — and the **result is computed first**.
3. The chart is chosen from the result by a fixed ladder, not by the model's taste:

| The answer is… | Chart |
|---|---|
| one number | KPI (with a comparison when there is one) |
| a number per category, ≤ 12 | sorted bar |
| a number per category, > 12 | top 10 bar + "others", full list in a table |
| a number over time | line |
| parts of a whole, ≤ 5 parts | donut; more → bar |
| the records themselves | table (with links clickable) |

4. **Advanced charts only on a trigger**, each with its reason shown under *Show details*: relation between two numbers asked → scatter; two categories at once → heatmap; "how spread / typical range" asked → box plot or histogram; place column and a "where" question → map. No trigger → no advanced chart. The designer's "vary the shapes" instruction does not apply here.

**4b. Scope is applied, visibly.** If `in_data`: nothing to do, the title says it ("SUV cars — prices"). If `in_dashboard`: the scope is written into every widget's `filters` **and** shown as a chip at the top, "Showing: SUV · Show all types", which the user can turn off. Never a bare slicer the user must find. *To verify while building:* the simplest home for the chip — a slicer with a preset selection, or a new `scope` field on the report read by `widget_data`. The second is cleaner (one place, every widget, also Ask AI and export) and is the recommendation.

**4c. Meaning gate** (evaluation items 1 and 4), on every computed result before it is kept:
* flat (all values nearly equal), tied top-N, a KPI of exactly 0 on a change, one bar only, > 60% "Unknown" → replaced by the next-best reading of the same question, or dropped with the reason kept.
* every widget carries the `question id` it answers; a widget with none is dropped.
* every question ends with a widget **or** a plain line "This data cannot answer … because …".
* the existing `repair_and_check` rules stay in front (no sums of rates, no mixed units).

**4d. The answer first.** The top of the dashboard is a short text block: 2–3 sentences answering the Demand with the numbers of the charts below ("The typical SUV costs 1.25M EGP. Chery and MG are the cheapest brands; price drops about 9% per year of age."). Written by the model from the executed results only; each number checked against them; no model → omitted, the KPIs carry it. Layout: answer → KPIs → the main question's chart → supporting charts → the records table.

**4e. Several suggestions, one dashboard with pages** (owner, 2026-10-10). The step keeps suggesting several designs as today, but each is a different **angle on the same Demand** (for example: the overview, the comparison, the change over time, the records) -- never the same page reordered, never a page off the subject. Each card shows the design **drawn** (real charts, read-only) with its answer sentence, not only a list of titles.
* The user ticks one or more. **One dashboard is created; each ticked design becomes a page of it**, in the order ticked, each page named after its angle. Ticking one gives a one-page dashboard. Never several dashboards from one flow.
* The scope chip (4b) and the answer block (4d) are on every page; a chart that would repeat on two ticked pages is kept on the first only.
* Build: `buildDashboard` creates the report and its first page, then `reportsApi.addPage` + the existing `fillPage(reportId, pageId, proposal)` per further design; derived fields are created once for all pages. `flow.report_id` stays a single id.
* Coming back later: "Add a page" offers the designs not yet used, and "Suggest again" (on the button -- owner rule) offers new angles; both add pages to the same dashboard.
* "Change something" (chat, per design or on the made dashboard) edits the kept design -- add / remove / replace named charts, change scope -- and updates the Demand when the request changes what they want. Charts not mentioned stay.
* After opening: one line in the builder, "Did this answer what you wanted? Yes · Not yet -- tell us what is missing", which feeds the same change path. Start blank is kept.

**4f. Speed.** The Demand and the question→result work start when step 3 starts, so step 4 usually opens with the dashboard ready. Progress says which part is running ("Answering question 2 of 4").

**Done when** (acceptance, run as a user in the browser, English and Arabic, on at least three databases of different shapes -- Cars, EGX Stocks, the hospital test data -- with a subject taken from each):
* Cars DB, "I need SUV cars, prices by brand and year" → Demand sentence shown and confirmed; dataset or dashboard holds only SUV rows; no chart shows other types; first tile is the answer; only KPI / bar / line / table unless a trigger fired; no flat or tied chart.
* Ticking three suggested designs creates **one** dashboard with three pages, scope and answer on each; ticking one creates one page.
* Same connection, second flow "apartments in New Cairo under 5M" → its own dataset, cleaning and dashboard; the first is untouched.
* A subject that does not exist ("electric trucks") → asked which value is meant, nothing broad built silently.
* EGX Stocks, "which stocks grew most since 2020" → needs "growth over a period" (evaluation item 2): build it as a result type in `answer.py` (first vs last value per entity); without it this question lands in `cannot`.
* AI off or down → Demand from the boxes as typed (scope matched by plain text search on values), ladder charts from the statistics, no answer text; the journey still ends in a scoped dashboard.

## 5. Order of work

| Phase | Content | Size |
|---|---|---|
| 1 | Demand: schema, writer, scope verification, confirmation line in step 2, dataset prompt order (Part 3) | M |
| 2 | Answer designer: questions → results → ladder → meaning gate → scope → answer text (4a–4d) | L |
| 3 | Dashboard step: drawn suggestions, tick several → one dashboard with pages, add a page later, change-in-place, feedback line (4e–4f) | M |
| 4 | Step 3 auto-clean, summary, undo (Part 2) | M |
| 5 | Flows: table, migration, routes, flow strip, Home (Part 1) | M |
| 6 | Full browser run on Cars DB, EGX, hospital, a non-admin, Arabic; update EVALUATION_REPORT | S |

Phases 1–3 come first because they are the owner's main complaint (the result is not the demand). Phase 5 is independent and can be done in parallel by a second person; if it goes first, phases 1–4 write to `setup_flows` from the start and no field moves twice — **recommended if one person does all of it: 5 → 1 → 2 → 3 → 4 → 6.**

Tests with each phase: backend unit tests beside the existing `test_guided_setup_*.py` (scope matching, ladder, gate, undo marks, migration); frontend tests beside each step. Do not run the backend suite inside the live backend container while the app is in use.

## 6. Decisions (owner, 2026-10-10)

1. **AI-proposed rules in auto-clean:** applied automatically, always named in the summary with their row count, with undo.
2. **Subject narrowing:** in the dataset first (smaller, faster, nothing to filter); the broad dataset is offered second.
3. **Step 4:** keeps several suggestions; the ones the user ticks become pages of ONE dashboard (4e).
4. **Copied rows:** removed automatically in every case, stated with the count, with undo.

## 7. Not in this plan

Uploads in the guided setup, "ask an admin to create this dataset" for non-admins, classifying numeric columns once for every engine (evaluation items 3, 9, 10) — still worth doing, not needed for this goal. The meaning gate in 4c is written so the Dashboards page's designer can adopt it later.
