# Profile: demo_sqlite (SQLite /app/uploads/demo_1_directquery.db, table live_orders)

## 1. Table
live_orders: 12,000 rows, 8 columns: order_id INTEGER (1..12000, 12,000 distinct = unique key, ID not a measure), order_date TEXT (ISO 'YYYY-MM-DD', stored as text, not DATE), month TEXT ('YYYY-MM', redundant with order_date; 0 mismatches), city TEXT (24 distinct + 471 NULL), channel TEXT (4: Online 3,074, Partner 2,973, Retail 2,959, Wholesale 2,994), priority TEXT (4: Standard 4,000, Express 3,000, Priority 3,000, Overnight 2,000), quantity INTEGER (1..24, sum 151,247), amount REAL (70.99..3,556.02, sum 10,888,973.27). No declared keys, single table, no joins.

## 2. Grain and dates
One row per order (order total in `amount`, not per unit). order_date 2025-01-01 .. 2025-12-31, all 365 dates present (every weekday 1,657-1,784 rows, so no weekday seasonality). 12 months, 893 (Feb) to 1,075 (Oct) orders per month.

## 3. Measures and traps
- Revenue = SUM(amount) = 10,888,973.27; orders = COUNT(*) = 12,000; AOV = AVG(amount) = 907.41 (do not average per-city averages); avg quantity 12.60; amount/quantity avg 141.85 per unit (amount does NOT depend on quantity: quantity 1 orders average 907.0, so "price per unit" is meaningless).
- Dates are text: need parsing for time axis; `month` is a text label.
- Null city: 471 rows (3.9%), 424,129.10 revenue (3.9%) - shows up as a blank/None city; ranking cities with None included puts None as 18th of 25 groups.
- Uniform/synthetic-looking distribution: channel and priority averages within 1.6% of each other (AOV: Wholesale 915.66, Online 907.50, Partner 905.20, Retail 901.20); no strong signals expected. Priority exactly 4000/3000/3000/2000 (synthetic round counts).
- Outliers: 6 orders > 3,000, 5 orders < 100 (extremes are not errors). 2,554 orders have quantity >= 20. No negatives, no zeros, no nulls except city; 0 duplicate rows ignoring order_id.
- Cardinality: city 24 (+NULL), channel 4, priority 4, month 12.

## 4. Personas and true answers
### Persona A - sales manager ("I know total sales")
A1. Total revenue 2025? `select sum(amount) from live_orders` = 10,888,973.27 (12,000 orders).
A2. Which month sold most? `group by month`: highest revenue 2025-10 = 964,178.03 (1,075 orders), then 2025-01 955,644.66; lowest 2025-02 = 804,155.13 (893 orders, shortest month). Highest AOV month is 2025-12 = 930.21.
A3. Best channel by revenue? Online 2,789,665.32 (3,074 orders), Wholesale 2,741,479.78, Partner 2,691,164.92, Retail 2,666,663.25; by AOV Wholesale is best (915.66).
### Persona B - regional analyst ("I know cities")
B1. Top city by revenue: Singapore 481,462.25 (530 orders), Vienna 463,970.29, Melbourne 461,934.71. Lowest: Milan 399,156.15 (455), Helsinki 401,507.50.
B2. How much revenue has no city? 424,129.10 (471 orders; 3.9%). Naive ranking without a NULL-handling would treat it as a city; clean top-city answer unchanged.
B3. Cities with orders: 24 named (25 groups incl. NULL).
### Persona C - operations ("I know priority levels")
C1. Share of orders by priority: Standard 33.3%, Express 25%, Priority 25%, Overnight 16.7% (4,000/3,000/3,000/2,000).
C2. Revenue by priority: Standard 3,636,224.13; Express 2,733,325.23; Priority 2,710,882.87; Overnight 1,808,541.04. AOV nearly identical (Express 911.11, Standard 909.06, Overnight 904.27, Priority 903.63).
C3. Average units per order: 12.60 (151,247 units); average per priority Express 12.33, Overnight 12.66, Priority 12.83, Standard 12.61.

## 5. What a good BI tool should tell this user automatically
- KPIs: revenue, orders, AOV, units; monthly trend line; revenue by city (top 10), channel and priority.
- Charts: line by month, bar by city, donut/bar by channel & priority, histogram of amount.
- Warnings: order_date and month are text (parse as date); city has 471 nulls (3.9%); month duplicates order_date; order_id is an identifier; 24 cities too many for a pie; differences between channels/priorities are tiny (<2% AOV) - insight should say "no meaningful difference"; the data covers exactly 2025 so no YoY.
