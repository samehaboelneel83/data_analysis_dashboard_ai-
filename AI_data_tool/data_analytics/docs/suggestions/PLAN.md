# Suggested widgets — evaluation against the SAS approach, and a plan

Date: 2026-10-10 · Branch: `emad` · **Status: built the same day with the recommended decisions, except where §6 says otherwise. Not committed.**
Related: [../meaning-map/PLAN.md](../meaning-map/PLAN.md), [../guided-setup/PLAN_V2.md](../guided-setup/PLAN_V2.md)

## 1. The approach being compared

How SAS Visual Analytics creates suggestions, as described by the owner:

1. **Select a data source** — read the dataset's metadata: columns, data types, **roles**, and **measurement levels**.
2. **Analyse the available variables** — identify categories, measures, dates, **geographic fields**, and **relationships** that might be useful.

Two things make that approach work: the classification is done **once, stored with the data, and corrected by the author**; and **every** suggestion feature reads that same classification.

## 2. Evaluation of Datalytics against it

Datalytics has **five** places that suggest widgets, built at different times:

| # | Where the user meets it | Engine | Reads |
|---|---|---|---|
| A | Builder → Suggestions pane | Heuristics in the browser (`SuggestionsPane.tsx`) | column types, cardinality, correlations |
| B | Builder → Suggestions pane (server ideas) | Insights engine → widget (`/reports/{id}/suggest-widgets`, `suggest_variety.py`) | the rows, column roles, the report's name |
| C | Datasets → Suggest dashboards | Model with a goal, statistics without (`suggest_dataset_dashboard.py`, `analyst_panel.py`) | a profile of the rows, column knowledge |
| D | Connections → Suggest dashboard | Model writes SQL per chart (`suggest_dashboard.py`, `source_brief.py`) | the catalogue |
| E | Guided setup, step 4 | Question-led designer (`guided_setup/answer.py`) | the person's request, the Meaning map |

### Step 1 — reading the metadata

| SAS reads | Datalytics today | Verdict |
|---|---|---|
| Columns, data types | Yes, everywhere | **Equal** |
| Roles (category / measure / date) | Yes: detected, and the author can set a role per column (`column_meta.role`), which wins over detection | **Equal** |
| **Measurement level** (nominal / ordinal / interval / ratio) | **No.** There is no "ordered category" at all — Low / Medium / High, grades, age bands and month names are sorted alphabetically or by count. Whether a number may be added up is guessed from its **name**, by separate word lists in at least five files (`semantic_guard.py`, its copy `semanticGuard.ts` in the browser, `health.py`, `understand.py`, `meaning.py`) | **Behind** |
| Stored once, corrected by the author | Partly. Role and "do not suggest" are stored. Additive-or-not, unit and direction exist only in the new Meaning map, which only the guided setup and Ask AI read | **Behind** |

### Step 2 — analysing the variables

| SAS identifies | Datalytics today | Verdict |
|---|---|---|
| Categories, measures, dates | Yes, plus things SAS's description does not mention: identifiers never summed, personal data never charted, 0/1 flags treated as shares | **Ahead** |
| **Geographic fields** | Only latitude/longitude pairs and columns of country names. A column of cities, governorates, states or postcodes is an ordinary category: no map is ever suggested for it | **Behind** |
| **Relationships** | Engines A, B, C see **one dataset**. Relationships between tables are used only by D and E. Hierarchies (country → city) are guessed from value counts, not declared | **Behind** |
| "Counted against what" | The Meaning map (bases, outcomes) — built today, read by E and Ask AI only. A, B, C, D still rank groups by raw count | **Ahead in E, missing elsewhere** |

### What Datalytics does that the described approach does not

* **Every suggestion is drawn on the real rows before it is offered** — nothing blank is suggested — and as the person asking may see them (row rules, hidden columns).
* **Each suggestion says what it shows**, with its own numbers.
* **Suggestions can follow a stated need** (C with a goal, E): SAS suggests from the data's shape alone.
* **Meaningless charts are refused** (E): flat, single-group, mostly-unknown, a count that only follows group size.

### The real weaknesses

1. **Five engines, five sets of rules.** The same dataset gets different suggestions — and different mistakes — depending on which door the user came through. A fix made in one (today's size check, the share-versus-count rule, the "not in the data" handling) does not reach the others.
2. **No single stored classification.** Each engine re-derives what a column is. This is the opposite of the SAS model, and it is why the same bug keeps being fixed in a new place.
3. **No ordinal level, no geography beyond coordinates and countries, no declared hierarchies.**
4. **Suggestions do not learn.** A dismissed suggestion is remembered only in that browser (`localStorage`), per dashboard; nothing records which suggestions people accept or reject.
5. **The pane does not look at the page.** Engines A and B suggest from the dataset; they do not ask "what is this dashboard still missing?".

**Overall:** stronger than the described approach on *checking* a suggestion (drawn, secured, explained, question-led) and weaker on its *foundation* (one stored classification with measurement levels, geography and relationships, shared by every feature). Roughly: checking 9/10, foundation 5/10, consistency across the app 4/10.

## 3. Plan

The principle: **classify once, store it with the data, let the author correct it, and make every suggestion feature read it** — then keep what Datalytics already does better (draw, secure, explain, refuse).

### Phase 1 — one column classification, stored (the foundation)

A single record per dataset column, extending `column_meta`, written when the dataset is created or synced and editable in the dataset's Columns tab:

| Field | Values | Replaces |
|---|---|---|
| `role` | category · measure · date · identifier · free text · geography | (exists; add geography) |
| `level` | **nominal · ordinal · interval · ratio** | nothing today |
| `order` | the values in their real order, for an ordinal column | alphabetical sorting |
| `number` | amount · level · duration · score · share · count · code | the five name-based word lists |
| `unit`, `direction` | EGP, kg, days… · higher is better / worse / neither | Meaning map only |
| `geo` | country · region/state · city · postcode · latitude · longitude | coordinate and country detection only |
| `source` | measured · ai · confirmed | — |

* **Detection order:** what the rows show (distinct values, ranges, whether values parse as places or ordered labels) → the connection's Meaning map when the dataset comes from a connection → the model, for names and judgement → the author's correction, which always wins.
* **Ordinal detection, generic:** known orderings (weekdays, months, quarters, size and grade scales, "low/medium/high" in English and Arabic), numeric prefixes ("1 - New", "2 - Open"), and bands ("0–17", "18–25"); anything else stays nominal unless the author orders it.
* **One reader:** a single function returns a column's classification; `semantic_guard.py`, the browser's `semanticGuard.ts`, `health.py`, `understand.py`, `meaning.py` and `insights.effective_roles` call it. The browser receives the classification from the server instead of re-deriving it.
* **Uploads get it too** (they have no connection and so no Meaning map today).

### Phase 2 — relationships and structure

* **Declared hierarchies** per dataset (year → quarter → month; region → city → branch): detected as today, then stored and editable, instead of re-guessed on every request. (The hierarchy work of 2026-10-10 already stores hierarchies for widgets; suggestions should read those.)
* **Bases and outcomes for every dataset**, not only in the guided setup: a dataset made from a connection inherits them from the Meaning map; an upload gets its outcomes (yes/no and status columns) measured on its own rows.
* **Across datasets:** when a dashboard has more than one dataset joined by a declared relationship, suggestions may use a measure from one against a category of the other.

### Phase 3 — one suggestion engine behind every door

One service, `suggest(dataset, need?, page?)`, in three stages; the five doors become thin callers of it.

1. **Candidates from shape** — the SAS step: from the stored classification, the charts the data can support (one measure → headline number; measure × category → sorted bar; measure × date → line; two categories that move together → stacked bar; geography → map; ordinal → bars in order; outcome → share).
2. **Candidates from need** — when the person said what they want (a goal, a question, the dashboard's title), the model picks and adds, as today.
3. **One gate for all** — the checks that today live only in the guided setup: drawn on the secured rows; refused when flat, single-group, tied or mostly unknown; a share for an outcome instead of a count under a "share" title; **the size check** (a count per group gets its rate); filters that would be silently ignored refused; the same reading never offered twice.

Each suggestion carries the same explanation everywhere: what it shows (with numbers), why it was suggested, and which stage produced it.

### Phase 4 — suggestions that know the page and learn

* **"What is this page missing?"** The pane reads the dashboard: no headline number → suggest one; a category already charted by count → suggest its rate; a date column unused → suggest the trend; nothing suggested that duplicates a chart already there.
* **Remembered on the server, per person and dataset:** dismissed suggestions stay dismissed on any device; accepted and dismissed counts per kind of suggestion are kept.
* **Ranking uses it:** kinds a person (or their organisation) keeps dismissing sink; kinds they add rise. No model involved — counts only.
* **"Why not?"** For a chart type the user expected and did not get, the pane can say what the data lacks ("a map needs a place column; none of these columns is one").

### Phase 5 — geography

* Recognise place columns at the levels above (country, region/state, city, postcode) from the values, with a per-organisation gazetteer so local names (governorates, emirates, provinces, in Arabic and English) resolve.
* Suggest a map only when the place column resolves for most rows, and say how many did not.

### Order and size

| Phase | Depends on | Size |
|---|---|---|
| 1 Classification stored | — | L |
| 2 Relationships and structure | 1 | M |
| 3 One engine | 1, 2 | L |
| 4 Page-aware, learning | 3 | M |
| 5 Geography | 1 | M |

Phase 1 alone removes the duplicated word lists and gives ordinal sorting; phase 3 is where users see suggestions become consistent.

## 4. Done when (acceptance, as a user)

* The **same dataset gives the same suggestions** from the builder pane, "Suggest dashboards" and the guided setup when no need is stated — and the same refusals.
* A column of **Low / Medium / High** (or its Arabic equivalent) is charted in that order without anyone setting it; the author can change the order once and every chart follows.
* A **price, a rating and a duration are never totalled** in any suggestion, on a dataset whose column names give no hint (e.g. `col_a`, `val2`), after the author — or the model — classified them once.
* A **count per group is always offered with its rate** when the dataset holds the base or the outcome, from every door.
* A column of **cities or governorates** gets a map suggestion; a column that only looks like places does not.
* A suggestion **dismissed on one device stays dismissed** on another.
* On a dashboard that already has a chart, the pane **does not suggest that chart again** and does suggest what is missing.
* Tested on at least three databases of different shapes, plus an uploaded file, in English and Arabic.

## 5. Decisions for the owner

1. **One engine (phase 3) or keep five and share only the classification and the gate?** Plan: one engine — it is the only way a fix reaches every door. Cheaper alternative: keep the engines, share phases 1–2 and the gate.
2. **Who may correct a column's classification?** Plan: whoever may edit the dataset; corrections apply to everyone using it.
3. **Learning scope:** per person only, or per organisation as well? Plan: both, person first.
4. **Geography source:** built-in gazetteer for countries and first-level regions plus an organisation's own list, or organisation list only? Plan: built-in plus own list.

## 6. What was built (2026-10-10) — and what was not

Owner's instruction: "do it precisely, and don't miss any of insights engine". Decisions taken: classification and gate shared by every engine (the cheaper alternative of decision 1, see below); anyone who may edit the dataset may correct a column; learning per person; geography from the values, no gazetteer.

### Built

| Phase | What exists now | Where |
|---|---|---|
| 1 | One stored classification per column in `column_meta`: `number` (amount · count · level · duration · score · share · code), `unit`, `direction`, `level` (nominal · ordinal · interval · ratio), `order`, `geo_level`, `outcome`, `class_source` (measured · ai · confirmed). Written on the first scan of a dataset — uploads included — and never overwritten once a person corrected it. | `services/column_classes.py`, `schemas.ColumnMeta` |
| 1 | One reader. The name-based word lists are now only the fallback for a column nobody classified. Callers moved to the reader: insights, baselines, variety, dataset profile, both dashboard designers, the analyst panel, quality report, descriptive analysis, identifier checks. The browser reads the same stored fields. | `services/semantic_guard.py`, `lib/semanticGuard.ts` |
| 1 | Ordinal scales found from the values (weekdays, months, low/medium/high in English and Arabic, numbered labels, bands) and drawn in that order. | `column_classes.ordered_values`, `widget_data` (`sort_by: "order"`) |
| 1 | Columns tab: "This number is", "Higher is", "Order of its values", "Says what became of a row", "Place". | `ColumnMeaningPanel.tsx` |
| 2 | Declared hierarchies lead the guessed ones; outcomes measured on every dataset (yes/no and status columns), connection or upload. | `suggest_inputs.declared_hierarchies`, `column_classes` |
| 3 | One gate for every door: a suggestion that draws but says nothing (empty, one group, flat, zero, tied, mostly unknown) is refused. A level comparison is kept when a goal was stated — then it is the answer. | `services/suggest_gate.py` |
| 3 | The insights engine, every detector: **rates** (share of an outcome per group, against the overall share, minimum 30 rows) and **gradients** (a measure along an ordered scale) are new; **standouts** pass the size check (a group's share of a total against its share of rows); **trends** say when a month's total only followed its volume, skip a thin closing month and skip totals a few extreme rows make up; **outliers** of a gains-and-losses column are read through the average; **correlations** keep one r per claim; at most two "outlying rows" findings and two standouts per measure reach the list; a column's description is never used as its name; a count of `shipment_id` is "Shipment count"; a group that is only a number is named with its column; an outcome is not offered as the breakdown of a total. | `services/insights.py`, `services/readback.py` |
| 4 | The pane knows the page (no headline → one is offered first; a rate already on the page, however it is drawn, is not offered again) and remembers on the server what a person dismissed and added, per dataset; kinds they dismiss sink. | `SuggestionsPane.tsx`, `suggestionTakeaway.signature`, `SuggestionFeedback`, `/reports/{id}/suggestion-feedback` |
| 5 | Place columns recognised at country · region · city · postcode · latitude · longitude and ordered into a hierarchy. | `column_classes.geo_level`, `dataset_profile._hierarchies` |

Found and fixed on the way: every control of the Columns tab failed with "Invalid request" on a dataset that had preparation steps (the reserved keys of the map were sent back as columns) — `columnMetaApi.set`.

### Tested

* 928 backend tests in the 43 related files, 2,880 frontend tests in the related folders, type check clean.
* Live, as a user: the Insights scan, the Columns tab (change and save a classification) and the builder's Suggest pane on Nile Express.
* The scan and the classification on six more datasets of other shapes: an HR snapshot (240k rows), a scraped car listing with Arabic columns (upload), demo sales (upload), call records (upload), apartment listings, enrolments (upload). Four weaknesses seen there were fixed (thin last month, "-36% of profit", "carries 100%", a bare number as a group name).

### Not built, or only in part

1. **One literal engine** (`suggest(dataset, need?, page?)` with the five doors as thin callers). The five engines remain; they now share the classification, the gate and the size check. The same dataset can still get a different *selection* from two doors. This is the alternative named in decision 1.
2. **Connections → Suggest dashboard** (engine D, model-written SQL) reads neither the classification nor the gate.
3. **Maps for regions and cities.** A stored level and a hierarchy, no map: that needs a gazetteer with coordinates. Countries and latitude/longitude pairs get maps as before.
4. **Across datasets** (a measure from one dataset against a category of another on the same dashboard).
5. **"Why not?"** for a chart type the user expected.
6. **Learning per organisation** (per person only).
7. A number nobody classified and whose name says nothing is classified from its values alone: `bedrooms` and `area_sqm` of a listing come out as amounts, and are totalled, until the model or a person says otherwise.
8. Acceptance line "tested on three databases plus an upload, in English and Arabic": done through the API on seven datasets; the screens themselves were walked in English on one.

## 7. Neutral by construction (2026-10-10, owner: "it is general purpose platform, it is not biased to any business areas")

The classification of §6 still leaned on word lists that knew one field of work at a time: `salary`, `wage`, `mileage`, `bedrooms`, `imei`, `seller`, a "Headcount" for any person id, "Hires per year", a delivery as the only way a record finishes, five regional currency codes, and prompt examples taken from the two test databases. All of that is gone.

**The rule now.** No noun of one business area is written into the logic or into a prompt. What a column is comes, in this order, from:

1. **its values** — a yes/no, an ordered scale, a running sequence, a long fixed-width number (a code, whatever it is called), which date every row has and comes first (when the record began), which date is later and empty for some rows (when it finished);
2. **a neutral vocabulary of measurement and structure**, in English and Arabic — an id, a year, a rate, a percentage, an average, a price, a count, a duration. One list, in `services/semantic_guard.py` and its mirror `lib/semanticGuard.ts`;
3. **the model, asked once per dataset and kept** (`column_classes.model_hints`): it first says what one row is and whether rows are *things* or *events*, then what each number is. Only column names, ranges and descriptions are sent — no row, no text value, and never the name of a column hidden from the person asking. The answer is stored in the dataset's column settings; **Columns → Ask AI again** re-asks;
4. **the connection's Meaning map**, measured on the database;
5. **the author**, whose correction is never overwritten.

A neutral measurement word is not overruled by the model into a total (a `price` stays a level); only the author can do that.

**Checked on seven datasets from unrelated fields, classified from scratch with the lists removed:** staff pay → level; a listing's price, mileage, age, area and bedrooms → levels; a shipment's weight and fee, a sale's revenue, cost and units → amounts and counts; an exam score → score, higher is better; delivery days → duration; a margin → share.

**Also made neutral:** counts are named after the column ("Emp count", "Shipment count", Arabic "عدد الشحنة") — no "Headcount", no "Hires"; "records finished per month" is found from the dates' values and titled with the date's own name; lateness is measured against whichever real event lands nearest the promise; money is a column with a currency unit or an accounting word (amount, cost, fee, income, expense…); the examples inside the model prompts of the guided setup, the dataset designer, the analyst panel and the connection designer are abstract.

**What is still not neutral, and why it was left:**

* The catalogue of ordered scales recognises some scales that belong to a field (career levels, school stages, clothing sizes, loyalty tiers) beside the universal ones. It recognises values; it imposes nothing on a dataset that does not hold them.
* A tree is still found through the words *parent*, *manager*, *supervisor*, *reports to* (or a second identifier pointing at the key): numbers alone cannot tell a pointer from a quantity.
* Accounting words (*revenue*, *income*, *expense*, *profit*, *budget*) are treated as money words. They belong to every organisation's books rather than to one trade, but they are words of commerce.
* Personal-data detection keeps its lists (phone, device and national identifiers): that is privacy, not suggestion logic.
* **Ask AI** (the question-answering agent) was not part of this work; its few-shot examples still speak of revenue, customers and regions.
* With the AI switched off, a number whose name says nothing about how it is measured is totalled until someone sets it in the Columns tab — there is no longer a list that guesses for one industry.
