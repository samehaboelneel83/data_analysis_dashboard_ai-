# Ask AI: a held-out bilingual benchmark (E11)

The plan asks for Ask AI to be measured, not asserted: a held-out set of
questions in English and Arabic, with targets, scored the same way every time.

## What is in it

`qa/ask_benchmark.json`: 13 questions, each asked in English and in Arabic
(26 cases), about the demo dataset "Demo — Sales":

- **10 answers**: totals, a filtered total, a count, an average, a median, a
  difference between two regions, and which region and category lead.
- **3 refusals, 6 cases**: deleting the dataset (Ask AI does not change
  data), a figure the data does not hold (a salary), and editing a dashboard
  (the page copilot does that, not Ask AI).

The Arabic questions keep the data's own English values ("Europe",
"Online"), as a reader of this data would type them.

Expected numbers are not written in the file. The runner computes each one
from the data through the widget-data API, as the same user, so the
benchmark stays right when the demo data changes.

## How it is scored

`app/services/agent/benchmark.py`:

- **A number** is right when the answer states the expected value at the
  precision it wrote it ("2.2 million" for 2,221,091.66) or within 0.5 %.
  Arabic-Indic digits, thousands separators and percentages are read as the
  numbers they are.
- **A name** (the leading region) is right when the answer names it.
- **A refusal** is right when the answer declines or asks to clarify, and
  states no number.
- **Grounding**: each answered case is also checked with the evidence tracer:
  a number in the answer that no query result supports makes it ungrounded,
  even when the answer is right.

## Targets (proposed; to agree with the owner)

| Measure | English | Arabic |
|---|---|---|
| Answers right | ≥ 90 % | ≥ 85 % |
| Ungrounded answers | 0 | 0 |
| Refusals right | 3 of 3 | 3 of 3 |

## Running it

With the language model reachable and the demo loaded:

```
python backend/scripts/bench_ask.py --base http://localhost:8000 \
    --email admin@datalytics.local --password demo-password --out ask_bench.json
```

Each question is asked in a conversation of its own (deleted after), so no
answer leans on an earlier one. It prints each case as PASS or FAIL with the
reason, then the summary per language; `--out` keeps every answer.

## Results

**2026-10-11, model `qwen3.8_27b` (Auto), demo dataset, 26 cases.** Run twice on the same day: once with the
example questions as they were, and once after they were reworded in neutral terms (no customers, revenue,
departments or city names -- docs/discovery/PLAN.md, phase 0).

| | English | Arabic |
|---|---|---|
| Answers right — before rewording | 9 of 10 (90 %) | 9 of 10 (90 %) |
| Answers right — after rewording | 9 of 10 (90 %) | 9 of 10 (90 %) |
| Ungrounded answers (both runs) | 0 | 0 |
| Refusals right — before | 3 of 3 | 2 of 3 |
| Refusals right — after | 3 of 3 | 2 of 3 |

The same three cases fail in both runs, so the rewording changed nothing measurable:

* `na-minus-europe.en` -- a difference of two totals; the answer gives the two totals and a ratio, not the difference.
* `avg-margin.ar` -- an average of a percentage column; the Arabic question gets a different figure.
* `refuse-salary.ar` -- asked for a column the data does not have, in Arabic; it does not decline.

(The "after" run first scored `refuse-dashboard.en` as wrong: the answer began "I can’t change dashboard
settings here" with a typographic apostrophe, which the scorer's refusal pattern did not accept. The pattern was
fixed; the answer was a correct refusal.)

Targets met in English on answers and refusals; Arabic meets the answers target and misses one refusal.
