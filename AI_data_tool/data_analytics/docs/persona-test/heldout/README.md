# Held-out benchmark

The ten persona-test connections show where the platform is weak. They are not
targets: a rule tuned until they pass would break on the next database. This
folder holds databases the platform is **never tuned on**. A change counts only
when it holds or improves here too.

| Id | Database | Shape and traps | Persona |
|---|---|---|---|
| H1 | `h1.db` — ratings (neutral English names) | eight rating items stored as columns `r1…r8`; a lookup whose code `0` is a real unit; a unit with 4 reviews and an extreme average; three code columns on a similar 1–6 range | Team leader: average rating, lowest-scoring question, best unit |
| H2 | `h2.db` — ledger | daily balances (a level) with an `ALL` row that is the sum of the others; payments whose December stops on the 9th; a busiest complete month | Treasurer: balance change over 2024, account receiving most, busiest month |
| H3 | `h3.db` — الشحنات (Arabic table, columns and values) | branches of very different sizes: the biggest has the most returns, a mid-size one the highest rate; a branch with 6 shipments | مشرف عمليات: نسبة المرتجعات، أعلى فرع في نسبة المرتجعات، عدد الشحنات المتأخرة |

`generate.py` makes the files and `heldout.json` (same format as
`../benchmark.json`), computing every true answer from the generated rows. It
uses a fixed seed and the standard library only:

```bash
python3 generate.py .
```

In the app they are the connections "Held-out H1 — ratings", "Held-out H2 —
ledger" and "Held-out H3 — الشحنات" (SQLite files in `/app/uploads/heldout_h*.db`).
Run and score them like the main benchmark:

```bash
python scripts/persona_run.py /tmp/heldout.json --user 8
python scripts/persona_benchmark.py /tmp/heldout.json --flow H1=<id> --flow H2=<id> --flow H3=<id>
```

Rules for this folder: never change a generator to make the platform pass; never
read these files while writing a rule. When a held-out result is wrong, find the
general cause, as for any other database.
