# olist database profile (Brazilian e-commerce marketplace, public schema, 9 tables)

All numbers below were computed with read-only SQL via `docker exec datalytics_db psql -U datalytics -d olist`.

## 1. Tables, keys, joins
| Table | Rows | PK | FKs | Grain |
|---|---|---|---|---|
| orders | 99,441 | order_id | customer_id -> customers | one row per order |
| customers | 99,441 | customer_id | - | one row per (customer_id) = one per ORDER; person is `customer_unique_id` (96,096 distinct) |
| order_items | 112,650 | (order_id, order_item_id) | order_id, product_id, seller_id | one row per product line within an order (max 21 lines) |
| order_payments | 103,886 | (order_id, payment_sequential) | order_id | one row per payment instalment/method of an order |
| order_reviews | 100,000 | none declared (review_id not unique) | order_id (declared) | one row per review submission |
| products | 32,951 | product_id | - | one per product |
| sellers | 3,095 | seller_id | - | one per seller |
| product_category_name_translation | 71 | product_category_name | - | Portuguese -> English category |
| geolocation | 1,000,163 | none | none (zip prefix joins customers/sellers, not unique) | lat/lng sample points per zip prefix |

Joins: orders.customer_id=customers.customer_id; order_items/order_payments/order_reviews.order_id=orders.order_id; order_items.product_id=products.product_id; order_items.seller_id=sellers.seller_id; products.product_category_name=translation.product_category_name; customers/sellers zip_code_prefix = geolocation_zip_code_prefix (text; many rows per prefix).

Columns (type): 
- orders: order_id text, customer_id text, order_status text, order_purchase_timestamp / order_approved_at / order_delivered_carrier_date / order_delivered_customer_date / order_estimated_delivery_date (timestamp)
- customers: customer_id, customer_unique_id, customer_zip_code_prefix (text), customer_city, customer_state
- order_items: order_id, order_item_id int, product_id, seller_id, shipping_limit_date ts, price numeric, freight_value numeric
- order_payments: order_id, payment_sequential int, payment_type text, payment_installments int, payment_value numeric
- order_reviews: review_id, order_id, review_score int, review_comment_title, review_comment_message, review_creation_date ts, review_answer_timestamp ts
- products: product_id, product_category_name, product_name_lenght int (sic), product_description_lenght int (sic), product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm (ints)
- sellers: seller_id, seller_zip_code_prefix, seller_city, seller_state
- geolocation: geolocation_zip_code_prefix text, geolocation_lat/lng double, geolocation_city, geolocation_state

## 2. Date ranges
- order_purchase_timestamp: 2016-09-04 21:15 .. 2018-10-17 17:30. Orders per year: 2016=329, 2017=45,101, 2018=54,011. Tiny/sparse edges: 2016-09=4, 2016-10=324, 2016-11=0 (gap), 2016-12=1; 2018-09=16, 2018-10=4 (data effectively ends Aug 2018 -> partial months).
- order_approved_at 2016-09-15 .. 2018-09-03; carrier date 2016-10-08 .. 2018-09-11; delivered_customer 2016-10-11 .. 2018-10-17; estimated_delivery 2016-09-30 .. 2018-11-12.
- shipping_limit_date: 2016-09-19 .. **2020-04-09** (4 rows after 2018-12-31 = impossible/outlier).
- review_creation_date 2016-10-02 .. 2018-08-31; review_answer_timestamp 2016-10-07 .. 2018-10-29.

## 3. Measures and traps
Order status counts: delivered 96,478; shipped 1,107; canceled 625; unavailable 609; invoiced 314; processing 301; created 5; approved 2.

Correct measures
- Item revenue (GMV excl. freight) = SUM(order_items.price) = 13,591,643.70. Freight = SUM(freight_value) = 2,251,909.54 (16.57% of price). Price+freight = 15,843,553.24.
- Payments total = SUM(order_payments.payment_value) = 16,008,872.12 (differs from price+freight; see mismatch below).
- Orders = COUNT(DISTINCT order_id) from orders = 99,441. Customers (people) = COUNT(DISTINCT customer_unique_id) = 96,096 (NOT 99,441).
- Late delivery rate = delivered_customer > estimated among orders with a delivered_customer_date (96,476): 7,827 late = 8.11%.
- Delivery days = delivered_customer - purchase: avg 12.56, median 10.22, max 210.

Traps and counts
1. FAN-OUT order_items x order_payments: joining them on order_id gives SUM(payment_value)=20,308,134.71 (true 16,008,872.12) and SUM(price)=14,209,115.34 (true 13,591,643.70). 2,961 orders have >1 payment row; 9,803 orders have >1 item. Aggregate each table to order level before joining.
2. Fan-out with reviews: 555 orders have >1 review; review_id duplicated on 827 rows (99,173 distinct review_id for 100,000 rows). Joining reviews inflates counts (e.g. late+delivered join gives 7,866 late rows vs true 7,827 orders).
3. customer_id is a per-order key; repeat-buyer analysis needs customer_unique_id (2,997 people with >1 order = 3.12%, max 17 orders). customer_id has no duplicates.
4. IDs are hex strings (not numeric). zip_code_prefix is text (keep leading zeros) - do not treat as number/measure.
5. Orders without items: 775 (603 unavailable, 164 canceled, 5 created, 2 invoiced, 1 shipped); orders without payments: 1; orders without reviews: 0. order_items has 549 lines on canceled/unavailable orders; price excluding canceled/unavailable = 13,494,400.74.
6. Delivered-status inconsistencies: 8 'delivered' orders with no delivered date; 6 non-delivered (canceled) orders with a delivered date; 14 delivered orders lack approved_at; 166 orders with carrier date before purchase; 23 with customer date before carrier date.
7. Payments: payment_type 'not_defined' 3 rows (value 0); 9 rows payment_value=0; payment_installments=0 on 2 rows (invalid); installments max 24. Order total payments vs price+freight mismatch >0.01 in 303 of 98,665 orders (249 by >1.00) - vouchers/instalment interest.
8. Zero freight on 383 items; price max 6,735.00 (846 items >=1000; avg price 120.65) -> heavy right-skew, use median/percentiles.
9. Products: 610 products without category (32,341 with); 13 products' categories (pc_gamer, portateis_cozinha_e_preparadores_de_alimentos) have no translation; 73 distinct categories; 2 products without weight, 4 with weight 0; weight max 40,425 g. Column names have typo "lenght".
10. Geolocation: 1,000,163 rows but only 19,015 zip prefixes; 280,009 fully duplicate (prefix,lat,lng) rows; 42 points outside Brazil bounds (lat range -36.6..45.07, lng -101.5..121.1); city names inconsistent accents (8,011 raw vs 5,969 normalized distinct). Never join to it without deduping/averaging per prefix or you fan-out.
11. Cardinality: customer_state 27, customer_city 4,119, customer zips 14,994; seller_state 23, seller_city 611; payment_type 5; review_score 1-5 (1:11,858, 2:3,235, 3:8,287, 4:19,200, 5:57,420); review_comment_title non-null 11,715, message non-null 41,755 (58% blank).
12. SP concentration: customers SP 41,746 (42%), RJ 12,852, MG 11,635; seller revenue SP 8.75M of 13.59M.

## 4. Personas and true answers

### Persona A - Marketplace executive ("knows it's an online shop's sales data")
A1. What is total sales revenue and how did it grow by year?
```sql
select extract(year from o.order_purchase_timestamp)::int y, round(sum(price),2) item_rev, round(sum(price+freight_value),2) gmv
from order_items i join orders o using(order_id) group by 1 order by 1;
```
2016: 49,785.92 / 57,183.21; 2017: 6,155,806.98 / 7,142,672.43; 2018: 7,386,050.80 / 8,643,697.60. Total item revenue 13,591,643.70 (2018 is Jan-Aug only, +20% vs 2017 despite fewer months; 2016 is Sep-Dec stub).
A2. Which month sold the most?  Peak by orders-with-items: 2017-11 (7,451 orders, 1,010,271.37 revenue). Next 2018-01 (7,220), 2018-03 (7,188 orders; 983,213.44).
A3. What is the average order value?
Clean: SUM(price)/COUNT(DISTINCT order_id) from items = 137.75 (excl. freight); with freight 160.58; payments per paid order = 160.99. Naive trap: divide by all 99,441 orders (includes 775 without items) or join payments (inflated, see trap 1).

### Persona B - Logistics / operations manager ("knows it's orders and deliveries")
B1. What share of orders arrive late? Clean 8.11% (7,827 of 96,476 with delivery date). Same number by status='delivered' only = 8.11%. Naive via reviews join = 7,866 rows.
```sql
select round(100.0*sum((order_delivered_customer_date>order_estimated_delivery_date)::int)/count(*),2) from orders where order_delivered_customer_date is not null;
```
B2. Which states have the worst late rate / delivery time (states with >=100 delivered)?  Worst: AL 23.93% late (397 orders, avg 24.5 days), MA 19.67% (717, 21.6), PI 15.97%, CE 15.32%. Best: RO 2.88% (but 19.4 days), AM 4.14% (26.4 days), PR 5.00% (12.0 days).
B3. Average days to deliver? avg 12.56, median 10.22, max 210 (long tail -> use median).

### Persona C - Customer-care / marketing lead ("knows it's customer feedback and payments")
C1. Average review score and % unhappy? avg 4.071 (all 100,000 rows; same 4.071 using latest review per order, 99,441 orders); 11.86% scored 1; 76.62% scored 4-5.
C2. Does lateness hurt satisfaction?  Delivered on time: 4.28 avg (89,147 review rows); late: 2.55 (7,866 rows). Canceled orders avg 1.81.
C3. How many customers come back / how do they pay? Distinct people 96,096 (not 99,441); repeat buyers 2,997 = 3.12%. Payment mix by orders: credit_card 76.94% (76,505), boleto 19.90% (19,784), voucher 3.89%, debit_card 1.54%, not_defined 3 orders; 2,246 orders use >1 payment type. Avg credit-card installments 3.51 (all payment rows incl. boleto/voucher 2.85).
Extra: top categories by item revenue (English): health_beauty 1,258,681.34; watches_gifts 1,205,005.68; bed_bath_table 1,036,988.68 (most items 11,115); sports_leisure 988,048.97; computers_accessories 911,954.32. Top seller revenue 229,472.63.

## 5. What a good BI tool should do automatically
- KPIs: revenue (price) 13.59M, orders 99,441, unique customers 96,096, AOV ~137.75 (price) / ~160 incl. freight, freight share 16.6%, late rate 8.1%, avg review 4.07, repeat rate 3.1%.
- Charts: monthly revenue/orders line (flag partial first/last months: 2016 stub, gap Nov 2016, 2018-09/10 almost empty); category bar top-N (translate to English); Brazil state map/bar for customers and sellers; review score distribution; payment-type donut; delivery days histogram (log/ median) ; late % by state.
- Warnings: payments and items are 1-to-many -> never sum across a join (state inflation numbers); customer_id is per-order, use customer_unique_id; IDs and zip prefixes are identifiers not measures; geolocation has 280k duplicate rows, 42 points outside Brazil; shipping_limit_date reaching 2020 (4 rows); status/date inconsistencies (8 delivered w/o date, 6 non-delivered with date, 166 carrier-before-purchase); canceled/unavailable orders carry revenue (549 lines) - ask whether to exclude; heavy price skew (max 6,735 vs median 74.99, mean 120.65); 610 products with no category and 13 with no translation; review text mostly empty.
