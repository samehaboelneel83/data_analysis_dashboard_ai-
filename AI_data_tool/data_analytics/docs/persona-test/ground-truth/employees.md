# employees database profile (classic HR sample: 300k employees, salary/title/department history, public schema)

All numbers computed with read-only SQL via `docker exec datalytics_db psql -U datalytics -d employees`. The data is a snapshot "as of" about 2002-08-01 (latest real date in any table); open-ended rows use the sentinel to_date = 9999-01-01.

## 1. Tables, keys, joins
| Object | Type | Rows | Key | Grain |
|---|---|---|---|---|
| employees | table | 300,024 | PK emp_no (10001..499999, not contiguous) | one person |
| departments | table | 9 | PK dept_no (char, d001..d009); UNIQUE dept_name | one department |
| dept_emp | table | 331,603 | PK (emp_no, dept_no); FKs to employees, departments | one employee-in-department assignment with from/to dates |
| dept_manager | table | 24 | PK (emp_no, dept_no) | one manager stint |
| titles | table | 443,308 | PK (emp_no, title, from_date) | one job-title period |
| salaries | table | 2,844,047 | PK (emp_no, from_date) | one salary period (history, 1 to 18 rows/employee, avg 9.48) |
| current_dept_emp | view | 300,024 | - | latest dept assignment per employee (one row each, includes leavers) |
| dept_emp_latest_date | view | 300,024 | - | helper: per emp max(from_date), max(to_date) |

Columns: employees(emp_no int, birth_date date, first_name, last_name varchar, gender char M/F, hire_date date); departments(dept_no char, dept_name varchar); dept_emp / dept_manager (emp_no, dept_no, from_date, to_date); titles(emp_no, title, from_date, to_date); salaries(emp_no, salary int, from_date, to_date).
Joins: everything joins on emp_no; dept_emp/dept_manager to departments on dept_no. Cardinality: employees 1 -> many salaries, titles, dept_emp. Every employee has at least one salary, title and department row.

## 2. Date ranges
- birth_date 1952-02-01 .. 1965-02-01 (ages 37-50 as of 2002-08-01). hire_date 1985-01-01 .. 2000-01-28 (hires by year: 1985 35,316; 1986 36,150; 1987 33,501; 1988 31,436; 1989 28,394; 1990 25,610; 1991 22,568; 1992 20,402; 1993 17,772; 1994 14,835; 1995 12,115; 1996 9,574; 1997 6,669; 1998 4,155; 1999 1,514; 2000 13).
- salaries from_date 1985-01-01 .. 2002-08-01; to_date 1985-03-01 .. 9999-01-01 (real max closed date 2002-08-01). dept_emp / titles same ranges (from 1985-01-01..2002-08-01). dept_manager from 1985-01-01 .. 1996-08-30; to 1988-09-09 .. 9999-01-01.
- salary range 38,623 .. 158,220 (36 salary rows > 150,000; none below 38,000).

## 3. Measures and traps
Correct measures
- Current headcount = employees with an open row (to_date=9999-01-01) = 240,124. Total ever employed = 300,024. Left the company = 59,900 (19.97%). Gender: M 179,973 (60.0%), F 120,051 (40.0%) overall.
- Current salary = the salaries row with to_date='9999-01-01': avg 72,012.24, median 69,805, min 38,623, max 158,220 (240,124 rows).
- Average salary across ALL salary rows (naive) = 63,810.74 over 2,844,047 rows - a mixture of years, wrong for "what do we pay".

Traps and counts
1. SENTINEL DATE 9999-01-01 = "still active". Never plot/average it as a real date; 240,124 open rows in each of salaries, titles, dept_emp (so each active employee has exactly 1 open row in each; 0 employees have more than one open salary or open department row).
2. HISTORY TABLES: salaries (2.84M rows) and titles (443,308 rows) hold every past period. Joining or averaging without the to_date='9999-01-01' filter gives wrong headcounts and salaries. Leavers (59,900) have NO open row in any history table, so "current" filters drop them - and their last salary row has a closed to_date.
3. FAN-OUT: dept_emp has 331,603 rows for 300,024 people; 31,579 employees worked in >1 department. Naive department headcount (count rows) sums to 331,603 vs 300,024 real people; Development naive 85,707 vs current 61,386. Same with titles (443,308 rows).
4. Naive department average salary (all salary rows x all dept rows) differs hugely from current: e.g. Sales naive 80,668 vs current 88,853; Human Resources 55,575 vs 63,922.
5. Salary periods: 178 rows have from_date = to_date (zero-length) and 5,262 last less than 30 days; period gaps/overlaps: 0 (each from_date equals the previous to_date). to_date<from_date: 0 in all tables.
6. Manager data: dept_manager has 24 stints, 9 current (one per department); titles has 24 'Manager' rows (9 current) = consistent. Title names include a 'Technique Leader' (15,159 rows, 15,157 people) and 'Staff' vs 'Senior Staff', 'Engineer' vs 'Senior Engineer' (title progression, not separate jobs).
7. Duplicates: 6 employees share first+last name+birth date with another employee (distinct emp_no) - not true duplicates by key; emp_no is an identifier, not a measure (looks numeric, 10001..499999).
8. Cardinality: gender 2, departments 9, titles 7, first_name 1,275 distinct, last_name 1,637 distinct; birth_date has only ~ 13 years, hire dates stop at 2000 (data has no hires after 2000-01-28, while changes continue to 2002-08-01).
9. Anonymized-looking synthetic data: very narrow ages (37-50), salary averages almost equal by gender; no nulls in any column (all joins complete: 0 employees without salary, title, or department).
10. Ages: compute as of 2002-08-01, not current_date (today's date would give ages 61-74 and 'tenure' ~ 25 years for everyone).

## 4. Personas and true answers

### Persona A - HR manager ("knows it's employee data")
A1. How many people work here now and how many have left?
```sql
select count(*) from (select emp_no from dept_emp group by 1 having max(to_date)='9999-01-01') x;  -- 240,124
```
Clean: 240,124 current of 300,024 ever; 59,900 left (19.97%). Naive: COUNT(*) of employees = 300,024 (includes leavers); COUNT(*) of dept_emp = 331,603 (fan-out).
A2. Headcount by department (current)? Development 61,386; Production 53,304; Sales 37,701; Customer Service 17,569; Research 15,441; Marketing 14,842; Quality Management 14,546; Human Resources 12,898; Finance 12,437 (sum 240,124). Naive (all dept_emp rows): Development 85,707; Production 73,485; Sales 52,245; Customer Service 23,580; Research 21,126; Marketing 20,211; Quality Mgmt 20,117; HR 17,786; Finance 17,346 (sum 331,603).
```sql
select d.dept_name,count(*) from dept_emp de join departments d using(dept_no) where de.to_date='9999-01-01' group by 1 order by 2 desc;
```
A3. How many people left each year? By last departure year: 1985 89, 1986 374, 1987 668, 1988 905, 1989 1,288, 1990 1,594, 1991 1,883, 1992 2,317, 1993 2,742, 1994 3,135, 1995 3,739, 1996 4,330, 1997 5,069, 1998 5,941, 1999 6,964, 2000 7,610 (peak), 2001 7,241, 2002 4,011 (partial year, to 2002-08-01).
```sql
select extract(year from last_to)::int y, count(*) from (select emp_no,max(to_date) last_to from dept_emp group by 1 having max(to_date)<>'9999-01-01') x group by 1 order by 1;
```

### Persona B - Finance / compensation analyst ("knows there are salaries")
B1. What is the average salary today? Clean 72,012.24 (240,124 current salary rows; median 69,805; min 38,623; max 158,220). Naive (all rows) 63,810.74.
B2. Which department pays the most? Current avg salary: Sales 88,853; Marketing 80,059; Finance 78,560; Research 67,913; Production 67,843; Development 67,658; Customer Service 67,285; Quality Management 65,442; Human Resources 63,922. Naive (all history x all dept rows): Sales 80,668; Marketing 71,913; Finance 70,489; Research 59,665; Production 59,605; Development 59,479; Customer Service 58,770; QM 57,251; HR 55,575.
```sql
select d.dept_name, round(avg(s.salary)) from dept_emp de join departments d using(dept_no) join salaries s on s.emp_no=de.emp_no and s.to_date='9999-01-01' where de.to_date='9999-01-01' group by 1 order by 2 desc;
```
B3. How much have salaries grown per person over their career? Avg first salary 52,983 -> avg current salary 72,012 for the 240,124 current staff: +35.9% (first row by from_date vs open row).  Average of 9.48 salary rows per employee (max 18).

### Persona C - Executive / diversity officer ("knows it's a company staff list")
C1. Is there a gender pay gap? Current avg salary: M 72,045 (144,114 people) vs F 71,964 (96,010) - gap 81 (0.11%). Naive over all history: M 63,838 vs F 63,770. Gender split of current staff: M 60.0% / F 40.0%.
```sql
select gender,count(*),round(avg(s.salary)) from employees e join salaries s using(emp_no) where s.to_date='9999-01-01' group by 1;
```
C2. Which job titles are most common now and pay most? Current: Senior Engineer 85,939 (avg 70,823); Senior Staff 82,024 (80,706); Engineer 30,983 (59,603); Staff 25,526 (67,331); Technique Leader 12,055 (67,507); Assistant Engineer 3,588 (57,318); Manager 9 (77,724). Highest avg: Senior Staff 80,706 (Manager 77,724 only 9 people).
C3. Who manages each department today? Customer Service: Yuchang Weedman (since 1996-01-03); Development: Leon DasSarma (1992-04-25); Finance: Isamu Legleitner (1989-12-17); Human Resources: Karsten Sigstam (1992-03-21); Marketing: Vishwani Minakawa (1991-10-01); Production: Oscar Ghazalie (1996-08-30); Quality Management: Dung Pesch (1994-06-28); Research: Hilary Kambil (1991-04-08); Sales: Hauke Zhang (1991-03-07).
```sql
select d.dept_name, e.first_name||' '||e.last_name from dept_manager m join employees e using(emp_no) join departments d using(dept_no) where m.to_date='9999-01-01';
```

## 5. What a good BI tool should do automatically
- Detect that to_date=9999-01-01 is an "open/current" sentinel, offer a "current only" filter and show headcount 240,124 (not 300,024 or 331,603); do not treat it as a date axis value.
- Detect history tables (salaries, titles, dept_emp) and say that avg/sum across all rows double counts people; default the salary KPI to the current row (avg 72,012, median 69,805).
- KPIs: current headcount 240,124; leavers 59,900 (19.97% attrition); avg/median current salary; gender mix 60/40; avg tenure; salary growth +35.9% vs first salary; headcount by department/title.
- Charts: current headcount by department (bar), avg salary by department (bar, sorted: Sales highest), hires by year line (note hiring ends 2000), leavers by year (peak 2000), salary histogram (skew, min 38.6k max 158k), gender by department/title stacked.
- Warnings: department join fan-out (31,579 people in >1 dept); salary history volume 2.84M rows (aggregate in DB); 178 zero-length salary periods; emp_no is an ID not a measure; dates stop 2002 so "today"/age/tenure calculations should use 2002-08-01 as as-of date; only 9 departments / 2 genders / 7 titles = low-cardinality categoricals; Manager title has only 9 current people.
