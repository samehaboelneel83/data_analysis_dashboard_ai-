"""Held-out benchmark: synthetic databases the platform is never tuned on.

The ten test connections show weaknesses; a change only counts when it also
holds here, on data with other shapes, other names and another language.
Each database carries known traps, a persona who knows little about it, and
true answers computed HERE from the generated rows (exact, not estimated).

    python3 generate.py OUT_DIR        # writes h1.db h2.db h3.db and heldout.json

Standard library only; a fixed seed, so the same files every time.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import random
import sqlite3
import statistics
import sys

SEED = 20261013


def h1_ratings(path: pathlib.Path, rnd: random.Random) -> dict:
    """Eight rating items stored as columns; a lookup whose code 0 is a real
    unit; a tiny unit with an extreme average; code columns on a similar range."""
    units = [(0, "Central"), (1, "Harbour"), (2, "Hillside"), (3, "Riverside"), (4, "Old Town"), (5, "Airfield")]
    size = {0: 220, 1: 180, 2: 160, 3: 140, 4: 120, 5: 4}            # Airfield: 4 reviews only
    lift = {0: 0.0, 1: 0.35, 2: -0.2, 3: 0.1, 4: -0.1, 5: 1.4}       # Airfield looks best, on 4 rows
    item_shift = [0.0, 0.1, -0.15, 0.05, 0.2, -0.55, 0.0, 0.1]        # item 6 is the weakest
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE units (unit_code INTEGER PRIMARY KEY, unit_label TEXT);
        CREATE TABLE staff (staff_ref TEXT PRIMARY KEY, unit_code INTEGER REFERENCES units(unit_code), start_day DATE);
        CREATE TABLE reviews (staff_ref TEXT REFERENCES staff(staff_ref), period_start DATE, period_end DATE,
            r1 INTEGER, r2 INTEGER, r3 INTEGER, r4 INTEGER, r5 INTEGER, r6 INTEGER, r7 INTEGER, r8 INTEGER,
            form_kind INTEGER, channel_code INTEGER, slot_code INTEGER);
    """)
    con.executemany("INSERT INTO units VALUES (?, ?)", units)
    rows, by_unit = [], {u: [] for u, _ in units}
    n = 0
    for u, _ in units:
        for _ in range(size[u]):
            n += 1
            ref = f"S{n:04d}"
            con.execute("INSERT INTO staff VALUES (?, ?, ?)", (ref, u, f"20{rnd.randint(15, 23)}-0{rnd.randint(1, 9)}-15"))
            year = rnd.choice([2023, 2024, 2025])
            half = rnd.choice([1, 2])
            start = f"{year}-{'01' if half == 1 else '07'}-01"
            end = f"{year}-{'06-30' if half == 1 else '12-31'}"
            base = 3.2 + lift[u] + rnd.gauss(0, 0.5)
            items = [max(1, min(5, round(base + item_shift[i] + rnd.gauss(0, 0.45)))) for i in range(8)]
            rows.append((ref, start, end, *items, rnd.randint(1, 6), rnd.randint(1, 5), rnd.randint(1, 6)))
            by_unit[u].append(sum(items) / 8)
    con.executemany("INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    item_means = [statistics.mean(r[3 + i] for r in rows) for i in range(8)]
    overall = statistics.mean(sum(r[3:11]) / 8 for r in rows)
    weakest = min(range(8), key=lambda i: item_means[i])
    big = {u: statistics.mean(v) for u, v in by_unit.items() if len(v) >= 30}
    best = max(big, key=big.get)
    label = dict(units)
    return {"id": "H1", "file": path.name, "language": "en",
            "persona": {"work": "Team leader, new to these review forms",
                        "questions": "What is our average rating, which question on the form scores lowest, "
                                     "and which unit is rated best?"},
            "questions": [
                {"id": "H1.1", "question": "What is the average rating?",
                 "checks": [{"type": "number", "value": round(overall, 3), "rel_tol": 0.03}],
                 "truth_note": "mean over reviews of each review's average of r1..r8"},
                {"id": "H1.2", "question": "Which question scores lowest?",
                 "checks": [{"type": "name", "any_of": [f"r{weakest + 1}"]},
                            {"type": "number", "value": round(item_means[weakest], 3), "rel_tol": 0.03}],
                 "truth_note": f"lowest item mean: r{weakest + 1}"},
                {"id": "H1.3", "question": "Which unit is rated best?",
                 "checks": [{"type": "name", "any_of": [label[best]]},
                            {"type": "none_of", "values": [label[5]]}],
                 "truth_note": f"best mean among units with 30+ reviews: {label[best]}; {label[5]} has 4 reviews"},
            ]}


def h2_ledger(path: pathlib.Path, rnd: random.Random) -> dict:
    """Daily balances (a level) with an ALL subtotal row; payments whose last
    month is partial; a busiest complete month."""
    accounts = ["Operating", "Payroll", "Reserve", "Projects", "Suppliers"]
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE balances (day DATE, account TEXT, balance REAL);
        CREATE TABLE payments (payment_no INTEGER PRIMARY KEY, day DATE, account TEXT, amount REAL);
    """)
    start, end = dt.date(2024, 1, 1), dt.date(2024, 12, 31)
    level = {a: rnd.uniform(40_000, 160_000) for a in accounts}
    drift = {a: rnd.uniform(-20, 140) for a in accounts}
    first = last = None
    day = start
    while day <= end:
        if day.weekday() < 5:
            total = 0.0
            for a in accounts:
                level[a] = max(1000.0, level[a] + drift[a] + rnd.gauss(0, 300))
                total += round(level[a], 2)
                con.execute("INSERT INTO balances VALUES (?, ?, ?)", (day.isoformat(), a, round(level[a], 2)))
            con.execute("INSERT INTO balances VALUES (?, ?, ?)", (day.isoformat(), "ALL", round(total, 2)))
            first = first if first is not None else total
            last = total
        day += dt.timedelta(days=1)
    weight = {"Operating": 5, "Payroll": 2, "Reserve": 1, "Projects": 3, "Suppliers": 4}
    season = {m: 1.0 for m in range(1, 13)}
    season[10] = 1.6                                                  # October is the busiest complete month
    pays, n = [], 0
    stop = dt.date(2024, 12, 9)                                       # December is partial (to the 9th)
    day = start
    while day <= stop:
        for _ in range(int(rnd.uniform(6, 10) * season[day.month])):
            n += 1
            a = rnd.choices(accounts, weights=[weight[x] for x in accounts])[0]
            pays.append((n, day.isoformat(), a, round(rnd.uniform(50, 900), 2)))
        day += dt.timedelta(days=1)
    con.executemany("INSERT INTO payments VALUES (?, ?, ?, ?)", pays)
    con.commit()
    con.close()
    by_account: dict[str, float] = {}
    by_month: dict[int, float] = {}
    for _, d, a, amt in pays:
        by_account[a] = by_account.get(a, 0) + amt
        by_month[int(d[5:7])] = by_month.get(int(d[5:7]), 0) + amt
    top = max(by_account, key=by_account.get)
    busiest = max((m for m in by_month if m != 12), key=by_month.get)
    month = dt.date(2024, busiest, 1).strftime("%B")
    change = (last - first) / first * 100
    return {"id": "H2", "file": path.name, "language": "en",
            "persona": {"work": "Treasurer of a small organisation",
                        "questions": "How much did our total balance go up in 2024, which account received "
                                     "the most money in payments, and which month was the busiest?"},
            "questions": [
                {"id": "H2.1", "question": "How much did the total balance go up in 2024?",
                 "checks": [{"type": "number", "value": round(change, 1), "rel_tol": 0.10, "percent": True},
                            {"type": "direction", "value": "up" if change > 0 else "down"}],
                 "truth_note": "sum of the five accounts (not ALL) on the last business day vs the first"},
                {"id": "H2.2", "question": "Which account received the most money in payments?",
                 "checks": [{"type": "name", "any_of": [top]}, {"type": "none_of", "values": ["ALL"]},
                            {"type": "number", "value": round(by_account[top], 2), "rel_tol": 0.03}],
                 "truth_note": "sum of payments.amount by account"},
                {"id": "H2.3", "question": "Which month was the busiest?",
                 "checks": [{"type": "name", "any_of": [month, f"2024-{busiest:02d}"]},
                            {"type": "number", "value": round(by_month[busiest], 2), "rel_tol": 0.03}],
                 "truth_note": "highest payments total among complete months (December runs to the 9th)"},
            ]}


def h3_shipments_ar(path: pathlib.Path, rnd: random.Random) -> dict:
    """Arabic names and values; branches of very different sizes, where the
    biggest has the most returns but not the highest return rate."""
    branches = {"القاهرة": 2600, "الإسكندرية": 900, "أسيوط": 350, "دمياط": 120, "سيوة": 6}
    rate = {"القاهرة": 0.06, "الإسكندرية": 0.08, "أسيوط": 0.15, "دمياط": 0.09, "سيوة": 0.5}
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE "الشحنات" ("رقم_الشحنة" INTEGER PRIMARY KEY, "الفرع" TEXT, "الحالة" TEXT, '
                '"تاريخ_الطلب" DATE, "أيام_التوصيل" INTEGER, "الموعد_بالأيام" INTEGER, "الوزن_كجم" REAL)')
    rows, n = [], 0
    for b, size in branches.items():
        for _ in range(size):
            n += 1
            returned = rnd.random() < rate[b]
            promised = rnd.choice([2, 3, 5])
            days = max(1, int(rnd.gauss(promised + 0.3, 1.6)))
            status = "مرتجع" if returned else "تم التسليم"
            d = dt.date(2025, 1, 1) + dt.timedelta(days=rnd.randint(0, 364))
            rows.append((n, b, status, d.isoformat(), days, promised, round(rnd.uniform(0.2, 30), 1)))
    con.executemany('INSERT INTO "الشحنات" VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
    con.commit()
    con.close()
    returns = sum(1 for r in rows if r[2] == "مرتجع")
    share = returns / len(rows) * 100
    per = {b: sum(1 for r in rows if r[1] == b and r[2] == "مرتجع") / sum(1 for r in rows if r[1] == b)
           for b in branches if branches[b] >= 30}
    worst = max(per, key=per.get)
    late = sum(1 for r in rows if r[4] > r[5])
    return {"id": "H3", "file": path.name, "language": "ar",
            "persona": {"work": "مشرف عمليات جديد في شركة شحن",
                        "questions": "ما نسبة الشحنات المرتجعة؟ وأي فرع لديه أعلى نسبة مرتجعات؟ وكم شحنة تأخرت عن موعدها؟"},
            "questions": [
                {"id": "H3.1", "question": "ما نسبة الشحنات المرتجعة؟",
                 "checks": [{"type": "number", "value": round(share, 2), "rel_tol": 0.05, "percent": True}],
                 "truth_note": "returned / all shipments"},
                {"id": "H3.2", "question": "أي فرع لديه أعلى نسبة مرتجعات؟",
                 "checks": [{"type": "name", "any_of": [worst]}, {"type": "none_of", "values": ["سيوة"]}],
                 "truth_note": f"highest return rate among branches with 30+ shipments: {worst}; the biggest branch "
                               "has the most returns by count; سيوة has 6 shipments"},
                {"id": "H3.3", "question": "كم شحنة تأخرت عن موعدها؟",
                 "checks": [{"type": "number", "value": late, "rel_tol": 0.02}],
                 "truth_note": "delivery days above the promised days"},
            ]}


def main() -> None:
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(SEED)
    scenarios = []
    for maker, name in ((h1_ratings, "h1.db"), (h2_ledger, "h2.db"), (h3_shipments_ar, "h3.db")):
        path = out / name
        path.unlink(missing_ok=True)
        scenarios.append(maker(path, rnd))
    (out / "heldout.json").write_text(json.dumps(
        {"version": 1, "about": "Held-out synthetic databases: never tuned on; a change counts only if it holds here.",
         "scenarios": scenarios}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({s["id"]: [c for q in s["questions"] for c in q["checks"]] for s in scenarios},
                     ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
