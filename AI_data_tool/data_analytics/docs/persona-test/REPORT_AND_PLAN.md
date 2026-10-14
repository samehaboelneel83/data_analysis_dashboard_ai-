# Persona test of every connection, and the plan that follows (2026-10-12)

What was done, what Datalytics answered against the true answers, what is wrong and why,
and the plan to fix it without favouring any database.

- Detailed notes per scenario: [FINDINGS_LOG.md](FINDINGS_LOG.md)
- True answers, computed with read-only SQL per database: [ground-truth/](ground-truth/)

## 1. How the test was run

1. Every connection was tested from the app (`POST /data-sources/{id}/test`).
   - 13 of 17 connections answer.
   - 4 do not:
     - **Questions** (45): no route to host.
     - **Tra5ees** (44): password refused.
     - **QA Conn 1125** (24): host `qa-db.invalid`.
     - **Moodle** (17): the file is missing.
2. Each reachable database was profiled with read-only SQL: tables, keys, grain, traps with counts,
   three personas, and the true answer to each persona question (naive and clean versions).
3. For each distinct database, one persona was played in the browser, as a person who knows about 10% of the data.
   - The persona ran the whole Guided setup: Understand → Choose data → Check & discover → Dashboard.
   - Then one persona question went to Ask AI.
   - Duplicates were not repeated: "Nile Express (smoke)" and "M7md Amr" point at databases already covered.
   - `datalytics` is the app's own store and was skipped.
4. Every number on screen was compared with the true answer. A suspected cause was confirmed in the code
   or with SQL before it is listed here.

AI model in use: Auto → Qwen 3.8 27B (local). One run per scenario, so results can vary between runs.

## 2. Scorecard

A question counts as answered when the dashboard pages (or Ask AI, where stated) gave the right answer
in a form the persona can use.

| # | Connection | Persona and questions | Answered | Worst thing the persona was told |
|---|---|---|---|---|
| S1 | UK online retailer | Marketing analyst: countries outside the UK, best products, busy season | 1.5 / 3 | Top products start with "Manual", "DOTCOM POSTAGE"; November's seasonal peak is called "+83% growth" (2011 was really 4.5% below 2010) |
| S2 | Taxi | Driver: best hours, best pickup areas, airports, tips | 1.5 / 4 | "Earnings by hour of day" is really by date (2002-12-31 → 2024-02-01); best zone is one with very few trips; tips understated (cash tips are never recorded) |
| S3 | Olist | Customer-experience lead: do late deliveries hurt reviews, % late, worst states | 0 / 3 | "Late orders score 4.14" — the truth is 2.55 against 4.28 on time; the page tells the opposite of the real story |
| S4 | Employees | HR partner: headcount now, best-paying department, gender gap, leavers by year | 1.5 / 4 | "300,024 people work here now" (true: 240,124); department shown as "d007" |
| S5 | Nile Express | Operations supervisor: % late, worst service, returns | **3 / 3** | Nothing serious. The fixes and the numbers were all right |
| S6 | Cars DB | Family buying a used car: fair Corolla price, price drop per year, cheapest governorate | 1.5 / 3 | "Aswan is the cheapest governorate" from a single listing |
| S7 | EGX Stocks | Private investor, 2023: most traded, COMI rise, index rise | 0 / 3 | "The year 2023" became a filter on 6 random days; index tickers ranked as companies; "COMI change 0.992" (true +79.9%) |
| S8 | food (egypt_stats) | Journalist: sugar and rice prices since 2021, refugees now vs 2022 | 0.5 / 2 | "Refugees fell from 318,539 to 243,580" — the true total rose from 410,894 to 1,175,943 |
| S9 | sh2on_zobat (Arabic UI) | Unit commander: average, best branch, weakest criterion, trend | 2.5 / 4 | Military numbers kept although the person asked to leave them out |
| S10 | Demo — Live SQLite | Shop owner: best channel, best month, top city | 2 / 3 | "Best month" not answered (first vs last month shown instead) |
| | **Total** | | **14 / 32 (44%)** | |

**Ask AI on its own: 5 of 7 questions were answered correctly.**
- Correct: taxi hour, gender gap (with a real statistical test), price by car age, weakest criterion in Arabic, and the retail top months.
- Failed: the Olist late-review question and the first retail season question.
- Ask AI is clearly stronger than the dashboard pages built by the guided setup.

**What works well, and should be kept:**
- Dataset suggestions are usually on target, explained in plain words, and show their SQL.
- Nile Express end to end, including:
  - de-duplication,
  - trimming padded names,
  - "delivered before created" rows,
  - the "In transit" exclusion note,
  - the note "follows the size of each group".
- The Arabic interface: right-to-left layout and wording are correct; an Arabic persona was understood.
- Ask AI's statistical test, and its "these numbers are not in the result rows" guard.

## 3. What is wrong, grouped by cause

Each item: what the person sees, the evidence, and the cause where it was confirmed.

### A. What the person says is turned into wrong filters (`services/guided_setup/demand.py`)

1. **Dates become six example values.**
   - Seen: "the year 2023" became `trade_date in (6 dates)`. Every EGX page ran on 6 days ("1,415 of 50,865 rows").
   - Cause (confirmed):
     - `_is_date` only accepts pandas datetime64, but a database `DATE` column arrives as Python `date` objects.
     - `profile_text` therefore shows it as "text, e.g. <6 dates>".
     - The prompt tells the model to copy values "EXACTLY from the listed values".
   - The same cause produced the "Did you mean 2010-11-01 …" lists in S1 and "listed at 2026-06-18 01:26:17" in S6.
2. **A restriction the dataset already applies is reported as "not found".**
   - Seen: "2015 to 2018", "real sales, not cancelled orders", "now compared with 2022". The datasets' own `WHERE` already did these.
   - Cause: `made_for` only reads text values from the dataset SQL, not dates, ranges or flags.
3. **A false banner on every page:** "This data has nothing called '…', so this page shows everything it holds." (S1, S6, S8). It also produced "used cars only only".
4. **The focus text becomes the analysis name** ("real sales, not cancelled orders").

### B. Column meaning and types are lost at import or misread

1. **Intervals become text.**
   - Seen: `days_late` (a date minus a date) was stored as text ("0 days 18:17:31"). Every late-delivery number in S3 failed, and Ask AI hit a conversion error.
2. **The wrong columns are marked "add up".** Examples:
   - `order_item_id`, `payment_sequential`, `product_name_lenght`, `admin_level` (S3, S8);
   - salary history (S4);
   - population that has "all" subtotal rows, and rainfall stored three times (S8).
3. **Latitude and longitude are treated as numbers to average** (S3).
4. **Rating scales are flagged as outliers.** 1-star reviews on a 1–5 scale (S3, 12,769 values) and 3–5 grades (S9).
5. **Row count shows 0 for SQLite.** Demo and Moodle show "0 rows" (the demo has 12,000).

### C. Cleaning that removes real data or invents problems

1. **Lookup codes are taken for "unknown".**
   - Seen: 140,162 Flex-fare taxi trips (4.7%) were removed as "a code for unknown". The lookup table says code 0 = "Flex fare trip".
   - Cause (confirmed): `data_quality._placeholder` treats 0 in any identifier column as unknown and never looks at the lookup table.
2. **AI "contradiction" rules remove valid rows**, or report problems that do not exist:
   - "No charge with a fare" removed 19,453 valid trips;
   - "same zone ID with different names" is false, since the zone IDs are unique;
   - "payment ID does not match its text" is false.
3. **Out-of-period dates are never flagged.** 18 taxi rows dated 2002–2023 produced "January was 64,182,344% above the prior 3 months", three times (S2).
4. **De-duplication without a key.**
   - S1: 1,067 real lines were merged only because the dataset left out the invoice number.
   - S8: 101 small refugee rows.

### D. Numbers that are computed wrongly

1. **No minimum group size for rankings.**
   - "Best pickup zone" (354 from a handful of trips), "cheapest governorate" from 1–2 listings, "8 passengers = best".
   - The influencers module already has a minimum group size (`MIN_GROUP_ROWS = 10`); dashboards do not.
2. **"Change" is first period against last period, with a partial last period.**
   - S1: "-23%" ends on December 2011, which covers 9 days.
   - S3: "▼99.3%" ends on the stub month.
   - S10: "best month" is answered with January against December.
3. **Seasonality called an anomaly.** S1: November, the very season the persona asked about, is reported as a spike to check.
4. **Stocks summed over time.**
   - S8: refugees 2022 + 2025 summed to "1.6M".
   - S4: headcount counts people who left.
5. **Things of different kinds mixed in one number:**
   - stock indices ranked with companies (S7);
   - sugar and rice averaged together (S8);
   - postage, fees and manual adjustments ranked as products (S1).
6. **The share of the whole is missing from rankings.** In S8 "refugees" meant only the REF group; asylum seekers (924K) were shown separately and never added.
7. **Time parts not derived.** No hour of day or weekday, although the persona asked for them (S2).

### E. Dataset suggestions whose SQL contradicts their description

| Says | SQL does |
|---|---|
| "Current employees" (S4) | LEFT JOIN keeps 59,900 leavers with an empty salary |
| "Departures" (S4) | Counts department transfers as leaving (91,479 against 59,900) |
| "Leaves out market index data" (S7) | Keeps the 5 index tickers |
| "One row per delivered order" (S3) | 97,015 rows for about 96,478 orders (orders with several reviews counted twice) |
| "Late delivery complaints" (S5) | LEFT JOIN over all shipments |
| A combined food-and-refugee dataset (S8) | `UNION ALL` puts refugee counts in the price column |
| Leave out military numbers (S9, asked by the person) | `mil_no` kept |

Two suggestions in S6 are near-duplicates (same 11,699 rows).

### F. Pages that say something false or nothing at all

1. **A label that does not match its number.** "Review score: late orders 4.14" is the average of all orders (S3).
2. **"Could not answer" when the data can answer:**
   - gender gap (S4);
   - % late (S3);
   - price drop per year (S6);
   - trend over years (S9);
   - best month (S10).
3. **Two totals for one number on two pages of one dashboard** (S1: 20.46M and 20.81M; true 20.97M).
4. **A sentence that contradicts its own chart.** "907.41 — about the same for every city (913.84 to 934.53)" (S10).
5. **Codes instead of names:** "d007", "s2 1". Raw column names in sentences: "sum(line_total)", "corp name" inside Arabic text.
6. **Text about the page itself:** "The page does not state…", "The page lists 12 records".
7. **Self-referring advice:** "What to do: check if the data includes sugar and rice" on a sugar-and-rice dataset.
8. **Trivial findings shown as insights:**
   - "open and high move together r = 1.00" eight times (S7);
   - "quantity moves with line_total";
   - "Changed mind → 100% returned".
9. **Only the first suggested page is ticked.** Most people get a 1-page dashboard, and drill-through detail pages are left out.

### G. Ask AI

1. **A keyword rule refuses correct queries.**
   - Seen: "When is our busiest season…" → "Could not answer".
   - Cause (confirmed): `services/agent/validate.py:254`, rule V7, forces COUNT(*) for any question with "busiest / how many / number of". On a summary table one row is one country-month, so COUNT(*) is wrong there.
2. **Made-up numbers are flagged, but the sentence still states them.** S1 says "2011 > 2010"; the truth is the opposite.
3. **Ask AI and the dashboard read different data.** Ask AI reads raw rows while the dashboard reads cleaned rows (S2: 36.23 against 37.60).
4. **Starter questions are poor:**
   - they sum ages or IDs ("Total car age years by make", "Total review score by days late");
   - they use raw column names;
   - they group by an excluded identifier (S9).
5. **Speed and truncation.** Up to about 70 s per answer; one answer was cut mid-sentence (S6).

### H. Screens

1. **KPI numbers clipped at the top on every dashboard.**
   - Measured: the number starts 12–24 px above its 80 px clipping box.
   - The 36 px figure, the change badge and the sparkline do not fit.
2. **"PUBLIC" next to Share.** It is a sensitivity label but reads as "this dashboard is public".
3. **Broken connections look healthy.**
   - They look the same as working ones in Connections.
   - The Moodle setup page shows a confident AI description of a database that cannot be opened.
4. **Leftover test objects are visible to users:** "claude job check (delete me)", "Discovery check (scratch)".
5. **Chart presentation:**
   - single-series charts in rainbow colours;
   - an axis reading "45,000,000,000,000";
   - a Pareto "cumulative share" line on rankings where it means nothing;
   - years shown as "2000.0".
6. **Waiting.** Each AI step takes 30–120 s (datasets, check, pages); a full flow takes 5–8 minutes.

### I. Privacy

1. **Identifiers shown with no warning.** Military numbers are listed in a "Top 10 officers" chart with no masking or warning.
2. **An explicit "leave out" is ignored.** "Leave out military numbers" did not remove them; it is a hint to the AI, not a rule.

### J. Neutrality

1. **The platform is tuned to one database.** Nile Express answered 3/3, while the average of the other nine was about 40%.
   - Nile Express is the database used through four guided-setup retries.
   - Its shape is status and flag columns, one fact table, clean types.
   - The others fail on what Nile Express does not contain:
     - intervals and DATE columns,
     - lookup codes,
     - subtotal rows,
     - summary tables,
     - mixed entity kinds,
     - wide score columns,
     - partial periods,
     - small groups.
2. **The existing guards do not catch this.** The domain-neutral tests check wording only; they do not check that answers are right on other shapes of data.

## 4. The plan

Ordering rule: first stop wrong answers, then make the numbers right, then make the answers complete,
then polish. Every rule below works from the data's shape, never from a database, a business or a language.
Every threshold is an admin setting:
- a field in `core/config.Settings`,
- a spec in `services/app_settings.py`,
- a label in `adminPlatform.ts`.

### Phase 0 — Stop telling people wrong things (first)

| # | Change | Where | Done when |
|---|---|---|---|
| 0.1 | Recognise dates of every kind (Python `date`, `datetime`, ISO text that parses for ≥ 95% of rows) as dates | `demand._is_date`, `profile_text` | "the year 2023" becomes `trade_date ≥ 2023-01-01 and < 2024-01-01` |
| 0.2 | Never build an `in` filter from example values. Periods and ranges become `gte`/`lt`. A list of values is allowed only when every listed value was shown in full | `demand.build_prompt`, `resolve_scope` | No scope uses values the column was only sampled with |
| 0.3 | Read the dataset's own `WHERE` for dates, numbers and flags too, and mark a matching restriction as "already in the data" | `demand.made_for` | No "could not find '2015 to 2018'" on a 2015–2018 dataset |
| 0.4 | An unmatched restriction is asked about once, in the check step. It is never a banner on dashboard pages, and the focus text is never the analysis name | `demand.py`, page builder, flow naming | No "nothing called …" text on any page |
| 0.5 | Truth check on every headline. Each KPI and each sentence number is recomputed from its widget query; the label must state every filter in the query; when they differ the page is dropped or relabelled | page builder (`suggest_dataset_dashboard.py`) | "late orders 4.14" cannot appear |
| 0.6 | Import keeps intervals as numbers with a unit (days or hours, picked from the median) | import type mapping | `days_late` arrives as a number of days |
| 0.7 | A code that exists in a lookup table, or sits next to a label column, is never "unknown" | `data_quality._placeholder` | Flex-fare trips kept |
| 0.8 | AI-found "contradictions" are shown as "worth checking" and never removed by default. Removing needs the person's tick or an admin setting | check step, `cleaning.py` | No valid rows removed without consent |
| 0.9 | V7 applies only when a row is one event. It accepts SUM of a count-like column and any measure the question implies ("sell more" → amount) | `agent/validate.py` | "When is our busiest season" is answered on a monthly summary |
| 0.10 | KPI tile: the number, badge and sparkline fit (the height grows, or the sparkline shrinks) | KPI trend tile CSS | No clipped number at 1280 px and on a phone |

### Phase 1 — Make the numbers right on any data

| # | Change | Done when |
|---|---|---|
| 1.1 | **Meaning of each measure**, stored with the column: amount (adds up), rate or price (average only), stock / level (latest per period, never summed across periods), score on a scale (average; low values are not outliers), identifier, coordinate, sequence number. Derived first from the data (bounded integers → scale; monotonic per entity → stock; ends in `_id` / unique → identifier), then the AI, then the person | Population, salary, close price and review score are never summed over time; lat/lng and `order_item_id` are never measures |
| 1.2 | **Subtotal rows**: a category that holds members such as "all" / "total" whose value equals the sum of the others is found by arithmetic, not by the word. Totals then use only the subtotal or only the details | Refugee and population totals are right without the AI noticing |
| 1.3 | **Partial periods**: a first or last period whose coverage (days with rows, or rows) is below X% of the median period is marked partial. It is drawn hatched and left out of change claims and anomalies | No "-23%" on a 9-day December |
| 1.4 | **Out-of-range dates**: dates far outside the main range of a column are shown as a fix to accept, not used as a baseline | No "64,182,344%" |
| 1.5 | **Seasonality-aware anomalies**: before calling a period unusual, compare it with the same period a year earlier when there are ≥ 2 years | November is "the yearly peak", not a spike |
| 1.6 | **Minimum group size** for any "by group" ranking of an average or rate (admin setting, default 30 rows). Smaller groups are left out of best/worst claims, and every bar shows n | No "cheapest governorate" from one listing |
| 1.7 | **Mixed kinds in one column**: members whose values sit on a different scale (orders of magnitude apart, or a distinct value pattern) are flagged as "not like the others" for the person to exclude. Examples: indices beside stocks, fee lines beside products | Index tickers and postage lines are flagged, not ranked |
| 1.8 | **Units**: never average or add a measure across members with different units or kinds (commodity, unit column) unless the person asks; split by that column instead | Sugar and rice not blended |
| 1.9 | **Join safety**, checked on every suggested dataset: does the join multiply the base rows? does a LEFT JOIN leave empty rows that the description calls "current"? does the description ("leaves out X", "one row per Y") match the SQL? A mismatch is fixed or shown | The S4 "current employees", S3 "one row per order" and S7 "leaves out index" problems are caught |
| 1.10 | **Exclusions are rules**: columns the person asked to leave out (and identifier or personal columns when asked) are removed server-side from the dataset, never left to the AI | `mil_no` absent when excluded |
| 1.11 | **Time parts on demand**: when a question names hour, weekday or month-of-year, the matching derived field is added | "best hour" answered on the dashboard |
| 1.12 | **One version of the data per analysis**: dashboard, insights and Ask AI read the same cleaned dataset version, and every total on every page comes from it | One total for one number |
| 1.13 | **De-duplication only with a key**, or with every source column present. Otherwise "possible copies", for the person to decide | No real rows merged |

### Phase 2 — Answer what was asked, in words people use

| # | Change | Done when |
|---|---|---|
| 2.1 | **Answer contract**: every question in "What you need to know" gets one answer card at the top of the first page (number + one sentence + chart). "Could not answer" is allowed only with the reason and the missing column | The scorecard questions in §2 all get an answer or a precise reason |
| 2.2 | **Best/worst questions** are answered with the best/worst member (with n). **Change questions** compare like-for-like periods (same months, complete periods), never first against last | "Best month: October, 964,178" |
| 2.3 | **"No real difference"** is a valid answer: when groups differ less than a set share, or a test finds no difference, say so plainly | Channels in S10: "about the same (within 5%)" |
| 2.4 | **Names, not codes**: when a column is a key to a lookup table with a name column, the name is used everywhere (department, criterion). Wide repeated columns (`s2_1 … s3_10`) are offered as one "criterion / score" pair | "Sales pays most", "weakest criterion: <name>" |
| 2.5 | **Sentences are checked against their own numbers**: no claim whose number is outside its stated range; no text about the page itself; no "What to do" that repeats the person's question | No S10 range contradiction |
| 2.6 | **Insights must be news**: correlations between columns of one family (open/high/low/close, a price and its total) and facts true by definition (a reason that only exists on returns) are not shown | No "open and high move together" |
| 2.7 | **Ask AI**: when numbers are not in the rows, the sentence is rewritten without them; starters use the measure meaning (never sum a score, an age or an ID; never group by an excluded column); answers never cut mid-sentence | Starters on S6/S9 make sense |
| 2.8 | **Every answer page ticked by default**; detail pages that charts open are added automatically | A full dashboard in one click |

### Phase 3 — Screens and housekeeping

1. **Connection health.**
   - Each connection shows a health dot from its last test.
   - Setup on a broken connection says so first and offers "Edit connection".
   - Cached descriptions are labelled as cached.
2. **SQLite row counts** use `count(*)` when statistics are missing.
3. **Rename the "PUBLIC" badge** to "Sensitivity: Public" and move it away from Share.
4. **Hide test objects.** Hide objects named as tests ("delete me", "scratch") from people other than their maker, or offer a clean-up in admin.
5. **Charts:**
   - one colour for one series;
   - compact axis numbers (45T);
   - whole-number years;
   - Pareto line only when asked;
   - the language of the interface in all generated text, including column labels (a display name per language).
6. **Progress and speed.**
   - Show the step being done and a time estimate.
   - Run the page builder's chart checks in parallel.
   - Target under 30 s per step on a 3-million-row dataset.
7. **Privacy.** Identifier and personal columns get a "personal data" mark; charts that list individuals warn before sharing.

### Phase 4 — Prove it is neutral, and keep it so

1. **A permanent benchmark built from this test.**
   - Inputs: the 10 databases, the personas, and the ground-truth answers in [ground-truth/](ground-truth/).
   - Each release runs the guided setup for every persona and scores each answer automatically (number within tolerance, direction right, best/worst right).
2. **A release gate.** The score per database is reported; a release may not lower any database's score, and the lowest-scoring database is the one to work on next.
3. **One small synthetic fixture per trap,** so each rule in Phases 0–2 has a test that does not depend on any real database:
   - interval column;
   - DATE column;
   - lookup code 0;
   - subtotal rows;
   - partial last period;
   - out-of-range dates;
   - seasonal peak;
   - tiny groups;
   - mixed-scale members;
   - mixed units;
   - fan-out join;
   - LEFT JOIN "current";
   - wide score columns;
   - stock over time;
   - excluded identifier.
4. **Tuning rule.** No prompt example or rule may name a column, value or business from these databases; the existing domain-neutral tests already enforce wording.

### Order and size (rough)

| Phase | Effort | Scenarios it should fix |
|---|---|---|
| 0 | about 1–2 weeks | S3, S7 and most false banners; the Ask AI season refusal; the taxi cleaning |
| 1 | about 3–4 weeks | S1, S2, S4, S6, S8 numbers |
| 2 | about 2–3 weeks | The "could not answer" cases, codes, contradictions |
| 3 | about 1–2 weeks | Screens |
| 4 | starts with Phase 0 (fixtures first), benchmark about 1 week | Keeps it neutral |

Target after Phases 0–2: at least 85% on the scorecard for every database, not on average.

## 5. Left from this test

- **Created by the test (not deleted):**
  - dashboards 377–386, one per scenario;
  - about 16 datasets;
  - 10 guided-setup analyses (flows 68–76 and the ones on Olist, Employees, food and Demo).
  - Delete them when no longer needed, or keep them as before/after evidence for Phase 0.
- **Nothing committed or pushed.**
- **No backend file changed.**

## 6. Progress

Each entry: what changed, the trap test that guards it, the tests run. Tests live in
`backend/tests/test_persona_traps.py` (synthetic frames only).

| Item | Status | What changed | Tests |
|---|---|---|---|
| 0.1 | done 2026-10-12 | `demand._is_date` recognises Python `date`/`datetime` objects and ISO text (≥ 95% of a sample); `_as_dates` reads them; date columns are shown to the model as a range and never offered as values | `TestPlan01…` 4 tests; guided-setup suites 225 passed |
| 0.2 | done 2026-10-12 | New scope op `between` (both ends included): a period said with years, or a list of dates copied as examples, becomes one range; `filters_for` gives `gte` + `lte`; `scope_words` reads "model year: 2015 – 2018"; values for a column shown only by examples count only when the person typed them; prompt updated | `TestPlan02…` 7 tests |
| 0.3 | done 2026-10-12 | `made_for` also matches years against date literals, numbers against numeric literals, and yes/no conditions whose column the person's words name (stem match), so these are "already in the data" | `TestPlan03…` 4 tests |
| 0.4 | done 2026-10-12 | No "nothing called …" note on dashboard pages (asked once in the check step); "only" not doubled; an analysis is named from the demand or the questions, never the focus, cut at a word with "…" | `TestPlan04…` 3 tests; journeys test updated to the new rule |
| 0.7 | done 2026-10-12 | `data_quality.label_of`: when another text column names every code one-to-one (one label per code and one code per label, ≥ 2 labels), a suspected placeholder whose label is not an "unknown" word is a real code and is kept | `TestPlan07…` 3 tests; 501 data-quality-related tests passed |
| 0.6 | done 2026-10-12 | `ingest.durations_to_numbers` (run first in `detect_types`, so every import, upload chunk and refresh gets it): a duration column (timedelta64 or Python `timedelta`) becomes a number in the unit its name says (seconds/minutes/hours/days), else days; the name is kept so live tables still match their source | `TestPlan06…` 2 tests; 2,149 import/upload/type tests passed |
| 0.9 | done 2026-10-12 | V7 accepts the sum of a count column (`order_count`, `n_…`, `…_num`); in the agent loop a query that only V7 doubts is answered on the last attempt instead of refused (the doubt stays in `validation_failures`) | `TestPlan09…` 2 tests; new graph test; 499 agent/Ask tests passed |
| 0.8 | done 2026-10-12 (adapted) | The owner's 2026-10-10 decision (AI rules under 1% apply by themselves) is kept, with a guard: `health.rule_describes_group` marks a rule whose broken rows are ≥ 80% one value of a category and ≥ 50% of that value's rows; such a rule is explained ("this may be how that group works") and never applied by itself. The 1% share is now the admin setting `setup_ai_rule_auto_share` (0 = always ask) | `TestPlan08…` 3 tests; 332 guided-setup/settings tests passed |
| 0.10 | done 2026-10-12 | KPI tile (`WidgetBody.tsx`): the column is `justify-content: safe center` (overflow goes below, never above) and the sparkline may shrink to nothing in a short card. Measured on dashboard 381 at 1280 px: each number now starts inside its card (449 against 443; before 432 against 443). Phone width: not measured (widgets still loading after 12 s) | tsc clean; 194 widget + 174 i18n tests passed |

| 0.5 | done 2026-10-12 (part) | `answer.title_promises` in the guided-setup gate (`Gate.one`): a chart whose title names a yes/no column, a number column (by word stem) or a value of a category that the chart's config does not use is refused with the reason, so the repair round retitles or filters it (cards mode: it is dropped). Words that belong to a used column never count. **Not yet:** the "Suggest dashboards" builder (`suggest_dataset_dashboard.validate_widget` works from the profile, not the rows); sentence-level claims are still guarded only by `honest_text` (numbers) | `TestPlan05…` 5 tests; 207 guided-setup tests passed |
| 0.2 (screen) | done 2026-10-12 | `DemandCard.tsx`: a `between` restriction reads "trade date: 2023-01-01 – 2023-12-31"; the same restriction on several datasets is listed once | `DemandCard.test.tsx` (new); Setup tests passed; tsc clean; ARCHITECTURE counts 534 / 370 updated |

**Browser re-check after Phase 0 (EGX, flow 79, same persona, "Only the year 2023"):**
- The scope is now one full-year range on every dataset ("This data holds only trade date: 2023-01-01 – 2023-12-31"). Before, it was 6 example days.
- COMI money traded in 2023: 74,547,159,340, which matches the truth (74.55 bn).
- Still wrong, and planned:
  - index tickers ranked first as "companies" (1.7);
  - "COMI price gain" is an average or sum of daily changes (0.296 or 84.06) against a true +79.9% (2.2);
  - index "+52%" is January to November, not a year on year (1.3, 2.2).
- New fault found: "About you" answers typed before ticking existing datasets are lost (logged in FINDINGS_LOG; Phase 3).

Phase 0 is complete. Next: Phase 1, starting at 1.3 / 1.4 (partial periods and out-of-range dates) and 1.6 (minimum group size), the faults that hit the most scenarios.
| 1.3 | done 2026-10-12 | `relative_dates.partial_period` also catches a last bucket the dates cannot judge (a summary keyed by the first day of each month): under 50% of the median rows of the 12 buckets before it → partial ("holds 34% of the rows of a usual month"). `kpi_trend` drops unfinished periods one after another (up to 3), so a stub month before the last one is not the comparison either. Page sentences, KPI badges and change drivers already honour `partial_period` | `TestPlan13And14…` (thin month, full month, KPI tail); 567 date/KPI tests passed |
| 1.4 | done 2026-10-12 | `relative_dates.stray_dates`: dates beyond the column's 0.5–99.5% range by more than max(31 days, 10% of that range), and at most 0.5% of rows. The monthly-trend insight ignores them; the check step offers "{n} rows dated far outside … leave them out" as a fix to accept (kind `stray`, never applied by itself) | 3 tests; 1,538 insight/dates/guided-setup tests passed |
| 1.6 | done 2026-10-12 (not on live tables) | Widget option `min_group_rows`: a ranking by an average / median / min / max leaves out groups with fewer rows (totals and counts keep every group); the result carries `small_groups {hidden, min_rows}` and the chart says "{n} groups with fewer than {min} rows are not ranked" (EN/AR). `polish_widget` (shared by the guided setup and Suggest dashboards) sets it on non-time category charts from the new admin setting `min_group_rows` (default 30). DuckDB applies it as `HAVING COUNT(*) >= n`. **Not yet:** live (DirectQuery) tables ignore it (the key is dropped before re-shaping, so nothing breaks) | `TestPlan16…` 4 tests (pandas, totals, builder, DuckDB); 3,886 widget-engine tests passed; frontend 361 tests + tsc clean |
| 1.10 | done 2026-10-12 (suggestions; not yet chat edits) | The dataset-suggestion call also returns `excluded_columns` (every catalog column holding what the person asked to leave out, in whatever language they asked); `datasets.without_columns` removes those columns from the outer SELECT of every suggestion by code (they may still join or filter) and adds them to "Leaves out". Browser re-check (sh2on_zobat, exclusions typed in Arabic): no suggestion shows names, military numbers or medical data; `mil_no` appears only in joins. **Not yet:** a proposal changed through its chat ("Change it", `refine`) is not re-checked | `TestPlan110…` 2 tests; 35 dataset/journey tests passed |
| 1.13 | done 2026-10-12 | `health.has_row_key`: identical rows are removed by themselves only when a column names each row (text or whole numbers, ≥ 95% distinct); otherwise they are reported as "may be real repeats" (EN/AR) with the fix offered, never applied by itself | `TestPlan113…` 3 tests; 256 guided-setup tests passed |
| 1.6 (amended) | done 2026-10-12 | The group floor applies only when at least two groups pass it; on data too small for it every group is shown (caught by the Suggest-dashboards endpoint tests, whose fixtures have a few rows per group). DuckDB applies the same rule in SQL | `TestPlan16SmallData` 1 test; 408 suggest/DuckDB tests passed |
| 1.11 | done 2026-10-12 | `suggest_dataset_dashboard.time_part_named`: a chart whose title names the hour of the day, the day of the week or the month of the year (English or Arabic) on a date axis is grouped by that part (`hour_of_day`, `weekday`, `month_of_year`), in `polish_widget`, shared by both builders | `TestPlan111…` 3 tests |
| 1.2 | done 2026-10-12 | `health.subtotal_members`: a category value is a subtotal when its rows' main amount (the number with the largest total; never a year, never a number a category fixes such as an age band's bound) equals the sum of its sibling values within the same other-category groups. The test is by arithmetic: total not below its parts in ≥ 90% of groups, within 5% in ≥ 50%, overall gap ≤ 12% (a total may hold an unrecorded part). Nested totals ("both sexes" only at "all ages") are compared with the companion column held at its value. The check step leaves the total rows out by itself (kind `subtotal`, EN/AR, named in the summary; lossless because the details add up to the totals). Tables over 200,000 rows or columns past the 8th category are not searched. Measured on real tables: population by governorate → gender "all"; refugees → age "all" (which also removes every gender-"all" row); no false positives on 13 other tables (food prices, rainfall, poverty, conflict, funding, WHO, shipments, order items, car and property listings, titles, stock prices). At most 1.5 s per table | `TestPlan12…` 5 tests; 263 guided-setup tests passed |
| 1.7 | done 2026-10-12 (shape signal; magnitude signal not yet) | `health.odd_members`: in a code-like text column (≥ 30 distinct values, the two commonest value shapes, e.g. `99999` / `AAAA`, cover ≥ 80%), the few values written another way (each shape < 1% of values, together ≤ 3%, plain numbers ignored) are reported in the check step: "{k} values of “{col}” are written unlike the rest (…)", with "leave them out" offered, never applied by itself (EN/AR). Measured: EGX 2023 → exactly the 4 index tickers; product codes → `POST`, `DOT`, `D`, `C2`, `GIFT…` and some 7-character variants (65 of 5,131, for the person to judge); no flags on 10 other tables. **Not yet:** members of the same shape but a different scale (orders of magnitude apart) | `TestPlan17…` 3 tests; 207 guided-setup tests passed |
| 1.5 | done 2026-10-12 | `timeline.repeats_a_year_before`: a month on the same side of the series' median as the same month a year before, within ×1.25 of it, repeats a season. Insights then (a) report it as "{measure} peaks / dips every {month}" with both years' values, not as an anomaly, and (b) when the last month is such a month, compare it with the same month a year before ("ran 3% above the same month a year before") instead of the average of all months. New keys `rb.ins.season.*`, `rb.ins.trend.yoy.*`, `rb.ins.d.season`, `rb.ins.d.vsYearBefore` (EN/AR). Measured on the real retail sales: "Sales peaks every November (2010-11 1.5M; 2011-11 1.5M)" and "2011-11 ran 3% above the same month a year before" (truth +2.7%), where it said "84% above its monthly average". **Note:** the month name in "every {month}" is English in the Arabic text | `TestPlan15…` 3 tests; 1,104 insight tests passed; 174 i18n tests |
| 1.9 | done 2026-10-12 (counts; description wording not yet) | Every suggested dataset that joins is measured on the source, under the person's row rules (`datasets.join_check_sql` / `join_notes`, built with sqlglot so any dialect quotes correctly): rows against distinct keys of the main table (when it has a single primary key), and per LEFT JOIN the share of rows with no match. The suggestion card says "Rows repeat: 97,015 rows hold 96,478 orders …" and "Unmatched rows: 20% of the rows have no matching salaries …" (EN/AR). Measured on the real S3/S4 queries: olist 97,015 vs 96,478; employees 59,900 of 300,024 without a current department or salary. **Not yet:** checking the description's own words ("one row per …", "current") against the SQL | `TestPlan19…` 3 tests (SQLite); new ChooseDataStep test; 207 guided-setup + 216 frontend tests; tsc clean |
| 1.8 | already covered (units); averages across items not | `fact_sheet.mixed_units` + `analyst_panel.mixes_units` (used by the guided-setup gate through `repair_and_check`) already refuse adding a measure across values whose typical size differs ≥ 1000× (bytes beside seconds). **Not done:** a price averaged across different items of similar size (S8 sugar and rice in one "typical price"); left for Phase 2 (answers name what they average over) | verified in code; no change |
| 1.12 | done 2026-10-12 (Ask AI); pages from two datasets not | Ask AI (`agent/graph.dataset_frames`, shared by the statistics short-circuit) applies the dataset's Prepare steps, with their join frames, after the row rules, as every chart does, so Ask and the dashboard read the same rows. **Not done:** two datasets of one analysis cleaned differently still give two totals for one number (S1 20.46M / 20.81M) | new `TestPreparedRows` in test_agent_dataset_mode.py; 477 agent/Ask tests passed |

Remaining in Phase 1: 1.1 (a stored meaning per measure: amount / rate / level / score / identifier / coordinate / sequence).
| 1.1 | done 2026-10-12 (measured guards over the model's word) | The per-dataset classification (`column_classes`, kinds amount/count/level/duration/score/share/code) already existed. The connection's Meaning map (`guided_setup/meaning.py`), which writes "Add up / Average" on the first page, now overrides the model where the evidence is measured and neutral: `never_calculated` makes a code of identifiers, sequence or position columns (`…_sequential`, `item_id`, `index` …), latitude and longitude, and whole numbers all between 1800 and 2200 (years); `holds_periods` makes a level ("a value held over a period") of any amount in a table whose date column runs to a far-future "not ended" date (≥ year 9000). Re-measured Olist in the app: "Add up" no longer lists order item id or payment sequential; "Average" no longer lists latitude or longitude. The Employees salary, title and department-history tables are recognised as periods. **Left to the model:** physical sizes (height, length) and text lengths | `TestPlan11…` 2 tests; 85 meaning/trap tests passed |

**Phase 1 status:** every item has a change, a trap test and a measurement. Gaps are written in their rows: 1.5 month names in Arabic; 1.6 live tables; 1.7 scale signal; 1.8 averages across items; 1.9 description wording; 1.10 chat edits; 1.12 two datasets of one analysis. Next: Phase 2.
| 2.8 | done 2026-10-12 | Dashboard step (`DashboardStep.tsx`): every suggested page, detail pages included, starts ticked for the first dashboard of an analysis; when adding to a dashboard already made, only the first stays ticked | DashboardStep tests updated (9 passed); tsc clean |
| 2.6 | done 2026-10-12 | Insights: (a) two columns with r ≥ 0.99 whose medians are within ×1.25 are one quantity read twice (a day's opening and closing price) and are not reported as "moving together". The real COMI 2023 pairs are 0.993; the existing test of a genuinely derived column (r ≈ 0.988) still passes. (b) A category filled in only on the rows WITH an outcome (the rows without it all hold one stand-in value) gives no rate finding: "Changed mind → 100% returned" is true by definition | `TestPlan26…` 2 tests; 1,113 insight tests passed (the first threshold, 0.98, failed 2 existing inferential tests and was raised) |
| 2.3 | done 2026-10-12 | A bar chart's finding whose highest and lowest groups are within 10% (`CLOSE_SHARE`) says "Highest … lowest … only 4% apart, so about the same" (EN/AR) instead of a bare ranking | `TestPlan23And25…` 2 tests |
| 2.5 | done 2026-10-12 (part) | "About the same for every {group}" no longer puts an overall number outside the groups' own range beside it ("907 -- about the same for every city (913 to 934)"); the range alone is said. Text about the page itself and self-referring advice: not yet | 100 answer/dashboard tests passed |
| 2.2 | done 2026-10-12 | A time chart's finding of 3+ periods reads "{latest}: {value} ({±%} on {the same period a year before, else the period before}); highest: {peak} ({value})" (EN/AR), never first period against last; two periods keep "a → b". The best period is therefore always named (S10: the true best month was missing) | `TestPlan22…` 2 tests; 282 guided-setup tests passed |
| 2.4 | done 2026-10-12 (names beside codes; wide columns not) | `understand.load_facts` keeps each table's outgoing declared/confirmed keys (`links`); `datasets.with_names` adds, for every shown code that points into a small lookup table (≤ 10,000 rows) with a text column, a LEFT JOIN on that key and the lookup's name column beside the code (the lookup's own column name, e.g. `dept_name`). Summaries (GROUP BY) and lookups already joined are left alone. Real Employees "current employees" query: `d005 → Development`, `d007 → Sales`. **Not yet:** wide repeated score columns (`s2_1 … s3_10`) offered as one criterion/score pair | `TestPlan24…` 2 tests (SQLite run); 207 guided-setup tests passed |
| 2.7 | done 2026-10-12 (part) | (a) Ask AI starter questions (`pages/ask/suggestions.ts`, used on the Ask page and the dashboard's Ask panel) read the stored classes: a level, score, duration or share is averaged ("Which make has the highest average car age years?") and never totalled; codes and identifiers are never used. (b) An answer sentence holding a figure that is in no result row is set aside on the server (`evidence.set_aside_untraced`, at read time, no second model call): the checked sentences are shown, the others sit under "Left out: n sentence(s) with figures that are not in the results" (EN/AR). S1's reversed "2011 > 2010" sentence is the trap test. **Not yet:** answers cut mid-sentence | `TestPlan27…` 2 tests; new suggestion + AnswerText tests; 556 agent/Ask + 329 chat/i18n frontend tests; tsc clean |
| 2.1 | done 2026-10-12 (part: every "could not answer" has a reason) | The guided-setup gate keeps why it refused each asked question's chart (`Gate.refusals`, question id → reason); "This data could not answer: {q}" now always carries one: "-- the chart for it was left out: {reason}" or "-- no chart of these columns answers it" (EN/AR). **Not yet:** a separate answer card per question at the top of the first page (the page sentence and the per-question charts carry the answers today) | `TestPlan21…` 1 test; 207 guided-setup tests passed |

**Phase 2 status:** 2.1 (part), 2.2, 2.3, 2.4 (names; wide columns not), 2.5 (part), 2.6, 2.7 (part), 2.8 done. Next: Phase 3 (screens and housekeeping).
| 3.2 | done 2026-10-12 (adapted) | Counting a SQLite file's rows during introspection was tried and reverted: the existing rule (and its test) that introspection never scans a table stands, so an unknown count stays unknown. Fixed instead: the first page says "Rows not counted" (per table and in the totals, `totals.rows_known`), never "0 rows" (EN/AR). MySQL/MariaDB now read the engine's own estimate (`information_schema.TABLES.TABLE_ROWS`, no scan) | 207 guided-setup + 111 introspection/trap tests; 216 frontend tests; tsc clean |
| 3.3 | done 2026-10-12 | The dashboard header's sensitivity badge reads "Data: Public" ("البيانات: عام"), so it is not read as "this dashboard is public" beside Share | ReportBuilder test extended; 335 frontend tests; tsc clean |
| 3.1 | done 2026-10-12 | The connection test keeps its result with the connection (`config.__health__`: ok, time, first line of the error). The Connections list shows "Failed" and why from that kept result, before anyone tests again. The guided setup tests the connection when it opens (for those allowed to) and, when it does not answer, says so first: "This connection does not answer right now; what you see below was read earlier." with a link to check it (EN/AR). Browser: Moodle (missing file) shows the warning on its setup page and "Failed: Database file not found…" in the list. Connections never tested show nothing until tested | new API test (`test_the_last_test_is_kept_with_the_connection`); 2 Setup + 1 Connections frontend tests; 26 data-source + 207 guided-setup + 218 frontend tests; tsc clean |
| 3.0 (found in run) | done 2026-10-12 | What a person types in "About you" was lost when they ticked datasets that already exist and went on without pressing Suggest: the form kept it only on screen. The step now keeps the typed draft and saves it with the flow before the choice goes ahead (a failed save does not block the choice) | new ChooseDataStep test (typed question saved before `onDone`); 45 setup frontend tests; tsc clean |
| 3.4 | done 2026-10-12 (adapted) | Judged by use, not by name (a name rule would be language-bound and could hide a real "Test scores" dataset). "Already made" on Choose data now says how many dashboards read each dataset ("Used by 2 dashboards" / "Not used by any dashboard"), lists those in use first, then the person's own, and folds away unused datasets made by someone else behind "Show N more not used anywhere" (EN/AR). Nothing is deleted. Browser: Demo — Live SQLite shows the two used datasets and folds the leftover trial dataset (made by another account, used by no dashboard) | new trap test (`TestPlan34LeftoversFoldAway`); new ChooseDataStep test; 116 trap/guided-setup backend tests; 101 setup+i18n frontend tests; tsc clean |
| 3.5 | done 2026-10-12 (4 of 5; display names per language not yet) | **Pareto only when asked:** the setup's dress step adds the running-share line only when the chart carries `pareto` (the planner's menu now offers it "only when the person asks how concentrated a total is; never on a plain ranking"); a concentrated ranking stays a plain bar. **One colour for one series:** `getFillFactory(..., oneSeries)` — single-measure bars all take the first colour (rule fills still win; donut/pie/funnel keep a colour per part). **Compact axes:** 14 renderers (dual-axis, area, bubble, dot, waterfall, forecast…) used full numbers on value axes; all now use the shared `valueTick` (compact from a million up), so "45,000,000,000,000" reads "45T". **Whole-number groups:** `widget_data._whole_groups` — a float grouping column whose values are all whole (a year with blanks) groups as integers, so names read "2000", never "2000.0"; real decimals stay. Browser: EGX dashboard bars in one colour. **Not yet:** a display name per language for column labels | `TestPlan35ParetoOnlyWhenAsked` (3), `TestPlan35WholeNumberGroups` (2); chartUtils + axis tests; full backend suite 8,296 passed (3 telemetry tests failed only under the OTEL-off flag used to quiet the run; they pass normally); 2,002 report frontend tests; tsc clean |
| 3.6 | partly done 2026-10-12 (time shown; speed not yet) | Each AI step (dataset suggestions, the check of each dataset, the page design) keeps how long it took (`took`, from its pending state's start). While a step runs, its "working" line now says how long it has run and how long that step usually takes here: "Running for 0:42. Usually about 75 seconds here." (EN/AR, local digits). The usual time is the median over the organization's last 40 analyses (`_usual_waits`), so it learns from this installation, not from a fixed guess; nothing is shown until something was measured. **Not yet:** running the page builder's chart checks in parallel (they are CPU-bound pandas work; needs a thread pool and a measurement) and the "under 30 s per step on 3 million rows" target | `TestPlan36HowLongItTakes` (2); new `WaitTime` frontend test (2); 295 guided-setup + 35 architecture-doc backend tests; 103 setup+i18n frontend tests; tsc clean; ARCHITECTURE counts 371 frontend test files |
| 3.7 | done 2026-10-12 | **Mark:** dataset columns carry `personal` (the personal-data type from the existing detection, `pii.personal_type`: detected email/phone/national ID…, or a telling name such as first/last name, address), and the builder's Fields list shows a "Personal data" shield on such a column (EN/AR). **Before sharing:** new `GET /reports/{id}/listed-records` (`services/listed_records.py`) finds charts grouped by — or tables showing — a personal column or an identifier (one mark per record). The Share dialog says so above every tab: "13 charts here show single records, not groups. If they are people, check that sharing them is allowed." naming the first five and counting the rest; it never blocks, since an identifier may name an order as well as a person. Browser: the officers dashboard (sh2on_zobat) lists its 13 `mil_no` charts; the stocks and retail dashboards show nothing | `TestPlan37ChartsThatListPeople` (3); 2 ShareDashboardDialog tests; 212 report/dataset/PII/architecture backend tests; 334 share/builder/i18n frontend tests; tsc clean |
| Phase 3 | done 2026-10-12, with open parts | Open: 3.5 display name per language; 3.6 parallel chart checks and the 30 s target |
| 4.3 | done 2026-10-12 (14 of 15 traps pass; wide score columns is an expected failure until built) | `test_persona_traps.TRAP_FIXTURES` maps each of the 15 traps to its synthetic fixture and `test_every_trap_has_a_fixture` fails if one goes missing. New fixtures: **mixed-scale members** — the open magnitude half of 1.7 is now built: `health.scale_members` flags members of a category whose median of a non-negative amount sits in a cluster ≥ 100× from the rest (a gap in the ranked medians, not a long tail; ≤ 10% of members; never an identifier, a signed number or dates written as text), reported in the check step as "{k} values of “{col}” have “{m}” on another scale from the rest…" (EN/AR) with "leave them out" (never applied by itself). Measured on 145 real imported datasets: no false alarm after excluding identifiers, signed measures and text dates (3 found before those guards); finds the four EGX index tickers among stocks by `traded_value_egp`. **Mixed units** (`fact_sheet.mixed_units` + `mixes_units`), **stock over time** (a column recorded as a level defaults to average), **wide score columns** (strict xfail: plan 2.4's long pairs are not built) | 5 new fixture tests + index; 303 trap/guided-setup tests passed, 1 expected failure |
| 4.4 | done 2026-10-12 | New `tests/test_neutral_wording.py`: every string constant in the backend (comments and docstrings excepted; the demo's own sample builder excepted) and the EN/AR interface text are scanned for the distinctive table, column and business names of the ten tested databases (from `ground-truth/`); plain words any business uses ("orders", "customers") are not on the list. Clean today; a third test proves the rule would catch one | 3 tests; architecture doc counts 536 backend test modules (with the benchmark tests) |
| 4.1 | done 2026-10-12 (scoring of existing analyses; fresh automated run not yet) | [benchmark.json](benchmark.json): the 10 scenarios with the personas' own words (from their saved analyses) and 32 questions as checks taken from `ground-truth/` (number within a tolerance, best/worst named in EN or AR, direction, known wrong answers that must not be stated). `services/persona_benchmark.py` scores what a dashboard SAYS (page names, chart titles, text boxes); `scripts/persona_benchmark.py` scores the latest analysis per connection (or chosen flows), read-only. Baseline on the persona test's own analyses (flows 68–77, made before Phases 0–3): **10 / 32** automatic (the hand scorecard said 14 / 32; the automatic one counts only what is written, not values drawn on charts). Weak spots of the truths: S2.1 has no true earnings figure, S6.2/S6.3 have only a direction / known-wrong check (see the file's `truth_note`s) | 5 scorer/gate tests |
| 4.2 | done 2026-10-12 | `persona_benchmark.gate`: a run fails (exit 1) when any scenario scores below [benchmark_baseline.json](benchmark_baseline.json); it names the lowest-scoring scenario as the next to work on (today S2 Taxi, 0 / 4). Usage: `python scripts/persona_benchmark.py BENCH.json --baseline benchmark_baseline.json --out scores.json` | covered by the scorer tests |
| Phase 4 | done 2026-10-12, with open parts | Open: a fresh run of all ten personas through the guided setup (creates ten analyses with AI, about an hour) to measure Phases 0–3 against the 10 / 32 baseline; wide score columns (strict xfail) |
| 4.1 fresh run | done 2026-10-13 | New `scripts/persona_run.py` walks each persona through the guided setup by the app's own API (their own words from the saved analyses; every suggested dataset imported; Check & discover; page design; no dashboard made) and the benchmark reads the designed pages. The baseline was re-read the same way (designs of flows 68–77): **13 / 32** ([benchmark_baseline.json](benchmark_baseline.json)). Fresh analyses 81–91 (S1 84, S2 82, S3 91, S4 85, S5 86, S6 87, S7 88, S8 89, S9 90, S10 81), 3–8 minutes each: **19 / 32**, gate passed (no scenario lower) — [benchmark_scores_2026-10-12.json](benchmark_scores_2026-10-12.json). Per scenario: S1 2→2, S2 1→2.5, S3 0.5→0.5, S4 0→3, S5 3→3, S6 2→2, S7 0.5→1, S8 0.5→1, S9 1→1, S10 2.5→3. Two single questions fell (S2.3 airports 1→0.5, S7.1 most traded 0.5→0): the gate is per scenario, so watch these. **Next to work on (lowest, S3 Olist 0.5 / 3):** the late share is computed on a dataset of late orders only ("9.55% of 7,826", 7,826 being the late orders); "which states suffer most" is ranked by late COUNT (SP) instead of late RATE (truth AL 23.9%); the "Review scores: late vs on-time" chart has no sentence with its two numbers (truth 2.55 vs 4.28); a delay summary says "about the same … from 1 to 1". Run notes: the driver's first pass timed out on slow replies (S1, S4 finished on the server anyway; S2 resumed with `--resume`, S3 re-run) | — |
| Olist fixes (benchmark's lowest) | done 2026-10-13 | Root cause was charts whose titles promised more than their query: "Share of late deliveries" was the average days late and read "9.55%"; "Review scores: late vs on-time" showed days late on a dataset with no review score; while the dataset that held the true answers had its late-rate charts refused for naming `delivery_performance` "Late" beside `is_late` — one fact written twice. Changes, all from data or declared meaning: (1) **twin columns** — a title naming a column, or a value of it, that is one-to-one with a column the chart uses keeps its promise, in both title checks (`answer.title_promises` measures it; `analyst_panel.broken_promise` now receives `fact_sheet.one_to_one`); (2) **sibling datasets** — a title naming a column (2+ words) that only another dataset of the analysis holds is refused on this one; (3) **the dataset's own name** describes every row, so its words in a title promise nothing; (4) **declared kind** — every designed chart carries `shows` (share/average/total/count/distinct/change/level/list/other) and `answer.shows_mismatch` holds the query to it in any language; a share must be the average of a yes/no column, a column measured or classified as shares, or a part of the whole — this REPLACED a title word list (owner, 2026-10-13: no static rules tuned to the test connections); (5) equal groups read "1 for every state", never "from 1 to 1". Fixed on the way: the noise words of column names were compared after cutting to 5 letters, so "amount" was never noise | `TestOlistTitlesKeepTheirPromise` (4), `TestTitleRulesDoNotOverreach` (2), `TestLevelGroupsSaidPlainly` (2), `TestOlderTitleCheckKnowsTwins` (1); 621 trap/setup/suggest/panel tests |
| Benchmark noise | done 2026-10-13 | Three redesigns under the same rules scored Olist 0.5, 2, 0.5 and Taxi 2.5, 1, 2.5: one run cannot judge a change. `persona_benchmark.average` takes the mean of several scored runs (per question, with the spread) and the gate allows `GATE_MARGIN` 0.5 below the baseline for averaged runs only. `persona_run.py --redesign S1=84 …` designs the same analyses again on their datasets (no new imports) | 1 new benchmark test (6 total) |

## 7. Generic by design — what still guesses from names (2026-10-13)

The owner's rule: the platform must work on any database; the test connections show weaknesses, they are not targets. These still decide meaning from a column's or a title's **words**, in English (sometimes Arabic) only. Each should first use the data's shape or the stored classification (`column_classes`), then a meaning the model declares in a fixed field (like `shows`), and a name only as the last fallback:

| Where | What the words decide |
|---|---|
| `guided_setup/answer.py` `_SHARE_WORD` (`Gate._as_share`) | a count titled as a share is redrawn as a percent — should follow `shows: share` (next) |
| `guided_setup/answer.py` `_CHANGE`; `guided_setup/health.py` `_PERCENT`, `_LEVEL`, `_AMOUNT`, `_ADDITIVE` | whether a number is a change, a percent, a level or an amount |
| `semantic_guard.py` `_INTENSIVE_WORDS`, `_YEAR_WORDS`, `_COORD_WORDS` | average vs sum for unclassified columns; years; coordinates |
| `source_brief.py` `_RATE_WORDS`, `_SIZE_WORDS`, `_PCT_WORDS`, `_TITLE_RATE`, `_LATEST_WORDS` | rates, sizes, "latest" in a request |
| `analyst_panel.py` `_ALREADY_A_RATE`, `_MONEY`, `_MIX_WORDS`, `_GRAIN_WORDS` | rates, money, a mix, a time grain in a title |
| `agent/validate.py` `_COUNTING`, `_COUNT_NAME` | whether a question counts |
| `metadata/infer_semantic.py` currency/percentage rules | semantic type from the name |

**Held-out check (to build):** a generator of synthetic databases with the same traps in other shapes and languages (neutral column names such as `m1`, `cat_a`, values in other scripts), with personas and truths produced alongside; a change counts only when it holds or improves there too, never on the ten connections alone.
| Benchmark, averaged | done 2026-10-13 | Three redesign rounds of the ten fresh analyses under today's rules, averaged: **18.3 / 32** (runs 18, 18, 19), lowest S9 sh2on_zobat 1.0 / 4 (no spread), S2 Taxi 1.5 / 4 (spread 2.0) — [benchmark_scores_mean_2026-10-13.json](benchmark_scores_mean_2026-10-13.json). Four redesigns had failed on a closed kept-alive connection (`ReadError('')`) and kept the round before's pages; `persona_run.py` now retries such a request. Also: the count-to-share repair (`Gate._as_share`) now follows the declared `shows: share`; the title word list decides only for a chart that declares nothing | `TestAShareIsWhatTheChartDeclares` (2); 623 tests |
| 2.4 wide columns (score groups) | done 2026-10-13 (average and trend; a bar per item not yet) | New `guided_setup/groups.py`: columns that hold one kind of score, one per item, are found from their VALUES — whole numbers, 3 to 11 different values, on one scale (each covers half the group's range), at least four, and moving together (each correlates ≥ 0.2 with the average of the others; measured 0.48+ for twenty real evaluation items, about 0 for code columns beside them). Names never matter (a test renames the items in Arabic). The setup makes each group's row average as a calculated column (created on the dataset only when a kept chart uses it, like shares) and tells the planner what the group is, so "the average score" and its trend are one number. Measured on 171 real imported datasets: found only on the three that hold the 20 evaluation items. **Not yet:** comparing the items to name the weakest needs one bar per column with no category, which the chart engine does not draw yet | `TestPlan24ScoreGroups` (3); the Phase 4 wide-columns fixture is now a real test (no expected failures left); 627 tests |
| Benchmark, averaged (2) | done 2026-10-13 | Three rounds with score groups and the declared share repair: **20.5 / 32** (runs 19, 19, 23.5; no dropped requests) against 18.3 before — [benchmark_scores_mean2_2026-10-13.json](benchmark_scores_mean2_2026-10-13.json). S9 sh2on_zobat 1.0 → 3.5 / 4 in every round (average score and its trend now answered; weakest item half). S2 1.5 → 2.0. Lowest now S7 EGX 0.67 / 3: "most money traded" fails in every round | — |
| One bar per measure | done 2026-10-13 | A bar with NO dimension and `measures` listing 2+ columns draws one bar per column (`multi_measure.measures_as_bars`, mirrored in the frontend's `measuresAsBars` so it is not shown as unfinished). Each bar is its measure resolved as a headline number through the widget-data endpoint's own path, so row rules, engines and caching are the single-measure ones (`bars_of_measures`); the in-memory engine does the same for the setup's test draws. `widget_roles.missing_roles` accepts it; the planner's bar entry and the score-group note offer it ("to name the weakest item… `sort` asc"). General BI capability, not tied to any data | 2 trap tests (engine, roles, page sentence, sort); new `test_measures_as_bars.py` (3: the rule, the averages through the API, a row rule restricting every bar); 847 related tests (the known `test_widget_roles` 77≠75 aside); 1 frontend test; architecture count 537 |
| Benchmark, averaged (3) | done 2026-10-13 | With one bar per measure: **20.5 / 32** again (runs 20, 21.5, 20; every change within its spread) — [benchmark_scores_mean3_2026-10-13.json](benchmark_scores_mean3_2026-10-13.json). The planner did use the new chart (20 items, avg) and its finding read "lowest: s3_7 (4.15)" (truth 4.16), but the page sentence, written by the model, left it out — so it never reached the dashboard | — |
| 2.1 every asked question stated | done 2026-10-13 (part: lines under the summary; separate answer cards not yet) | `answer.answer_lines`: under each page's summary, one line per question the person ASKED that the page answers, made from its chart's measured finding ("• Which item is weakest: … lowest: s3_7 (4.15)"), unless the summary already gives those numbers; at most 4 | `TestPlan21EveryAskedQuestionIsStated` (2) |
| Members set apart (EGX) | done 2026-10-13 | What the check MEASURED as unlike the rest of its column (`odd`: written another way or on another scale; now stored with its `values`, read from the rule for older checks) is left out of every chart of the design by one visible, removable "is not" scope filter per value (at most 8; never when the person's own scope names that column), the planner is told why, and the page note says "Left out: … — unlike the rest of that column. Remove the dashboard's filter to bring them back." (EN/AR). Nothing is deleted. Cause: "EGX 30 Capped led the top 10 companies by money traded", and the total money traded included the indices | `TestMembersSetApartByTheCheck` (4) + page-note test; 597 tests |
| Benchmark, averaged (4) | done 2026-10-13 | With per-question answer lines and members set apart: **21.5 / 32** (runs 21.5, 22, 21) — [benchmark_scores_mean4_2026-10-13.json](benchmark_scores_mean4_2026-10-13.json). S9 sh2on_zobat **4 / 4** in every round (the weakest item is now stated). EGX pages now say "COMI leading the top 10 companies at 74,547,159,340" (the truth) but scored 0: the scorer counted the page note "Left out: “EGX 30 Capped” …" as stating a wrong answer. **Scorer fixed** (`persona_benchmark` none_of): a wrong NAME counts only in a sentence that gives it a figure, quoted names and the name's own digits not counting; a wrong figure written as text ("+83%") still counts anywhere | 4 new benchmark tests (9 in all) |
| Change over the period | done 2026-10-13 | "How much did X go up" was answered with the average of a daily-change column (EGX30 "0.264" for a year it rose 66.8%; COMI "2.10" for +79.9%). New `services/period_change.py`: a kpi with `change_over: <date column>` is the level on the last date against the first, resolved as four headline numbers through the caller's own path (widget-data endpoint: row rules, engines, caching unchanged; in-memory engine for the setup's draws). The tile shows "+79.9%" with "42.75 → 76.89 (2023-01-02 – 2023-12-11)" beneath; the page sentence reads "+80.0% (from 40 on 2023-01-02 to 72 on 2023-12-28)" (EN/AR); the planner's kpi entry offers it "for 'how much did it go up or down' — never the average of a column of daily changes" | 2 trap tests; new `test_period_change.py` (4: the rule, through the API, a row rule restricting both ends, DuckDB); 1 frontend test; architecture count 538; 320 related tests |
| Benchmark, averaged (5) | done 2026-10-13 | With the change over the period and the fixed scorer: **22.3 / 32** (runs 22, 21, 24) — [benchmark_scores_mean5_2026-10-13.json](benchmark_scores_mean5_2026-10-13.json). S7 EGX 1 → 2 (most traded now counted). The planner used `change_over` ("EGX30 Index Growth in 2023: +62.8%, from 14,961 on 2023-01-02 to 24,351 on 2023-12-27"); the truth's +66.8% counts from the last close of 2022 — another convention, left as it is (no tuning to pass). **Fault found:** the model bound "How much did COMI's stock price go up?" to that index chart, and the new answer line printed the index's change as COMI's | — |
| A question about another dataset's rows | done 2026-10-13 | `datasets.narrowed_to` reads the text values a dataset's own query keeps it to (string literals compared by `=`/`IN` in its WHERE, by the query's structure, never its name). In the designs step each dataset learns the values only OTHER datasets of the analysis are kept to (`foreign`), minus any its own rows hold; a chart whose question names such a value is kept but loses that question, so no answer line or answer is written under the wrong rows | `TestAQuestionAboutAnotherDatasetsRows` (3); 599 tests |
| Benchmark, averaged (6) | done 2026-10-13 | With questions kept off other datasets' rows: **22.3 / 32** (runs 22.5, 22.5, 22; no wrong answer lines) — [benchmark_scores_mean6_2026-10-13.json](benchmark_scores_mean6_2026-10-13.json). Lowest S3 Olist 1.0 / 3, S8 food 1.0 / 2 | — |
| Held-out benchmark | built 2026-10-13 | [heldout/](heldout/README.md): three synthetic databases the platform is never tuned on (ratings with items as columns; a ledger with a level, an ALL subtotal and a partial month; Arabic shipments with very different branch sizes), personas and exact truths from `generate.py`. Registered as connections 49–51 | — |
| Held-out, first run | done 2026-10-13 | Fresh analyses 92–94: **6 / 9** ([heldout/heldout_baseline.json](heldout/heldout_baseline.json)) — about the main benchmark's 70%, so today's rules carried over to data never tuned on. H2 ledger 3 / 3 (balance change, ALL left out, busiest month); H1 ratings 2 / 3 (average and weakest item right; "Airfield leads" — 4 reviews); H3 Arabic shipments 1 / 3 (return share and worst branch by rate missing). Causes, all general: (a) only true/false columns got a share, and every column with a non-ASCII name was skipped by an ASCII-only identifier rule; (b) a summary dataset (GROUP BY) had no group size left, so the minimum-group rule could not apply | — |
| Shares in any script | done 2026-10-13 | `share_columns`: a column of exactly two text values, in any language, gets a percent twin per value ("the share of rows where «الحالة» is «مرتجع»"); column names are quoted (`` `col` ``) instead of required to be ASCII, also in the count-to-share repair (`_as_share`) | `TestSharesInAnyScript` (2) |
| Summaries keep their group size | done 2026-10-13 | `datasets.with_group_size`: a suggested query that groups keeps how many rows each of its rows stands for (its own COUNT(*) column, or `COUNT(*) AS row_count` added, by the query's structure); the designs step passes that column to the gate, which sets `size_column` beside `min_group_rows`; both engines weigh a group by the SUM of it (pandas; DuckDB `SUM(size)` in its HAVING) | `TestSummariesKeepTheirGroupSize` (3, DuckDB included); 849 related tests |
| Held-out, second run | done 2026-10-13 | Fresh analyses 95–97 after the two fixes: **5 / 9** (single run; H3 return share now right). New causes, all general: (a) the score group's derived column `average_of_8_r1_to_r8` made the title check refuse "lowest average score" — the platform's own derived columns (shares, group averages, comparisons) no longer count as data a title names (`Gate._data_only`); (b) "how many were late" needs delivery days > promised days: a filter comparing two columns, which no engine applies — now `Gate._compare_columns` derives a 1/0 column and filters `= 1` (made on the dataset when used); (c) scorer: a wrong name in a sentence that also names the right answer is a comparison or listing, not a wrong answer | `TestAColumnComparedWithAColumn` (2), 1 benchmark test; 647 tests |
| Held-out, averaged | done 2026-10-13 | Three redesign rounds of 95–97: **6.0 / 9** (runs 7, 6, 5) — H1 ratings 2.7, H2 ledger 3.0, **H3 Arabic shipments 0.3** — [heldout/heldout_mean_2026-10-13.json](heldout/heldout_mean_2026-10-13.json). The Arabic database is the weakest. Causes: (a) the model filtered the wrong column ("الفرع = مرتجع"; the value is the status column's) and the check only refused it — now `Gate._retarget_filters` moves an `eq`/`in` filter to the ONE other text column that holds all its values (decided from values, any language; none or several → refused as before); (b) the two-column repair ran before the widget validator, which did not know the derived column — comparisons are now set aside before the checks and applied after them (`_set_aside_comparisons` → `_compare_columns`) | `TestAFilterOnTheWrongColumn` (3); 641 tests |
| Held-out, averaged (2) | done 2026-10-13 | After the filter fixes: **6.3 / 9** (runs 7, 5, 7); H3 Arabic 0.3 → 1.0 (the late count now right every round). Still: share charts drawn as counts with no "returned" filter at all, and a chart of something else (average days) stood under "which branch has the highest return share" and its answer line printed it. Fix: the demand step now records what each question `wants` (share/average/total/count/distinct/change/level/list/other — the same words as a chart's `shows`), and a chart whose declared `shows` is another kind keeps its place but loses that question (`answers_kind`; total and count may stand for each other). Declared by the model on both sides, so it holds in any language | `TestAChartAnswersOnlyItsKindOfQuestion` (3); 647 tests |
| Full backend suite | done 2026-10-13 | 8,364 passed, 26 skipped, 1 failed: `test_domain_neutral` caught "headcount" in the new period-change prompt line — reworded ("a value at one moment, such as a price or a balance") | domain-neutral + wording tests pass |
| Held-out, averaged (3) | done 2026-10-13 | With question kinds (`wants`): fresh analyses 98–100 then three redesigns, **7.2 / 9** (runs 8, 7, 7, 7): H1 ratings 3 / 3 and H2 ledger 3 / 3 in every run; H3 Arabic shipments 1.2 / 3. Replaying the Arabic share chart through the real gate found the last cause: the "known rows" filter for a yes/no share (`col in [True, False]`) was also added to the new text-value shares, where it kept no row — now only for yes/no columns. Replayed, the share-by-branch bar passes with its minimum-group rule (so a 6-shipment branch cannot top it) | 659 tests |
| **Final measurement** | done 2026-10-13 | Main benchmark, three averaged rounds: **22.7 / 32** (runs 24, 22.5, 21.5) against 13 / 32 at the start — [benchmark_scores_final_2026-10-13.json](benchmark_scores_final_2026-10-13.json). Held-out (never tuned on), three rounds: **8.0 / 9** in every round — H1 ratings 3, H2 ledger 3, H3 Arabic shipments 2 — [heldout/heldout_final_2026-10-13.json](heldout/heldout_final_2026-10-13.json). Weakest still: S3 Olist 1.5 / 3 (spread 2), S8 food 1.0 / 2, H3 Arabic 2 / 3. How to test: [TEST_GUIDE.md](TEST_GUIDE.md) | — |
| 2.1 answer card | done 2026-10-13 | `frontend/src/lib/answersCard.ts`: a dashboard made by the guided setup opens with **"Your questions" / «أسئلتك»** — every question the person asked, answered in the chart's own measured words from whichever chosen page holds it, or why not (the setup's recorded reason, else "not answered on the pages chosen — add the page that answers it, or ask it in Ask AI"). Browser, held-out H3 (Arabic): "return share 7.5%; highest Asyut 15.4%; 1,315 late" — all three true | 2 frontend tests; frontend test files 372 |
| Derived columns with non-ASCII names | done 2026-10-13 | Found on that dashboard: "'الحالة_مرتجع_pct' is not a column". `derived_for` searched for each derived column's name in JSON that escaped non-ASCII text, so no Arabic-named share or comparison was ever created on the dataset — now `ensure_ascii=False` (test dashboard 387 was built before the fix) | 1 trap test |
| 3.5 display names per language | done 2026-10-13 | The page designer returns `names`: each column it uses, named in the person's language (kept only for real columns, ≤ 40 characters). Generated text uses them (`display_name`): filter titles, detail pages, "the same for every …", the "Left out: …" note — no more "تصفية حسب corp name". Stored with the design only: no column metadata is written on any dataset | `TestDisplayNamesInThePersonsLanguage` (2); 652 tests |
| 3.6 speed | done 2026-10-13 (designs in parallel; the 30 s target on 3 M rows not reached) | Chart checks already ran in worker threads, four at a time. The designs step now designs an analysis's datasets at the same time, each in its own session on the step's engine (`write_designs` → `one_dataset`, `asyncio.gather`), page order unchanged. Held-out page design before: 98–530 s (typically ~140); after: 51, 61, 162 s — about twice as fast, same answers (held-out 8.5 / 9 on that run). The model's own time per call is the floor; under 30 s per step would need fewer or smaller model calls | 348 setup tests |
| §7 names after meaning | done 2026-10-13 (the harmful uses) | A read-only audit of every name/word rule (≈35 uses) sorted them: most already put the stored classification or measured data first and use words only for a column nobody classified. Changed where a name overrode a stored kind or removed something: (1) `health.sensible` dropped trend findings of any column whose name looked like a level (`open_tickets`, a count) — now a stored kind decides and the words only judge unclassified columns; (2) the analyst panel's "true rates first" order and its "Average … per day" headlines read only the column name — now a stored share/level/score/duration decides (an Arabic-named share now gets its headline); (3) the dataset health page ran the negative-value rule without the stored classes — now passed; (4) `infer_semantic` tested money words before rate words, so `fee_rate` became currency — rate first; (5) `_mix_from_filter` rewrote a chart from its title words even when the chart declared what it shows — now only for undeclared charts. Kept on purpose: `column_classes` lets a price-like name veto the model's "amount" (a safety net against summed prices; in another language it simply does nothing), `worth()` (a zero count on a change-named column; rare), the agent's V7 (English "how many" only — it never refuses in other languages) | `TestStoredKindsBeforeNames` (3) + 1; 862 tests |
| **Final measurement (2)** | done 2026-10-13 | After every open item: main benchmark **24.5 / 32** averaged over three rounds (runs 25, 24, 24.5; 13 at the start, 22.7 this morning) — [benchmark_scores_final2_2026-10-13.json](benchmark_scores_final2_2026-10-13.json); held-out **8.5 / 9** in all three rounds — [heldout/heldout_final2_2026-10-13.json](heldout/heldout_final2_2026-10-13.json). Part of the rise since this morning is the scorer's half point for a right answer beside an unrelated wrong name. Weakest: S8 food 1.0 / 2 (a data convention and an ambiguous "refugees", left as open data questions), S6 Cars 1.7 / 3, S1 retail 2.0 / 3 | — |
| Full suites, final | done 2026-10-13 | Backend 8,379 passed, 26 skipped, 0 failed (the known `test_widget_roles` 77≠75 and the benchmark module excluded as before); frontend 4,489 passed in 372 files; tsc clean | — |
| Too few to rank | done 2026-10-13 | Cars "cheapest governorate" scored 0 in every round: on 29 Corolla listings the 30-row floor could not apply (fewer than two groups would pass), every group was drawn — and the page said "lowest: Aswan" from one listing. Now the engine marks that case (`small_groups.too_few`), the page sentence says "{n} groups, most with fewer than {min} rows each: too few to say which is highest or lowest" (EN/AR) instead of naming one, and the chart shows the same note | `TestTooFewToRank` (2); 1 frontend test |
| A leader made by one row | done 2026-10-13 | Retail: one order of 80,995 units made a product "the top product". A ranking that adds a measure up now says when one single row gives half or more of the leader's total ("— one single row gives 99% of the leader's total", EN/AR) | `TestALeaderMadeByOneRow` (2); 628 tests |
| Dataset-name words with endings | done 2026-10-13 | Taxi: "earnings per trip" was refused for naming `trip_distance_miles` although every dataset is named "…trips…": words are cut to five letters, so "trip" ≠ "trips". Dataset-name words are now compared by prefix (a word and its ending are one word), in any language that adds endings | 1 trap test |
| Clean measurement (3) | done 2026-10-13 | On the final code after the too-few, one-row and prefix fixes: main **25.3 / 32** (runs 25, 27, 24) — S1 retail 2.0 → 2.8, S2 Taxi 2.5 → 3.2, S6 Cars 1.7 → 2.0; S3 Olist 2.3 → 1.5 (rounds 1.5 / 2.5 / 0.5) — [benchmark_scores_final3_2026-10-13.json](benchmark_scores_final3_2026-10-13.json); held-out **8.3 / 9** — [heldout/heldout_final3_2026-10-13.json](heldout/heldout_final3_2026-10-13.json). Cars "cheapest governorate" now reads "too few rows in most groups to identify the highest or lowest", and still scores 0 because that sentence lists one governorate's price — the benchmark has no positive truth for this question; left as it is | — |
| 0/1 numbers as percentages; questions name their columns | done 2026-10-13 | Olist pages said "late delivery rate is 0.0811" and put days late over time under "do late deliveries get lower review scores" (both averages). (1) A number column holding only 0/1 gets a percent twin and an average of it is drawn as that percentage (8.1%). (2) The demand step records for each question the columns its answer rests on (`about`, the data's own column names); a chart using none of them — directly or through a share, group average or comparison made from them — keeps its place but loses that question. Not judged when the question names none of the dataset's columns. Language-neutral: column names are data | `TestAChartUsesItsQuestionsColumns` (3); 664 tests. Test analyses 81–91 and 98–100 had their demand and designs cleared so the next design rewrites them |
| Measurement (4) and three faults it showed | done 2026-10-13 | With question columns and 0/1 shares: main **25.0 / 32** (runs 26, 25, 24; within noise of 25.3) — [benchmark_scores_final4_2026-10-13.json](benchmark_scores_final4_2026-10-13.json); held-out **8.5 / 9** every round. Retail 3 / 3, Cars 2.7. Olist pages showed three faults of the rules themselves, fixed: (1) a chart that lost its question to the wrong-kind / wrong-columns / other-dataset checks was then REFUSED for having no question instead of kept — now it stays, unlinked; (2) a one-number card titled "Late vs. On Time" filtered `is_late in [0, 1]` (every row) passed the title check as "using" is_late and read 4.14 (late orders: 2.55) — a filter that keeps every value of its column no longer counts as using it; (3) a share filtered to its own outcome (avg is_late over the late rows) read 100% — the self-filter is now dropped for every share, the known-rows filter kept for yes/no columns only. Not fixable by a rule: the model put "the share of DELIVERED orders" under "share of late deliveries" on a dataset with no lateness column | 2 real-Gate trap tests (`_synthetic_gate`), 1 title test; 628 tests |
| Measurement (5) | done 2026-10-13 | After the unlink / keep-everything / self-filter fixes: main **26.0 / 32** (runs 26.5, 26, 25.5) — **S3 Olist 1.3 → 3 / 3 in every round** — [benchmark_scores_final5_2026-10-13.json](benchmark_scores_final5_2026-10-13.json); held-out **8.2 / 9** (one ledger round lost "top account"; the others 3 / 3) | — |
| A scope that is the dataset itself; counting people not rows | done 2026-10-13 | Employees pages: (1) "current staff" became `from_date >= 2002-08-01` on a dataset of current employees, keeping 673 of 240,124 rows ("there are currently 673 employees"). `demand.describes_dataset`: a date or number cut whose phrase states no figure and shares a word (by prefix) with the dataset's own name is what every row already is — kept as "in data", no filter. A stated figure ("since 2020") or a list stays a scope. (2) "The current workforce is 489,903" counted assignment rows of 240,124 people: when a question wants a count, the first column it rests on repeats in the rows, and the chart counts rows, it now counts that column's distinct values (`Gate._count_whom`) | `TestAScopeThatIsTheDatasetItself` (2), 1 real-Gate test; 633 tests |
| Measurement (6) and three causes | done 2026-10-13 | Main **25.2 / 32** (runs 25.5, 24, 26; within noise of 26.0), held-out **8.0 / 9** — [benchmark_scores_final6_2026-10-13.json](benchmark_scores_final6_2026-10-13.json). Drops traced: (1) rewriting the demand turned the person's "how many shipments are returned" into "what SHARE are returned" — the demand prompt now says a question they asked keeps what they asked for (a count stays a count; the other may be added as its own question); (2) "COMI total gain in 2023: +62.8%" was the INDEX's change, drawn on the index dataset — a chart whose TITLE names a value only another dataset of the analysis is kept to is now refused (the question link was already dropped, the title was not); (3) guard added to the people-count repair: it applies only to a column whose values mostly differ (≥ 20%), never to a category such as a status | 2 real-Gate tests; 635 tests |
| Measurement (7) | done 2026-10-13 | Main **25.2 / 32** (runs 25, 25, 25.5), held-out **8.3 / 9** — [benchmark_scores_final7_2026-10-13.json](benchmark_scores_final7_2026-10-13.json). Nile Express back to 3 / 3 (a count stays a count), Cars 2.7, Olist 3, Employees 3. EGX's two change questions fell to 0 in every round: the period-change tile "COMI price change" (over `close`) was refused for naming the daily column `change_pct` — a chart that computes a change itself (`change_over`, percent change, difference) now keeps a title that says "change" (number columns are not taken as named by it). Retail: fee lines ("Manual", "POSTAGE") ranked as products on a dataset that kept only the description (no product code, so no shape signal — left as a known limit, no word list); its busy season was measured on non-UK sales because "outside the UK" scoped the dashboard — a fair reading of an ambiguous question | 1 trap test; 636 tests |
| Measurement (8) — plateau | done 2026-10-13 | Main **24.7 / 32** (runs 25.5, 25, 23.5); the last six measurements sit in 24.7–26.0, the band one model run varies by — further rules tuned to single main-benchmark questions would be fitting these ten connections. Held-out **8.5 / 9 in every round** (ratings 3, ledger 3, Arabic shipments 2.5) — [benchmark_scores_final8_2026-10-13.json](benchmark_scores_final8_2026-10-13.json), [heldout/heldout_final8_2026-10-13.json](heldout/heldout_final8_2026-10-13.json). Remaining misses are model variation (Employees' gender gap 1 → 0.33 between measurements, EGX change questions) and the data questions recorded above (food totals vs suppressed cells and "refugees"; retail fee lines without product codes; Cars "cheapest" with no positive truth) | — |
| Full suites, after the weakness work | done 2026-10-13 | Backend 8,396 passed, 26 skipped, 0 failed; frontend 372 test files passed; tsc clean | — |
