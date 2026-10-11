"""A courier company's database, for testing the guided setup on data nobody has seen.

    docker exec -i datalytics_backend python - < qa/fixtures/generate_logistics_db.py

Creates the Postgres database `nile_express` (dropped first if it exists) on
the app's own Postgres server: branches, customers, drivers, shipments and
complaints -- with foreign keys, English and Arabic names, and the kinds of
mess real operational data has, so the Check & discover step has something
true to find:

* 420 shipment rows entered twice (exact copies);
* extra spaces around some governorate names;
* weight -1 where the parcel was never weighed;
* `declared_value` kept as text;
* `internal_note` almost always empty, `currency` always "EGP";
* a few negative delivery fees;
* a few parcels "delivered" before they were created.

The patterns are deliberate, so an answer can be checked against the truth:
Same Day is the dearest service and the one most often late; cash on
delivery is returned about three times as often as prepaid; Upper Egypt is
slowest; volume grows through 2024-2025 with a peak every November.
"""
import os
import random
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values

SEED = 20261010
DB = "nile_express"
rnd = random.Random(SEED)

HOST = os.environ.get("PGHOST", "postgres")
USER = os.environ.get("POSTGRES_USER", "datalytics")
PASSWORD = os.environ.get("POSTGRES_PASSWORD", "datalytics_secret")

GOVERNORATES = [  # name, arabic, region, weight in volume, extra delivery days
    ("Cairo", "القاهرة", "Greater Cairo", 26, 0.0), ("Giza", "الجيزة", "Greater Cairo", 16, 0.2),
    ("Qalyubia", "القليوبية", "Greater Cairo", 6, 0.4), ("Alexandria", "الإسكندرية", "Delta & North", 12, 0.6),
    ("Dakahlia", "الدقهلية", "Delta & North", 6, 0.9), ("Gharbia", "الغربية", "Delta & North", 5, 0.9),
    ("Sharqia", "الشرقية", "Delta & North", 6, 1.0), ("Port Said", "بورسعيد", "Canal", 3, 1.0),
    ("Suez", "السويس", "Canal", 3, 1.0), ("Ismailia", "الإسماعيلية", "Canal", 3, 1.1),
    ("Fayoum", "الفيوم", "Upper Egypt", 3, 1.6), ("Minya", "المنيا", "Upper Egypt", 4, 2.1),
    ("Assiut", "أسيوط", "Upper Egypt", 3, 2.4), ("Sohag", "سوهاج", "Upper Egypt", 2, 2.7),
    ("Luxor", "الأقصر", "Upper Egypt", 1, 3.0), ("Aswan", "أسوان", "Upper Egypt", 1, 3.4),
]
SERVICES = [  # name, share, base fee, promised days, chance of being late
    ("Standard", 0.52, 55, 4, 0.12), ("Express", 0.27, 95, 2, 0.16),
    ("Same Day", 0.13, 160, 1, 0.31), ("International", 0.08, 780, 9, 0.22),
]
SEGMENTS = [("E-commerce seller", 0.55), ("Business", 0.3), ("Individual", 0.15)]
CATEGORIES = ["Clothing", "Electronics", "Cosmetics", "Documents", "Home goods", "Books", "Food & sweets", "Spare parts"]
RETURN_REASONS = ["Customer refused", "Wrong address", "Customer unreachable", "Damaged parcel", "Changed mind"]
COMPLAINT_TYPES = [("Late delivery", 0.42), ("Damaged parcel", 0.2), ("Rude courier", 0.1),
                   ("Wrong item delivered", 0.08), ("Lost parcel", 0.08), ("Overcharged", 0.12)]
FIRST = ["Ahmed", "Mohamed", "Mahmoud", "Mostafa", "Omar", "Youssef", "Karim", "Hassan", "Tarek", "Amr",
         "Khaled", "Ibrahim", "Sherif", "Hany", "Walid", "Sameh", "Emad", "Said", "Ramy", "Nader"]
LAST = ["Hassan", "Ali", "Ibrahim", "Sayed", "Fathy", "Mansour", "Saleh", "Farouk", "Gamal", "Nabil",
        "Abdallah", "Shaker", "Zaki", "Fouad", "Helmy"]
SHOPS = ["Store", "Boutique", "Trading", "Market", "Online", "Pharma", "Tech", "Home", "Fashion", "Supplies"]


def pick(pairs):
    r, acc = rnd.random(), 0.0
    for value, share in pairs:
        acc += share
        if r <= acc:
            return value
    return pairs[-1][0]


def connect(db):
    return psycopg2.connect(host=HOST, user=USER, password=PASSWORD, dbname=db)


def main():
    admin = connect("postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (DB,))
        cur.execute(f"DROP DATABASE IF EXISTS {DB}")
        cur.execute(f"CREATE DATABASE {DB}")
    admin.close()

    conn = connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE branches (
            branch_id SERIAL PRIMARY KEY, branch_name TEXT NOT NULL, branch_name_ar TEXT,
            governorate TEXT NOT NULL, region TEXT NOT NULL, opened_on DATE, monthly_rent_egp NUMERIC(12,2));
        CREATE TABLE customers (
            customer_id SERIAL PRIMARY KEY, customer_name TEXT NOT NULL, segment TEXT NOT NULL,
            phone TEXT, email TEXT, governorate TEXT, joined_on DATE, account_manager TEXT);
        CREATE TABLE drivers (
            driver_id SERIAL PRIMARY KEY, driver_name TEXT NOT NULL, branch_id INT REFERENCES branches(branch_id),
            vehicle_type TEXT, hired_on DATE, national_id TEXT);
        CREATE TABLE shipments (
            shipment_id BIGINT, tracking_no TEXT, customer_id INT REFERENCES customers(customer_id),
            origin_branch_id INT REFERENCES branches(branch_id), driver_id INT REFERENCES drivers(driver_id),
            service_type TEXT, parcel_category TEXT, destination_governorate TEXT, destination_region TEXT,
            weight_kg NUMERIC(8,2), declared_value TEXT, delivery_fee_egp NUMERIC(10,2),
            payment_method TEXT, cod_amount_egp NUMERIC(12,2), status TEXT, return_reason TEXT,
            created_at TIMESTAMP, promised_date DATE, delivered_at TIMESTAMP, delivery_days NUMERIC(6,1),
            is_late BOOLEAN, delivery_attempts INT, customer_rating INT,
            currency TEXT, internal_note TEXT, updated_at TIMESTAMP);
        CREATE TABLE complaints (
            complaint_id SERIAL PRIMARY KEY, shipment_id BIGINT, customer_id INT REFERENCES customers(customer_id),
            branch_id INT REFERENCES branches(branch_id), complaint_type TEXT, opened_at TIMESTAMP,
            resolved_at TIMESTAMP, resolution_hours NUMERIC(8,1), compensation_egp NUMERIC(10,2), status TEXT);
        CREATE TABLE app_sessions_log (
            id SERIAL PRIMARY KEY, session_token TEXT, user_agent TEXT, created_at TIMESTAMP);
        COMMENT ON TABLE shipments IS 'One row per parcel handed to the company for delivery';
    """)

    branches = []
    for i, (gov, gov_ar, region, weight, _d) in enumerate(GOVERNORATES):
        for n in range(2 if weight >= 12 else 1):
            name = f"{gov} {'Central' if n == 0 else 'East'} Hub"
            branches.append((name, f"فرع {gov_ar} {'الرئيسي' if n == 0 else 'الشرقي'}", gov, region,
                             datetime(2018 + rnd.randint(0, 5), rnd.randint(1, 12), 1).date(),
                             round(rnd.uniform(18000, 95000), 2)))
    execute_values(cur, "INSERT INTO branches (branch_name, branch_name_ar, governorate, region, opened_on, "
                        "monthly_rent_egp) VALUES %s", branches)
    cur.execute("SELECT branch_id, governorate FROM branches")
    branch_ids = cur.fetchall()
    branches_of = {}
    for bid, gov in branch_ids:
        branches_of.setdefault(gov, []).append(bid)

    customers = []
    for i in range(1800):
        segment = pick(SEGMENTS)
        person = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        name = person if segment == "Individual" else f"{rnd.choice(LAST)} {rnd.choice(SHOPS)}"
        gov = rnd.choices([g[0] for g in GOVERNORATES], weights=[g[3] for g in GOVERNORATES])[0]
        customers.append((name, segment, f"01{rnd.randint(0, 2)}{rnd.randint(10000000, 99999999)}",
                          f"{name.lower().replace(' ', '.')}{i}@example.com", gov,
                          (datetime(2021, 1, 1) + timedelta(days=rnd.randint(0, 1700))).date(),
                          f"{rnd.choice(FIRST)} {rnd.choice(LAST)}" if segment != "Individual" else None))
    execute_values(cur, "INSERT INTO customers (customer_name, segment, phone, email, governorate, joined_on, "
                        "account_manager) VALUES %s", customers)
    # A few big senders carry much of the volume, as in any courier's book.
    cust_weights = [rnd.paretovariate(1.3) * (4 if c[1] == "E-commerce seller" else 2 if c[1] == "Business" else 0.4)
                    for c in customers]

    drivers = []
    for bid, _gov in branch_ids:
        for _ in range(rnd.randint(5, 11)):
            drivers.append((f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", bid,
                            rnd.choices(["Motorcycle", "Van", "Truck"], weights=[6, 3, 1])[0],
                            (datetime(2019, 1, 1) + timedelta(days=rnd.randint(0, 2400))).date(),
                            str(rnd.randint(27000000000000, 30312319999999))))
    execute_values(cur, "INSERT INTO drivers (driver_name, branch_id, vehicle_type, hired_on, national_id) VALUES %s",
                   drivers)
    cur.execute("SELECT driver_id, branch_id FROM drivers")
    drivers_of = {}
    for did, bid in cur.fetchall():
        drivers_of.setdefault(bid, []).append(did)

    start, end = datetime(2024, 1, 1), datetime(2026, 9, 30)
    days = (end - start).days
    region_of = {g[0]: g[2] for g in GOVERNORATES}
    extra_of = {g[0]: g[4] for g in GOVERNORATES}
    rows = []
    sid = 500000
    for _ in range(64000):
        # More parcels as time goes on, and a peak every November.
        while True:
            day = start + timedelta(days=rnd.randint(0, days), minutes=rnd.randint(8 * 60, 21 * 60))
            growth = 0.45 + 0.55 * ((day - start).days / days)
            season = 1.9 if day.month == 11 else 1.25 if day.month in (12, 3) else 1.0
            if rnd.random() < growth * season / 1.9:
                break
        sid += 1
        service, _share, base, promised, late_p = rnd.choices(SERVICES, weights=[s[1] for s in SERVICES])[0]
        dest = rnd.choices([g[0] for g in GOVERNORATES], weights=[g[3] for g in GOVERNORATES])[0]
        if service == "Same Day":
            dest = rnd.choice(["Cairo", "Giza", "Qalyubia"])
        origin_gov = rnd.choices(["Cairo", "Giza", "Alexandria", dest], weights=[5, 3, 2, 3])[0]
        origin = rnd.choice(branches_of[origin_gov])
        cust = rnd.choices(range(1, len(customers) + 1), weights=cust_weights)[0]
        segment = customers[cust - 1][1]
        category = rnd.choice(CATEGORIES)
        weight = round(min(60.0, max(0.1, rnd.lognormvariate(0.5, 0.9))), 2)
        fee = round(base + weight * (9 if service != "International" else 60) + rnd.uniform(-8, 12)
                    + (15 if region_of[dest] == "Upper Egypt" else 0), 2)
        cod = rnd.random() < (0.72 if segment == "E-commerce seller" else 0.3)
        payment = "Cash on delivery" if cod else rnd.choice(["Prepaid card", "Prepaid wallet", "Company account"])
        value = round(rnd.lognormvariate(6.3, 0.9), 0)
        cod_amount = value if cod else 0
        recent = day > end - timedelta(days=5)
        returned = rnd.random() < (0.145 if cod else 0.045) * (1.35 if category == "Clothing" else 1.0)
        lost = rnd.random() < 0.004
        status = "In transit" if recent else "Lost" if lost else "Returned" if returned else "Delivered"
        late = rnd.random() < late_p + (0.1 if region_of[dest] == "Upper Egypt" else 0)
        took = max(0.2, promised * rnd.uniform(0.45, 1.0) + extra_of[dest] * 0.4)
        if late:
            took = promised + rnd.uniform(0.6, 4.5) + extra_of[dest] * 0.5
        if service == "Same Day" and not late:
            took = rnd.uniform(0.2, 0.95)
        delivered = day + timedelta(days=took) if status in ("Delivered", "Returned") else None
        attempts = 1 + (rnd.random() < 0.18) + (rnd.random() < 0.05) + (2 if status == "Returned" else 0)
        rating = None
        if status == "Delivered" and rnd.random() < 0.6:
            rating = max(1, min(5, round(rnd.gauss(4.4 - (1.5 if late else 0), 0.8))))
        rows.append([
            sid, f"NX{sid}EG", cust, origin, rnd.choice(drivers_of[origin]), service, category, dest,
            region_of[dest], weight, str(int(value)), fee, payment, cod_amount, status,
            rnd.choice(RETURN_REASONS) if status == "Returned" else None, day,
            (day + timedelta(days=promised)).date(), delivered,
            round(took, 1) if delivered else None, bool(late) if delivered else None, attempts, rating,
            "EGP", "checked by supervisor" if rnd.random() < 0.02 else None, delivered or day])

    # ── the mess ────────────────────────────────────────────────────────────
    for r in rnd.sample(rows, 1300):
        r[9] = -1                                    # never weighed
    for r in rnd.sample(rows, 900):
        r[7] = rnd.choice([r[7] + " ", " " + r[7], r[7] + "  "])   # stray spaces
    for r in rnd.sample(rows, 38):
        r[11] = -abs(float(r[11]))                   # refund keyed in as the fee
    for r in rnd.sample([r for r in rows if r[18] is not None], 55):
        r[18] = r[16] - timedelta(days=rnd.randint(1, 20))   # "delivered" before it existed
    copies = [list(r) for r in rnd.sample(rows, 420)]         # entered twice
    rows += copies
    rnd.shuffle(rows)
    execute_values(cur, "INSERT INTO shipments VALUES %s", rows, page_size=2000)

    complaints = []
    for r in rows:
        late, status = r[20], r[14]
        chance = 0.012 + (0.11 if late else 0) + (0.5 if status == "Lost" else 0) + (0.03 if status == "Returned" else 0)
        if rnd.random() < chance and r[18] is not None or (status == "Lost" and rnd.random() < 0.5):
            kind = "Lost parcel" if status == "Lost" else "Late delivery" if late and rnd.random() < 0.75 \
                else pick(COMPLAINT_TYPES)
            opened = (r[18] or r[16]) + timedelta(hours=rnd.randint(1, 96))
            hours = round(rnd.lognormvariate(3.1 if kind != "Lost parcel" else 4.6, 0.7), 1)
            done = rnd.random() < 0.9
            complaints.append((r[0], r[2], r[3], kind, opened, opened + timedelta(hours=hours) if done else None,
                               hours if done else None,
                               round(rnd.uniform(40, 900), 2) if kind in ("Lost parcel", "Damaged parcel") and done else 0,
                               "Resolved" if done else "Open"))
    execute_values(cur, "INSERT INTO complaints (shipment_id, customer_id, branch_id, complaint_type, opened_at, "
                        "resolved_at, resolution_hours, compensation_egp, status) VALUES %s", complaints,
                   page_size=2000)
    execute_values(cur, "INSERT INTO app_sessions_log (session_token, user_agent, created_at) VALUES %s",
                   [(f"{rnd.getrandbits(96):x}", "Mozilla/5.0", start + timedelta(minutes=rnd.randint(0, days * 1440)))
                    for _ in range(3000)])
    cur.execute("CREATE INDEX ON shipments (created_at); CREATE INDEX ON shipments (customer_id); ANALYZE;")
    conn.commit()
    cur.execute("SELECT (SELECT count(*) FROM shipments), (SELECT count(*) FROM complaints), "
                "(SELECT count(*) FROM customers), (SELECT count(*) FROM branches), (SELECT count(*) FROM drivers)")
    print("nile_express: shipments, complaints, customers, branches, drivers =", cur.fetchone())
    conn.close()


if __name__ == "__main__":
    main()
