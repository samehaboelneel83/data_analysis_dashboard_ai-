# Closing the UNKNOWN register — session 19

Worked through the five outstanding items. Two are now resolved, one partly, one is blocked by your own instruction, one by tooling.

### Safety log
- All model work happened in a **new blank sandbox**, closed with **Don't save**.
- **One project was created in your account, with your explicit authorisation** — see §2. I did not delete it, because your standing rules forbid me performing deletes.
- The **Esri terms dialog was left unanswered**, as you instructed. No response is recorded against your account.
- `130_551_Creating a Bar Chart` was not touched.

---

## 1. Machine Learning objects — 3 of 6 fitted, 6 of 6 role-verified

All six role schemas in `visualizations.md` §G.1 were **re-verified against the live object** and match. Three are now fitted and rendered.

| Object | Roles (verified) | Fit | Observations | Panels |
|---|---|---|---|---|
| **Forest** (session 16) | Response\*, Predictors\*, Partition ID, Frequency, Weight | KS (Youden) **0.1000** | **2.3M of 2.3M** | Variable Importance · **Error Plot** (Misclassification Rate vs Number of Trees) · Confusion Matrix |
| **Bayesian network** | Response\*, Predictors\*, **Partition ID only** | KS (Youden) **0.2855** | **646K of 2.3M** | **Network** (node-link: predictors → target) · **Variables in Network** (BIC Score) · **Model Selection** · Confusion Matrix |
| **Gradient boosting** | Response\*, Predictors\*, Partition ID, Frequency, Weight | KS (Youden) **0.3986** | **2.3M of 2.3M** | Variable Importance · **Iteration Plot** (Misclassification Rate vs Number of Trees) · Confusion Matrix |
| Factorization machine | Response\*, Predictors\* *(no optional roles)* | — | — | not fitted |
| Neural network | Response\*, Predictors\* + optional | — | — | not fitted |
| Support vector machine | Response\*, Predictors\* + optional | — | — | not fitted |

### 1.1 The Bayesian network's Model Selection panel
A small-multiples plot of **Misclassification Rate** across four structure families — **Structure · Markov blanket · Naive · Parent-child** — each with sub-ticks 1–5 for the number of parents, and a **green star marking the selected model**. A compact, honest way to show *"here is the search space and here is what I chose"*. Together with Model comparison's colour-coded winner, that is two places the product marks a verdict visually; both are worth copying.

### 1.2 Defect 75 gets a third data point — and it is now unambiguous
Same two predictors (`Customer Age`, `Margin`), same response, same table:

| Object | Observations |
|---|---|
| Cluster | **646K of 2.3M** |
| Bayesian network | **646K of 2.3M** |
| Decision tree | 2.3M of 2.3M |
| Forest | 2.3M of 2.3M |
| Gradient boosting | 2.3M of 2.3M |

Two distinct missing-value policies, split cleanly along model family, **never stated anywhere in the UI**. A reader comparing a cluster and a tree on one page is comparing two different populations. This is now a five-object finding rather than a two-object one.

### 1.3 A model-quality aside
On this data the ranking is Gradient boosting 0.3986 > Decision tree 0.3872 > Bayesian network 0.2855 > **Forest 0.1000**. A forest scoring an order of magnitude below a single tree on the same inputs is the kind of result a **Model comparison** object exists to surface — and it does, immediately and visually.

---

## 2. Create pipeline — RESOLVED (and it created something)

**Authorised by you.** From the fitted Gradient boosting object: **Create pipeline ▾ → Add to new project**.

### 2.1 What happened
1. The button showed **"Creating pipeline…"** inline.
2. **The tab navigated away from Visual Analytics** to `/SASModelStudio/` — the whole application context was replaced, with no warning and no new tab.
3. Model Studio rendered a full-screen error: **"The application has encountered a serious error and must be reloaded."** with *Copy the full error to the clipboard* and **Reload**.
4. **Reload recovered it, and the project had in fact been created.**

### 2.2 What it created
| | |
|---|---|
| App | SAS Model Studio → Projects |
| Project | **`Interactive Project`** |
| Type | Data Mining and Machine Learning |
| Modified by | your account · Sep 23, 2026, 10:46 AM |

**Delete it at:** Model Studio → Projects → ⋮ on the *Interactive Project* card → Delete.

### 2.3 What the handoff actually produces — and it is good
The project opens with four tabs: **Data · Pipelines · Pipeline Comparison · Insights**.

**Data tab** — a variable grid (`Variable Name · Label · Type · Role · Assess for Bias`) with a per-variable properties panel (Role · Level · Order · Transform · Impute). The VA roles were carried across and translated:

| In Visual Analytics | In Model Studio |
|---|---|
| Response `ChannelType` | **Target** |
| every other column | **Input** |
| `_dmIndex_` (generated) | **Key** |
| `age` / "Customer Age", `City` | **Rejected** |

> **A mismatch worth flagging:** `Customer Age` was an assigned **predictor** in the VA object and arrived **Rejected** in the pipeline. The handoff does not preserve the predictor set.

There is also an **"Assess for Bias"** column on every variable — a fairness feature with no counterpart anywhere in Visual Analytics.

**Pipelines tab** — a tab named **`Interactive-Model Pipeline`** containing a **complete, runnable four-node DAG**:

```
Data  →  Visual Data Preparation  →  Gradient Boosting  →  Model Comparison
```

with a **Run pipeline** button, a **+** to add further pipelines, and a properties panel per node (the Data node reads *"Defines all the information about the data set."*).

**This is the right design.** The promoted model does not arrive as an orphan node — the handoff wraps it in a data-prep step and a model-comparison step, so the analyst lands in a working pipeline. **Copy the pattern: a promotion should produce something runnable, not a fragment.** Fix the three faults around it: do not hijack the tab, do not crash on arrival, and carry the predictor set across.

### 2.4 A bonus capture — the platform's own application map
The Applications menu enumerates the whole platform, which is the best available answer to *"where does an analytics tool sit in a suite?"*:

- **Favorites:** Explore and Visualize · Build Custom Graphs
- **Analytics Life Cycle:** Discover Information Assets · Manage Data · **Explore and Visualize** · Build Models · Manage Models · Build Decisions · Develop Code and Flows
- **Administration:** Build Custom Graphs · Manage Themes · Explore Lineage · Manage Environment · Manage Workflows

The reporting tool is **one station of seven** on an explicit analytics life cycle, with the model workbench immediately downstream. That framing is why *Create pipeline* exists at all.

---

## 3. Esri ArcGIS basemap catalogue — BLOCKED BY INSTRUCTION

You chose *leave it unanswered*. The consent dialog remains unanswered and **no response is stored against your account**. Without acceptance the catalogue is **Automatic** + **OpenStreetMap {Standard · Light · Dark · High Contrast}**. The Esri catalogue stays **UNKNOWN by choice**, not by limitation.

---

## 4. Mid-drag visual feedback — BLOCKED BY TOOLING

Rows carry `draggable="true"`, so the app uses HTML5 drag-and-drop. Synthesised `mousedown`/`mousemove` sequences do not initiate a drag (verified in session 13), and a real drag cannot be paused mid-flight for a screenshot with the available tooling. Drop-target highlighting, insertion indicators and cursor states remain **UNKNOWN** — and `UI_UX_SPECIFICATION.md` §6.2 therefore **specifies** them rather than copying them.

## 5. Custom geography provider authoring — BLOCKED BY PERMISSION

*New provider · Edit provider · Delete provider* are greyed in this deployment (defect 68). Not a tooling limit — the capability is not granted to this account.

## 6. Geo line with a real path geography — NOT ATTEMPTED THIS ROUND

Requires a path-capable geography item, which neither the ten built-in lookup vocabularies nor the single registered provider (*US County Data*) can produce. Remains **UNKNOWN**.

## 7. Export / Share / Copy link / embeddable markup, Play report / Edit playback — NOT ATTEMPTED THIS ROUND

These can be opened and cancelled without downloading, sharing or saving, which would document their options safely. Budget went to the model work and the pipeline handoff instead. **Still open, and safely doable next session.**

---

## 8. New defects

| # | Observed | Required in the rebuild |
|---|---|---|
| 82 | **Promoting a model hijacks the tab and crashes the destination.** *Create pipeline → Add to new project* replaced the Visual Analytics session with Model Studio, which rendered *"The application has encountered a serious error and must be reloaded."* The project had been created; one Reload recovered it | Open the destination in a new tab; never replace unsaved authoring context; do not ship a handoff whose landing page fails |
| 83 | **The handoff loses the predictor set.** `Customer Age`, an assigned predictor in the source object, arrived **Rejected** in the generated pipeline | Carry every role assignment across, and report anything the destination cannot represent |
| 84 | **Two missing-value policies across the model family, never disclosed** — Cluster and Bayesian network use 646K of 2.3M rows; Decision tree, Forest and Gradient boosting use all 2.3M *(supersedes and strengthens defect 75)* | State the policy per object and warn when two objects on a page disagree about the population |
