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

Not run yet: the model was not reachable from the environment this was built
in. The runner was exercised end to end there (the expected values computed,
the conversations made and deleted, the model's failure scored as failed).
