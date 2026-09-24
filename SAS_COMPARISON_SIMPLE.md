# Datalytics vs SAS Visual Analytics — the short version

For someone deciding between the two, or explaining the choice to someone
else. The long, evidence-by-evidence version is
[SAS_COMPARISON.md](SAS_COMPARISON.md); every claim here comes from it.

---

## One paragraph

They are closer than you would expect. Datalytics matches SAS Visual Analytics
on the everyday work — preparing data, building charts, clicking one chart to
filter the others. It is **ahead** on statistics, on asking questions in plain
language, and on controlling who sees which rows and columns. SAS is **ahead**
on maps, on getting a dashboard to people who are offline or on a phone, and on
running at very large scale. Which of those matters more depends entirely on
what your people actually do.

---

## Where each side wins

### Datalytics is ahead

| | Why it matters |
|---|---|
| **Ask questions in plain language** | Type *"total revenue by region"* and get the answer, the rows, and a chart. SAS Visual Analytics has no equivalent — it generates prose *about* a result, but you cannot ask it a question. |
| **Classical statistics** | t-tests, ANOVA, chi-square, regression, survival analysis. The words "t-test" and "ANOVA" do not appear once in either SAS VA course. SAS offers automatic analyses instead, which need no statistical knowledge — a fair choice for its audience, but a different one. |
| **Security on the data itself** | Rules about which rows and which columns a person may see, applied in one place, so dashboards, chat, exports and shared links all obey them. |
| **Built-in AI that designs for you** | Describe your job and get whole dashboards proposed, with every chart run before it is offered to you. |

### SAS is ahead

| | Why it matters |
|---|---|
| **Maps** | Sub-national regions, map tiles, drive-time areas, routing, demographics. Datalytics does maps, but you must supply the geography yourself. This is SAS's clearest lead. |
| **Getting it to people** | Offline packages, native mobile apps, Microsoft 365 integration. Datalytics shares by link, embed, PDF and scheduled email. |
| **Scale** | SAS's in-memory engine is built for very large data and proven at it. Datalytics has not been tested at that size. |

### Level

Data preparation · charts and visuals (67 types vs about 50) · click-to-filter
interactivity · automatic analysis that picks a model for you.

One thing SAS still has in this group: a builder for inventing a *new kind* of
chart, rather than configuring an existing one.

---

## The honest caveat

**The two sides were measured with different instruments.**

The SAS side is read from its official courses — an authoritative list of what
SAS offers, written by the people who built it. A course contains no defects,
because courses never do.

The Datalytics side was measured by *using the product*, which is a harsher
test. That is why the long version has been corrected fifteen times — and
fourteen of those corrections found capability that was already built and had
been written off. The remaining one found a feature that worked everywhere
except on nine map widgets.

So read this comparison as: **SAS's column is a feature list; ours is a test
report.** They are not the same kind of evidence, and the difference does not
favour us.

---

## If you are choosing

- **Your work is maps, or your people are offline or on phones** → SAS.
- **Your work is statistics, or you want people to ask questions instead of
  learning a report builder, or you must prove who saw which rows** →
  Datalytics.
- **Your data is very large** → SAS, until Datalytics is tested at that size.
- **Everything else** → they are close enough that price, hosting and who
  supports it should decide.
