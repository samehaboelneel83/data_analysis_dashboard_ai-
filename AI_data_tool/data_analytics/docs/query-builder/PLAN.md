# Query builder — SQL safety and condition boxes

Date: 2026-10-10 · Owner request: "add a tab to build the query with nested boxes"
and "I need to avoid SQL injection". Agreed plan, in order:

- [x] **1. Close the injection hole** (backend only)
- [x] **2. Conditions as nested boxes** ("Match all / any" groups) in the Design tab
- [x] **3. Calculated columns made easy**: done 2026-10-10 at the owner's request (see below)
- [ ] **4. A full separate "Boxes" tab**: held back (it would be a third editor of the
      same query, the duplication just removed from the Fields panel)

## 1. SQL safety: what was wrong and what changed

| # | Problem | Fix |
|---|---|---|
| S1 | **Injection on MySQL / MariaDB / ClickHouse.** Values were written as `'…'` with quotes doubled. Those databases also treat `\` as an escape, so the value `\' OR 1=1 #` became the string `'` followed by real SQL `OR 1=1` | `services/sql_safety.encode_literal`: per database. Backslashes are doubled where they are an escape, and on any database we don't know. NUL characters and NaN/infinity are refused |
| S2 | The `contains` filter built its `LIKE` inline (same weakness), and `%` / `_` typed by the person acted as wildcards ("50%" matched "500") | `like_pattern`: encoded like every value, with `%` and `_` matched literally (`ESCAPE '!'`) |
| S3 | A quote character inside a table/column name could end the quoted name | `quote_ident`: the quote is doubled (`a"b` → `"a""b"`) |
| S4 | **Hand-written SQL was not checked at all.** The SQL tab, custom-SQL imports and previews ran anything with the connection's rights: `DELETE`, `DROP`, `SELECT … INTO`, `EXEC`, or a second statement after `;` | `ensure_read_only`: exactly one read (SELECT / WITH … SELECT / UNION). Checked by parsing in the database's own dialect, plus a check for a second statement. A saved live dataset is also checked for a second statement on every read |
| S5 | SQL Server and ClickHouse queries were parsed as PostgreSQL by the existing SQL checks (dialect map gap) | `agent/validate._DIALECTS` gains `sqlserver`, `mariadb`, `clickhouse` |
| S6 | **Ask AI** checked only the top of the AI model's SQL, so `WITH d AS (DELETE … RETURNING *) SELECT …` (deletes on PostgreSQL) and `SELECT … INTO` (creates a table) passed. The model can be steered by text inside the data | Ask AI's first check (`agent/validate.py`, V1) now also runs `ensure_read_only` over the whole query |

Values stay literals (not bound parameters). The builder's SQL is shown to the person,
saved as the dataset's query, and wrapped later by DirectQuery and re-imports, so it must
be complete text. That's why the encoder is per database.

**Older bugs found while testing, fixed too (real PostgreSQL Cars DB):**

- Any hand-written SQL containing `%` (every `LIKE`) failed on PostgreSQL and MySQL
  ("immutabledict is not a sequence"): the driver read `%` as a placeholder. Now `%` is
  doubled for those drivers only.
- **Incremental refresh never worked on PostgreSQL**: `:cursor_val` was sent raw, the
  driver could not bind it (a syntax error at ":"), and every refresh silently fell back to
  a full reload. It now goes through SQLAlchemy `text()`. Checked: 856 new rows above the
  watermark.

Read-only database accounts are still the strongest protection. With this change the app
is safe even on a connection that can write.

## 2. Condition boxes

- Filters is now a box, "Rows to keep: all of these must be true / any one of these is
  enough". It holds conditions and **groups** (boxes inside boxes, up to 5 deep, each with
  its own all/any and a coloured edge per level). AND/OR is shown between items.
- Comparisons in plain words (is, is not, is at least, contains, is one of, is empty…).
- An unfinished condition is outlined red and says, inside its box, what it needs
  ("Choose a column — until then this condition is left out"). It is never sent half-made.
- The backend compiles a group with the same code as any condition: names checked
  against the database, values encoded, nesting bounded.
- **Fixed on the way:** reopening a saved query silently dropped any sub-query condition
  (and the next save removed it from the dataset). Now it's kept and shown as "Kept as
  saved".
- English and Arabic (right-to-left).

## Results

| Check | Result |
|---|---|
| New backend tests `test_sql_safety.py` (attacks × 6 databases, read via each dialect's parser; real SQLite run; read-only gate; driver text) | 108 pass |
| New backend tests `test_query_builder_groups.py` (nesting, brackets, empty groups, limits, sub-query in a group, real SQLite run) | 9 pass |
| Related backend suites (query builder, DirectQuery, imports, refresh, connections, guided setup, agent, security surfaces, docs) | all pass (1,063 + 372 + 580 across runs) |
| Frontend: type check, all tests (339 files / 4,257 tests), production build | pass |
| Live, Cars DB (PostgreSQL): attack value `\' OR 1=1 --` → 0 rows; `' OR '1'='1` → 0 rows | ✅ |
| Live: `SELECT 1; SELECT 2`, `SELECT … INTO`, `DELETE …` refused with a plain reason | ✅ |
| Live: `contains "Ki"` → Kia; custom `LIKE 'Hy%'` → Hyundai (both failed before) | ✅ |
| Live, as a user: built `condition = Used AND (make = Kia OR make = Hyundai)` with boxes; server SQL and preview correct; unfinished condition message | ✅ |
| Arabic: all box texts translated, layout right-to-left | ✅ |

Known, not changed here: other parts of the query builder dialog are English-only
("+ Add join", "+ Add column", "Walk a hierarchy", "Preview data"…), and backend error
messages are English.

## Wider check (2026-10-10, after the owner asked "and SQL injection?")

Every other place that sends SQL was looked at:

- **Widgets / DirectQuery, live counts, auto-bins, index advice:** values travel as
  bound parameters; names are checked against the dataset's columns. No change needed.
- **Ask AI:** gap S6 above, fixed and tested.
- **Measures** (`measure_eval`, Python expressions): the public entry points check the
  expression first and refuse attribute access, lambdas and comprehensions, so the known
  Python sandbox escapes are blocked (verified). The inner `_eval` is unsafe on its own
  and must only be reached through those entry points.

## 3. Calculated columns without writing code (2026-10-10)

**Evaluation first** (as a user, on "Demo — Sales Overview"): the builder opened on a code
box. "Simple" mode only built true/false conditions, and its IF was three empty text
boxes. Errors were raw Python (`name 'cot' is not defined`). Test showed six sample
values, so "every row got the same label" went unnoticed.

**Engine bugs found and fixed** (`services/widget_data.py`):

- `and` / `or` / `not` between columns failed ("the truth value of a Series is
  ambiguous"), although the builder offers them. They are now applied row by row
  (`_ElementwiseLogic`); single values keep their usual meaning, and the helpers cannot
  be typed by a person.
- `CONCAT` took exactly two values; it now takes any number.

**What the person now gets:**

1. **"What do you want to make?"** opens every new column: *Calculate from two columns*
   (± × ÷, % change, % of; division by 0 is left empty, not "infinity"),
   *Group numbers into bands* (limits in order, a label each, "otherwise", optional
   "no value"), *Label rows by conditions* (the condition boxes from step 2, "If / Else
   if / Otherwise"), *Combine text*, *Part of a date*, *Clean text*. Each form writes the
   formula (shown, and editable with "Edit this formula myself") and suggests the
   column name. "Write a formula myself" keeps the old editor.
2. **Plain errors** (`services/expr_explain.py`, worded in English/Arabic by the
   frontend): "There is no column or function called "cot". Did you mean "cost"?",
   missing bracket, single `=`, formula ending in an operator, open quote, text used in
   math, wrong number of values. The raw error stays behind "Show details".
3. **Test describes the whole column**: label counts ("Other · 1,744 · Focus · 256",
   with a warning when every row got the same label), or lowest / average / highest,
   plus how many rows are empty or "infinity".

**Checked:** frontend 340 files / 4,273 tests, type check, build; backend
`test_calc_formula_help.py` (26: engine fixes, every problem code, summaries, and every
formula the forms write run by the real evaluator) plus 765 related tests. Live, as a
user: label rules with an OR group → 2,000 rows, Focus 256 / Other 1,744; revenue ÷ units
→ −1,195 to 4,303, average 66.6; typo → "Did you mean cost?"; Arabic bands → كبير 1,842 ·
متوسط 107 · صغير 51. Nothing was saved to the demo data. A bug found in this re-test was
fixed: the label form wiped the Test result as soon as it arrived.

**Follow-up, same day: both items left open are now done.**

- **Date parts are whole numbers.** `YEAR`, `QUARTER`, `MONTH`, `DAY`, `WEEKDAY`,
  `DAYOFYEAR`, `HOUR`/`MINUTE`/`SECOND` and `DATEDIFF` by day/week/month/year return
  whole numbers with real gaps (pandas `Int64`, the type `WEEK` already used): 2024, not
  2024.0. Checked through JSON (empty → null), grouping, Parquet and CSV. A comparison
  on an empty date now counts as "no" in `IF` / `SWITCH`, as filters already did.
  Live: `YEAR(date)` → 2024, 2025.
- **Measures get "What do you want to measure?"** (`lib/measureTemplates.ts`,
  `MeasureTemplatePicker`): *Summarise a column* (total, average, median, number of
  different, lowest, highest), *Compare two totals* (÷, % of, % change, minus; 0 →
  empty), *Share of the total*, *Only some rows* (total / average / row count, with the
  condition boxes). Each writes the formula and a name; "Write a formula myself" keeps
  the editor. Measure Test errors are plain too ("Did you mean revenue?").
- **Measure engine gaps fixed:** `and`/`or`/`not` failed there too (now shared:
  `services/expr_logic.py`), and there was no Lowest/Highest (`MIN`/`MAX` added).
- **Checked:** backend 47 in `test_calc_formula_help.py` (every measure-form formula at
  whole-table and per-group level) plus 969 related; frontend 341 files / 4,280 tests,
  build. Live on the demo dataset: Highest revenue by region; each region's share
  (≈25% each, adding to 100%); online-only revenue per region; the typo message. Nothing
  saved.
