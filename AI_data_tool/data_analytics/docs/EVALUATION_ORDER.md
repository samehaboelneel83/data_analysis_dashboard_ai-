# Evaluation order

The order in which a widget's number is produced, for every engine. Order
changes answers: a filter before or after aggregation, a share over the shown
page or over every group. It also changes security: a row rule applied after a
join is a leak. This document is the rule. The engines implement it, and the
tests named in the last column pin each step.

There are three engines:

- **Import**: pandas, over the dataset's file.
- **DuckDB**: SQL over the same file. It is used only when the result is certain
  to be the same; otherwise the widget takes the import path.
- **DirectQuery**: SQL over the customer's database. Anything SQL cannot do
  exactly is done by fetching the rows and running the import engine's own
  code over them. Such a result is exact when every row was fetched, and marked
  `sampled` when the row cap was reached. It is never a different formula.

## The order

| # | Step | What it means | Pinned by |
|---|---|---|---|
| 1 | **Access** | Organization, then the dataset read rule (`docs/CAPABILITY_MATRIX.md`). Everything below runs only for a reader who passed. | `test_security_surfaces.py` |
| 2 | **Row rule** | The reader's `RowSecurityRule`, over every column of the raw rows, before anything else touches them. A rule that cannot be evaluated gives **no rows** (it fails closed). DirectQuery wraps the source query in its own subquery; DuckDB makes it the first `WHERE` term. | `test_get_widget_data_rls.py`, `test_rls_base_frame_choke_point.py`, `test_direct_query_sql.py` |
| 3 | **Column rule** | Denied columns leave the rows before preparation, calculated columns and measures. Anything computed from them fails as an unknown column. DirectQuery refuses a widget, or a measure, that names one (403). | `test_column_security.py`, `test_security_surfaces.py` (derived columns) |
| 4 | **Preparation** | The dataset's prep steps, in order. Joins read each other dataset as the same reader: its own row and column rules first. | `test_prep_steps_api.py`, `test_prep_join.py` |
| 5 | **Dataset filter** | The dataset's `default_filter_expr`. It defines the dataset's scope, so it runs **before** calculated columns. A filter that cannot be evaluated is skipped (it is an author's filter, not a security rule), and it cannot name a calculated column. | `test_widget_data_rls_enforcement.py` |
| 6 | **Calculated columns** | Row expressions, and the window functions (`CUMSUM`, `RANK`, `LAG` …), over the scoped rows. A window function therefore ranks within the dataset filter but **before** widget filters. | `test_calc_date_stats_functions.py` |
| 7 | **Report parameters** | `@name` values are substituted into filters and ranks before the request reaches the engine; expression parameters are computed over the rows of steps 2–3. | `test_report_parameters*.py` |
| 8 | **Relative dates** | "Last 3 months" becomes a date range, anchored on today or on the latest date in the rows of steps 2–6. | `test_relative_dates*.py` |
| 9 | **Widget filters** | Everything the page sends: the widget's filters, cross-filters, slicers, report filters, page prompts and drill steps. They are merged into one list by the client. A filter on a date bucket (`granularity`) compares the bucket's label. A filter on a column the rows do not have is skipped: a cross-filter from another dataset does not apply here. | `test_numeric_goldens.py` (filter narrows before aggregation), `test_engine_parity.py` (drill filter) |
| 10 | **Grouping** | Hierarchy levels and date buckets make the group key. Rows with a missing key are in **no group and no total**. They are counted and disclosed as `missing_category`. | `test_numeric_goldens.py::TestRowsWithNoCategoryAreDisclosed` |
| 11 | **Aggregation** | Per group, over the rows of step 9: `sum` skips missing values (an all-missing group sums to 0), `count` counts non-missing values, `countd` counts distinct ones, `avg` and `median` are over rows. | `test_numeric_goldens.py::TestPlainAggregations` |
| 12 | **Measures** | A named measure is evaluated **at the widget's grain over the rows of step 9**, never over already-aggregated values. `TOTAL()` means the same rows at no grain, excluding missing-key rows, so shares sum to 100. **Division by zero gives no value**, whatever the numerator. | `test_numeric_goldens.py::TestPostAggregationMeasures`, `::TestMeasuresWithMissingAndRanked` |
| 13 | **Percent aggregation** | `pct`: each group's share of the sum over every group of step 11, before anything below removes groups. | `test_numeric_goldens.py::TestPercentAggregation` |
| 14 | **Sort** | By value (ties broken by the group key, ascending) or by name. A time dimension with no stated sort is in time order. | `test_direct_query_totals.py` (tie order) |
| 15 | **HAVING** | Filters on the **group value**, over every group. | `test_series_having_and_custom_sort.py` |
| 16 | **Suppression** | Groups under `suppress_below` rows are hidden, and their rows leave every total below, so they cannot be recovered as total minus visible. | `test_quick_calc_and_suppression.py` |
| 17 | **Ranking** | Top or bottom N (or N %) of the groups; ties at the boundary are kept. **All Other** is the aggregation, or the measure, over the excluded groups' **raw rows**, never an aggregate of their values. | `test_numeric_goldens.py::TestRanking`, `::TestMeasuresWithMissingAndRanked` |
| 18 | **Quick calculation** | Percent of total, difference, percent change, rank: over the surviving groups, All Other included, before the limit. | `test_quick_calc_and_suppression.py` |
| 19 | **Custom order** | `sort_custom` puts the named categories first, in that order. | `test_series_having_and_custom_sort.py` |
| 20 | **Limit** | The page: `limit` groups (default 50). The result says how many there were (`truncation`). | `test_numeric_goldens.py` (limit does not shrink All Other) |
| 21 | **Totals** | From the **rows**, at no grain: every row with a group, minus suppressed ones (step 16), whatever HAVING, ranking or the limit kept on screen. An average total is the average of rows. A measure total is the measure re-evaluated. A "shown" total covers the displayed groups, if fewer. | `test_table_totals.py`, `test_direct_query_totals.py`, `test_pivot_goldens.py` |
| 22 | **Running values** | Running sum and average, over the displayed page. | `test_table_totals.py` |
| 23 | **Display rules** | Conditional styles, over the shaped result. | `test_display_rules*.py` |
| 24 | **Formatting** | Number, date and currency formats are applied by the browser from the dataset's column formats. The server sends raw numbers, and exports carry raw numbers. | — |

### Grids (crosstab, matrix, a bar with two dimensions)

A grid puts one dimension down the side and one across the top. It follows the
same order, with one rule of its own: **suppression is per cell and comes
first**, so no later step reads a suppressed cell. A percentage's base, a
measure's `TOTAL()`, HAVING, ranking, subtotals and totals all leave its rows
out, and a suppressed cell is blank. With `suppress_complement`, a row or
column left with exactly one hidden cell also hides its smallest visible cell.
Then:

- rows with no value on **either** dimension are in no cell and no total, and
  are disclosed as `missing_category`;
- a row's value is its aggregate over its own rows, the number its subtotal
  shows. HAVING, ranking and "sort by value" read it. Without a stated
  `sort_by`, rows stay in label order;
- "All Other" is the aggregation, or the measure, over the rank-excluded rows
  per column. A measure is evaluated over every row at once, so `TOTAL()` in
  the Other row means the whole;
- an intersection with no rows is 0 for a sum or a count and blank for anything
  else (an average of nothing is not 0);
- `pct` and "percent of total" are shares of the whole grid; difference,
  percent change and rank run down each column in display order;
- `limit` cuts rows and says so, like a series.

`tests/test_pivot_goldens.py` pins each of these on all three engines against a
hand-computed fixture, and `tests/test_object_families.py` takes 24 widget
families through role, configuration, a filter, save and reopen, and export.

Results are cached **after** access, with a key that includes the reader's row
rule text, denied columns, the configuration, and the dataset's calculated
columns, measures and prep. A permission change therefore can never be answered
from an entry made under different rules (`test_security_surfaces.py`,
revocation tests).

## How each engine meets it

**Import** runs steps 2–24 in order in `services/widget_data.py`
(`get_widget_data` → `get_widget_data_from_df` → the shaper).

**DuckDB** pushes steps 2, 5, 9 and 11 into one `GROUP BY` over the file, then
hands the shaper one row per group for steps 14–24. Because it does that, it is
used only when none of the other steps apply:

- no prep steps, calculated columns or measures;
- only configuration keys it knows;
- the widget is drawn by the grouped-series shaper (not a box plot or histogram);
- no filter on a date bucket;
- a grain-safe aggregation (sum, avg, min, max, median, percentiles).

In every other case the widget takes the import path.

**DirectQuery** pushes steps 2, 9, 11 and 12 into SQL on the source:

- **Grouped charts** use one `GROUP BY`, `LIMIT`ed to the page. Row count,
  `missing_category`, truncation and totals are measured by their own SQL
  queries.
- **Named measures** are written as SQL by `services/measure_sql.py`: `SUM`,
  `AVG`, `COUNT`, `COUNTD`, `MEDIAN` (PostgreSQL and Oracle only), arithmetic
  with division as `NULLIF`, `IF`, comparisons, `abs` and `round`. A KPI of a
  measure is one SQL value.
- **Fetching the rows instead.** SQL on a page of groups cannot give step 12's
  `TOTAL()`/`CALC()`/`BYGROUP()`, nor steps 15–22 over every group. So the rows
  are fetched and the import code does the rest when a widget uses any of:
  - HAVING, suppression, quick calculations, custom order, running values;
  - date buckets or hierarchy levels, or a drill filter on a bucket;
  - Top-N, a crosstab, a second measure;
  - a measure SQL cannot express.

  The fetch is exact up to the analysis row cap (250,000 rows). Above it, the
  rows are a random sample and the result says `sampled`.
- **Refused:** calculated columns and a dataset filter, with an explicit
  message.

`tests/test_engine_parity.py` runs each of these cases on all three engines and
requires the import engine's rows. `tests/test_numeric_goldens.py` checks
hand-computed values on all three. Measures were also checked against a live
PostgreSQL 16 (Margin, weighted average, share of total, a zero denominator, a
conditional sum, median, distinct count), and every value matched the import
engine.

## Known differences

- **A filter on an unknown column.** Import skips it (step 9). DirectQuery
  refuses it (400), because every column name that reaches SQL must be a real
  column of the dataset.
- **Series measure totals and `TOTAL()`** exclude missing-key rows. A KPI of the
  same measure includes them, and `missing_category` says how many there were.
