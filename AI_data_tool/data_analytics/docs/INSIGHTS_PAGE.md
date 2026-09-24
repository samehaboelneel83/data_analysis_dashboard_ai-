# The Insights page

**Route** `/insights` · **Source** `frontend/src/pages/InsightsHub.tsx` (246 lines) · **Tests** `frontend/src/pages/InsightsHub.test.tsx` (14)

Every statement here is read from the code. Where a rule is enforced server-side the endpoint is named — this page mirrors refusals, it never decides them.

---

## 1. What this page is for, and what it deliberately is not

Every analysis capability in the platform is **dataset-scoped**, so each one correctly lives as a section or tab of `/datasets/:id`. The cost of that was invisibility: you had to already know which dataset page to open and how far to scroll before you could find, say, key influencers.

This page is the front door to that family. Its job is **navigation**:

> pick a dataset → pick a question → land on the section that already implements it.

It re-implements **nothing** — with exactly one exception, the Top insights preview (§4), which it renders itself so that "is there anything here worth looking at?" can be answered without a click.

---

## 2. Header and dataset picker

| Element | Behaviour |
|---|---|
| **Insights** | `t('nav.insights')` |
| Subtitle | "Pick a dataset, then ask it a question. Every capability here runs on the same secured data your widgets read." (`t('insights.subtitle')`) — it states the governance guarantee, because a page offering six kinds of analysis is exactly where someone wonders whether the numbers obey their row rules. They do. |
| **Dataset** `<select>` | `id="insights-hub-dataset"`, properly labelled. Each option is the dataset name, plus **` · live`** for a DirectQuery one — so you can see *before* choosing why half the cards are about to grey out. |
| **Search datasets…** | `useListFilter` over the dataset **name** only. Client-side, and it appears only once you have **8 or more** datasets. |

**The default selection is the most recently *created* dataset, not the first one the API returned.** There is no "last opened" signal anywhere in the product (Home's Recents falls back the same way for the same reason), and someone landing here almost always wants the dataset they were just working with rather than dataset #1. The code says so explicitly rather than leaving it to look like an accident.

**A search that matches nothing does not empty the dropdown.** The options fall back to the full list (`noMatches ? datasets : filtered`), so a typo can never strand you with a picker you cannot pick from.

---

## 3. The three states

| State | What renders |
|---|---|
| **Loading** | `LoadingState` |
| **Error** | `LoadError` with a working **Try again** that re-runs the load and clears the error |
| **Empty** | `EmptyState` — "No datasets yet — upload one or connect a database first." |

These are three different claims and never borrow each other's copy. The page's whole content is the dataset list, so a failed load gets a persistent, retryable banner rather than a message that would sit there with no way out.

---

## 4. Top insights — the one thing this page computes

The panel between the picker and the cards. It fires **automatically** the moment a dataset is selected, whether by the default or by you.

```
TOP INSIGHTS                                   View full scan →
<one-paragraph narrative>
  • <finding title> — <detail>
      <inline chart>
  • …up to three
```

- **Source** — `insightsApi.runShared(datasetId)` → `POST /datasets/{id}/insights`.
- **Top three only.** The backend already returns findings sorted by score, so the page slices rather than ranks.
- **View full scan →** goes to `/datasets/:id#insights`, the section that owns the complete result.
- **It has its own three states**, independent of the page's: a "Scanning for insights…" loader, a retryable `LoadError`, and *nothing at all* when the scan finds nothing worth surfacing — no empty panel announcing that it has no news.

### Why `runShared` and not `run`

`runShared` de-duplicates concurrent scans of the same dataset: N callers in flight share **one** request. That matters here because clicking through to `/datasets/:id#insights` fires the identical scan moments later, and because every Dynamic Pin card on a dashboard evaluates through the same helper — five cards over one dataset cost one scan, not five.

### The inline charts

`FindingChart` draws each finding the same way the Insights pane's "+ Chart it" button would:

| Finding's columns | Chart |
|---|---|
| one categorical + one numeric | bar, summed by category |
| exactly one numeric | histogram, 20 bins |
| anything else (e.g. a correlation between two measures) | **no chart** — text only |

A correlation has no bar or histogram shape worth a thumbnail, so it stays a sentence rather than being forced into a picture.

---

## 5. The six capability cards

Each card is a link to the section that implements it. The **suffix is a cross-file contract** with `DatasetDetail.tsx` — change an anchor there and the card lands on nothing.

| Card | Goes to | Needs imported data |
|---|---|---|
| **Insight scan** | `/datasets/:id#insights` | **yes** |
| **Anomalies** | `/datasets/:id#anomalies` | **yes** |
| **Key influencers** | `/datasets/:id#influencers` | no |
| **Patterns** | `/datasets/:id#associations` | no |
| **Segments** | `/datasets/:id#segment` | **yes** |
| **Statistical tests** | `/datasets/:id?tab=statistics` | no |

Two things worth knowing about that last row: it is a **query parameter, not an anchor**, and the value is `statistics` while the tab is labelled "Analysis" — a bookmark-compatibility contract, not a typo.

---

## 6. DirectQuery: disabled, not hidden

For a DirectQuery dataset the three `importOnly` cards render as `<div aria-disabled="true">`, dimmed, with the line:

> *Needs imported data — this dataset is DirectQuery.*

This is the deliberate part. The alternatives were both worse:

- **Hide them** — the capability appears to not exist, and the reader never learns why.
- **Link them anyway** — the card navigates to a section that will not be on the page when it loads. Offering a control that silently does nothing is a real defect, and this codebase has shipped that bug before.

The gate mirrors the server exactly. `POST /datasets/{id}/insights` refuses at `backend/app/routers/datasets.py:1327`:

```python
if not ds.filename or ds.mode == "directquery":
    raise HTTPException(400, "Insights run over import-mode datasets")
```

The Top insights preview is skipped for the same reason — no request is made, so there is no error banner for a refusal the page already knew about.

---

## 7. The Ask AI line

> Prefer plain language? **Ask AI** answers questions about this data directly.

Links to `/ask?dataset=:id` with the current dataset pre-selected (or bare `/ask` if none is). It is the escape hatch from "pick a capability" to "just ask" — the same secured frame, a different interface to it.

---

## 8. Where the behaviour actually lives

| Concern | File |
|---|---|
| The page | `frontend/src/pages/InsightsHub.tsx` |
| Inline finding charts | `frontend/src/components/insights/FindingChart.tsx`, `MiniBarChart.tsx` |
| Scan de-duplication | `insightsApi.runShared` in `frontend/src/services/api.ts` |
| Search box | `frontend/src/components/ui/ListFilter.tsx` |
| The three state components | `frontend/src/components/ui/{LoadingState,LoadError,EmptyState}.tsx` |
| The scan endpoint and its DirectQuery refusal | `backend/app/routers/datasets.py` |
| The engine behind it | `backend/app/services/insights.py` |
| The sections every card links into | `frontend/src/pages/DatasetDetail.tsx` |

---

## 9. Known quirks, recorded rather than hidden

**The anchors are a contract nothing enforces.** `#insights`, `#anomalies`, `#influencers`, `#associations`, `#segment` and `?tab=statistics` must match `DatasetDetail.tsx`. Renaming a section there leaves the card pointing at a fragment that does not exist, and the failure is silent — the page loads, scrolled to the top, with no error.

**"Anomalies" is import-only by inference, not by its own endpoint.** The comment in `CAPABILITIES` reasons that `/outlier-details` refuses DirectQuery identically to `/insights` and `/segment`. That is correct today; it is a conclusion about a sibling endpoint rather than a gate read from that endpoint.

**The search filters the picker, not the page.** Unlike every other `useListFilter` surface, the result here narrows a `<select>` rather than a list of cards — and, as above, a no-match silently restores the full list rather than showing a "nothing matches" message.

**The page has no `noMatches` message at all,** for the same reason: there is no list to empty.

**The default dataset can surprise.** "Most recently created" is not "most recently used". Upload a throwaway CSV and it becomes the hub's default until something newer arrives.
