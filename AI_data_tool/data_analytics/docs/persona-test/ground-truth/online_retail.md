# online_retail profile (all numbers computed via read-only SQL)

## 1. Tables
| table | rows | PK | FKs |
|---|---|---|---|
| countries | 43 | country_id | country_name UNIQUE |
| customers | 5,942 | customer_id (int, 12346..18287) | country_id -> countries |
| products | 5,131 | stock_code (text) | - |
| invoices | 53,628 | invoice_no (text, 6-7 chars) | customer_id -> customers (nullable), country_id -> countries |
| invoice_lines | 1,067,371 | line_id (bigint) | invoice_no -> invoices, stock_code -> products |

Columns: countries(country_id int, country_name text); customers(customer_id int, country_id int, first_order_date date); products(stock_code text, description text); invoices(invoice_no text, invoice_date timestamp, customer_id int, country_id int, is_cancellation bool); invoice_lines(line_id bigint, invoice_no text, stock_code text, quantity int, unit_price numeric, line_total numeric).

Joins: invoice_lines -> invoices (invoice_no) -> customers (customer_id) / countries (country_id); invoice_lines -> products (stock_code). Star-like: invoice_lines is the fact table. No orphan rows (every invoice has lines, every product is used).

## 2. Grain, meaning, date ranges
- invoice_lines: one product line on one invoice (the fact table). line_total = quantity*unit_price exactly (0 mismatches).
- invoices: one sales invoice or cancellation invoice (header). invoice_date 2009-12-01 07:45 to 2011-12-09 12:50 (25 months; Dec 2009 full month, Dec 2011 only through the 9th = partial). Cancellation invoices have invoice_no starting with "C" (8,292 = is_cancellation true, exactly).
- customers: registered customers; first_order_date 2009-12-01..2011-12-09 (consistent with invoices, 0 mismatches). Customers by first-order year: 2009=1,045; 2010=3,368; 2011=1,529.
- products: catalog (stock_code, description). Prices are NOT in products; they are per line.
- countries: 43 lookup rows (incl. "Unspecified", "European Community", "Channel Islands"; EIRE = Ireland; RSA = South Africa).
- Customer country = invoice country except 40 invoices (14 customers have >1 country across invoices).

## 3. Measures and traps
- Naive SUM(line_total) over all lines = 19,287,250.55 (mixes sales, returns, fees).
- Gross sales (recommended) = lines on non-cancellation invoices with quantity>0 and unit_price>0: 20,972,594.55. Excluding non-product codes as well (POST, DOT, M, C2, C3, D, S, B, ADJUST, ADJUST2, AMAZONFEE, BANK CHARGES, CRUK, PADS, TEST001, TEST002, SP1002): 20,111,922.42 (non-product positive lines = 860,672.13).
- Returns/cancellations value (C invoices) = -1,526,667.86 (19,494 lines, 19,493 negative qty + 1 positive qty line: C496350, code M, qty 1, 373.57). Simple SUM over all = 19,287,250.55 (also includes the 3,457 zero-price negative adjustment lines and fee lines, B = -147,614.08, AMAZONFEE = -260,763.58).
- Sum of non-cancel invoices only = 20,813,918.41 (still contains 3,457 negative-qty zero-price lines and 5 negative-price "B" bad-debt lines).
- Return rate: cancellation value / gross sales = 7.28%; 15.46% of invoice numbers are cancellations (8,292 of 53,628). Excluding non-product codes 3.61%. (Cancellations are inconsistently matched to original invoices, so rate is by value, not per-order.)
- Data-quality counts:
  - quantity<0: 22,950 lines (19,493 on C invoices; 3,457 on normal invoices, ALL with unit_price=0 = stock write-offs/adjustments). quantity=0: 0.
  - unit_price=0: 6,202 lines (2,745 with positive qty = free/samples; 3,457 negative-qty adjustments). unit_price<0: 5 (all stock_code B, "Adjust bad debt").
  - Extreme/outlier lines: |qty|>=10,000: 15 lines. Biggest: invoice 581483 qty 80,995 @2.08 = 168,469.60 (code 23843) cancelled the same day by C581484; invoice 541431 qty 74,215 @1.04 (code 23166) cancelled by C541433. Unit price max 38,970 (C556445, manual "M"). Percentiles of positive-qty/price lines: qty p50=3, p90=24, p99=100, p99.9=~486; price p50=2.10, p90=7.95, p99=18, p99.9=~159.
  - Non-product stock codes: 61 products with non-5-digit codes (POST postage 2,122 lines/112,341; DOT dotcom postage 1,446/322,647; M manual -82,781; D discount; AMAZONFEE; BANK CHARGES; ADJUST; TEST001/2; etc.). 353 products have NULL description; 60 have non-uppercase descriptions (mixed text like "ebay", "Adjustment by john...").
  - customer_id NULL on 8,752 invoices (16.3%); 243,007 lines; 15.40% of clean gross sales (3,229,165.39) is anonymous/guest. Customer-level analyses must exclude them (or flag).
  - Duplicates: 32,911 groups of identical (invoice, stock_code, qty, price) lines = 34,339 extra rows (repeat scan lines; not removed; may be legitimate).
  - Saturday: only 32 invoices ever (no trading); Sunday 4,839; invoice times 06:00-20:xx.
- Code columns that look numeric: customer_id (ID, never sum/average), invoice_no (text with "C" prefix), stock_code (mostly 5-digit, with letter suffixes like 85123A, so text), country_id, line_id.
- Cardinalities: countries 43; customers 5,942 (5,881 with at least one non-cancel invoice); products 5,131 (4,745 sold at positive price on normal invoices, 4,730 excluding non-product codes); invoices 53,628 (45,336 non-cancel).
- UK = 85.21% of gross sales (customers: UK 5,410 of 5,942).
- Seasonality (gross clean monthly revenue): peak Nov (2010-11 1,470,272; 2011-11 1,509,496), Oct-Dec strongest, Feb/Apr weakest. 2011-12 is partial (9 days).

## 4. Personas and true answers
### Persona A: Marketing analyst ("it's an online shop, I know nothing else")
Gross clean sales predicate G: `not i.is_cancellation and l.quantity>0 and l.unit_price>0`.

A1. Which countries bring the most revenue? 
```sql
select c.country_name, round(sum(l.line_total),2) naive_net, round(sum(l.line_total) filter(where not i.is_cancellation and l.quantity>0 and l.unit_price>0),2) gross_clean
from invoice_lines l join invoices i using(invoice_no) join countries c on c.country_id=i.country_id group by 1 order by 2 desc limit 5;
```
Result (naive net / clean gross): UK 16,382,583.88 / 17,870,977.76; EIRE 615,519.55 / 664,431.78; Netherlands 548,524.95 / 554,232.34; Germany 417,988.56 / 431,262.46; France 328,191.80 / 356,944.60. Ranking identical; UK = 85.21% of gross. 

A2. How many customers do we have and how many are repeat buyers?
```sql
select count(distinct customer_id) from invoices where not is_cancellation;  -- 5,881
select count(*) from (select customer_id from invoices where not is_cancellation and customer_id is not null group by 1 having count(*)>1) x; -- 4,255
```
5,881 active customers (5,942 in customers table; naive count of customers table overstates by 61 who only ever cancelled). 4,255 (72.4%) bought on >1 invoice; 1,626 only once. Naive trap: counting invoices w/o customer ids (8,361 non-cancel invoices have no customer).

A3. When do we sell most (best month, seasonality)? 
```sql
select to_char(invoice_date,'YYYY-MM'), round(sum(line_total),2) from invoice_lines l join invoices i using(invoice_no) where not is_cancellation and quantity>0 and unit_price>0 group by 1 order by 2 desc limit 3;
```
2011-11 1,509,496.33; 2010-11 1,470,272.48; 2010-12 1,262,598.79. Day-of-week by non-cancel invoices: Mon 7,254, Tue 8,505, Wed 8,162, Thu 9,313, Fri 7,231, Sat 32, Sun 4,839. Peak hour of sales 12:00 (2.91M), 10-15h strong.

### Persona B: Merchandising / operations manager ("I know there are products and returns")
B1. Top 10 products by revenue (excluding non-product codes)?
```sql
select p.stock_code,p.description,sum(quantity) units,round(sum(line_total),2) rev
from invoice_lines l join invoices i using(invoice_no) join products p using(stock_code)
where not is_cancellation and quantity>0 and unit_price>0 and stock_code not in ('POST','DOT','M','C2','C3','D','S','B','ADJUST','ADJUST2','AMAZONFEE','BANK CHARGES','CRUK','PADS','TEST001','TEST002','SP1002') group by 1,2 order by 4 desc limit 10;
```
1 22423 REGENCY CAKESTAND 3 TIER 344,563.25 (27,577 units); 2 85123A WHITE HANGING HEART T-LIGHT HOLDER 267,102.06 (96,744); 3 85099B JUMBO BAG RED RETROSPOT 185,566.47; 4 23843 PAPER CRAFT, LITTLE BIRDIE 168,469.60; 5 47566 PARTY BUNTING 149,187.05; 6 84879 ASSORTED COLOUR BIRD ORNAMENT 132,187.92; 7 22086 PAPER CHAIN KIT 50'S CHRISTMAS 123,141.54; 8 79321 CHILLI LIGHTS 85,489.91; 9 23166 MEDIUM CERAMIC TOP STORAGE JAR 81,700.92; 10 22197 SMALL POPCORN HOLDER 80,920.64.
Traps: (i) naive net (all lines incl. fees/returns) top list puts DOT "DOTCOM POSTAGE" (322,647.47) #2 and shows 22423 at 327,813.65; (ii) 23843 (#4) and 23166 (#9) are single 80,995 / 74,215-unit orders that were fully cancelled the next minutes, so their NET revenue is ~0 - a real top-10 on net sales would drop them. Top by units: 84077 WORLD WAR 2 GLIDERS 110,138; 85099B 98,768; 85123A 96,744.

B2. What share of sales is returned?
```sql
select round(100*-sum(line_total) filter(where is_cancellation)/sum(line_total) filter(where not is_cancellation and quantity>0 and unit_price>0),2) from invoice_lines l join invoices i using(invoice_no);
```
7.28% by value (1,526,667.86 returned of 20,972,594.55); 3.61% excluding non-product codes (computed over product codes only, return value divided by product gross sales). Cancellation invoices: 15.46% of invoice numbers. Top returned products: 23843 (80,995 units, 168,469.60) and 23166 (74,494 units, 77,479.64), then 22423 (1,468 units, 16,749.60). 

B3. How many distinct products do we actually sell? 4,745 with positive-price non-cancel sales (4,730 real products), vs 5,131 in catalog. 361 invoice lines point to products with no description.

### Persona C: Finance / CEO ("knows it's a company with sales")
C1. What was revenue in 2010 vs 2011?
```sql
select extract(year from invoice_date), round(sum(line_total) filter(where not is_cancellation and quantity>0 and unit_price>0),2) gross, round(sum(line_total),2) net_all from invoice_lines l join invoices i using(invoice_no) group by 1 order by 1;
```
2009 (Dec only) 825,685.76 / 799,847.11; 2010 10,303,952.39 / 9,488,594.53; 2011 (through Dec 9) 9,842,956.40 / 8,998,808.91. Like-for-like (2011-01-01..2011-12-09 vs full 2010): -4.47% gross (10,303,952.39 -> 9,842,956.40). Comparing 2011 with 2010 without noting that 2011 lacks 3 weeks of Dec is a trap: 2010-12 alone is 1,262,598.79. Equal 12-month windows (2009-12-01..2010-12-09 vs 2010-12-10..2011-12-09): 10,744,744.66 vs 10,227,849.89 (-4.8%).
C2. Average order value?
Gross per non-cancel invoice (mean) 523.31; median 304.31 (n=40,077 clean invoices); naive mean over all invoices incl. cancel/zero = 359.65; sum(line_total)/distinct non-cancel invoices = 459.10 (diluted by negative lines). Skewed by wholesalers, so median is the honest typical order.
C3. How concentrated is revenue by customer?
Top 10 customers (identified only) = 2,826,476.26 = 15.93% of identified gross / 13.48% of all gross. #1 customer 18102 608,821.65 (145 invoices); #2 14646 528,602.52; #3 14156 313,946.37; #4 14911 295,972.63 (398 invoices); #5 17450 246,973.09. Top 10% of customers (588) = 63.89% of identified gross (a long-tail / Pareto effect). Customer 16446: 168,472.50 in just 2 invoices (the 80,995-unit ghost order, later cancelled).

## 5. What a good BI tool should tell this user automatically
- KPIs: gross sales 20.97M (or net), invoices 45,336, customers 5,881, AOV median 304 / mean 523, return rate 7.3%, UK share 85%, repeat rate 72%.
- Charts: monthly revenue line (show strong Q4 seasonality and partial last month flag), top-N products bar, revenue by country (UK dominates: use log scale or exclude UK view), customer revenue Pareto, hour/day heatmap.
- Warnings it must raise: ~2.1% of lines are negative-quantity (returns/adjustments) and invoice numbers beginning with "C" are cancellations, so raw SUM understates sales; non-product codes (POST, DOT, M, AMAZONFEE, BANK CHARGES...) in the product dimension; 16.3% of invoices have no customer_id; 6,202 zero-price lines and 5 negative prices; 15 lines with |qty|>=10,000 (80,995 qty order cancelled) and price up to 38,970; duplicate-looking lines (34,339 extra rows); last month (Dec 2011) is partial; customer_id and stock_code are identifiers, not measures; Saturday has almost no trading.
