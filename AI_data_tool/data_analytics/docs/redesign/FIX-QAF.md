# Step FIX-QAF: fixes from the final QA

Source: the final QA by Claude in Chrome (EN light and AR dark). It found no blockers, 5 majors and 22 minors. Save the report as `redesign-captures/qa-final/QA_REPORT_FINAL.md`, with its screenshots beside it.

Same rules as AUTOPILOT.md: Phase 1 (no new backend work, no fake data), translations through the guards, EN light and AR dark captures, low-usage mode. Work through the list **without stopping**, except for the STOP cases in AUTOPILOT.md. At the end, run the full suite once and make one commit (two at most). Then report in at most 20 lines: per item, Fixed, Backend, or Left (with why).

For every item: **first find the cause.** If the fix needs the server, don't fake it: add it to PLAN.md's backend follow-ups and mark it Backend.

## Majors (do first)

| ID | Problem | Done when |
|---|---|---|
| M1 | **Connections list:** row values sit under the wrong headers ("Not tested" under Connection, "Never" under Status, the count under Last sync). EN and AR. | Every cell sits under its own header, in both directions. Add a test that renders a row and checks each header/cell pair. |
| M2 | **Dashboards list / Home:** 10 of 13 dashboards show no status. The counts read All 13 / Drafts 3 / Published 0, which don't add up, and Home says "0 published". | Find what the API returns for those 10 (null, a missing field, an unknown value). If the backend's default for a missing status is draft, show it as Draft. Otherwise show a neutral label and count it consistently. The tab counts and Home's number come from one shared helper, so they always add up. |
| M3 | **Ask AI main page is slow:** about 49 s for a simple question, versus about 8 s for the same kind of question in the floating panel. There is no way to stop it. | Compare the two calls: endpoint, parameters (agent mode, tools, history sent, model) and any extra requests made before or during the ask. Make the main page use the same fast path unless there's a real reason not to; report the difference. Add a "Stop" button that aborts the client request ("Stopped waiting. The server may still finish."), translated. A server-side cancel stays backend item AN2. |
| M4 | **Lineage focus, Arabic:** the impact line reads "no dataset and 9 reports are affected", so it sounds like nothing is affected. English says "0 datasets and 9 reports". | Arabic and English say the same thing. When a count is 0, either leave that part out ("9 reports are affected") or use a zero form that can't read as "nothing". Tests for 0/1/2/many in both languages. |
| M5 | **Datasets list preview panel** loads all 12,000 rows of the live dataset into the page (about 243,000 characters). | The preview asks the API for a small page (e.g. 50 rows), using the same limit parameter as other previews. If the endpoint has no limit, slice on the client and record a backend item. Check every other preview for the same problem. |

## Minors

| ID | Problem | Done when |
|---|---|---|
| 6 | Home "Last refresh" card says "7 days ago" and "No jobs yet" at the same time. | Both lines come from the same source, or the wording explains the difference (e.g. "Last data update" vs "Scheduled jobs: none"). |
| 7 | Dashboards list: the folder panel says "No folders yet" until the folders load, then the toolbar shifts, so a click on "Published" hit "Drafts". | A loading skeleton instead of the empty text. The toolbar keeps its size while loading. |
| 8 | At 1464px the Dashboards toolbar wraps and the grid/list switch drops to a second line. | It stays on one line down to 1180px; below that it wraps cleanly. |
| 9 | The selected chart keeps its green edit border in View and Present. | Switching to View or Present clears the selection and its border. |
| 10 | Floating AI panel: the table shows 2221091.66 unformatted while the text shows 2,221,091.66, and it says "1 rows". | Use the same rows table and number rule as the Ask AI page (quantity grouping), and proper plurals. |
| 11 | Dataset Overview "Used by" says 10 dashboards; the list and Lineage say 9. | Find why (deleted, duplicate or other-org dashboards). All three use the same count. |
| 12 | Datasets list with the preview open: names and freshness are cut off heavily; in AR the Dashboards header is cut too. | Lower-priority columns hide while the preview is open; names get the space, with tooltips. |
| 13 | Dataset → Analysis says "0.78× less". | Show a percentage ("22% lower"), translated. |
| 14 | Dataset → Models card shows "—" for Tested on, Trained on and Baseline. | Show the values if the API has them. If not, hide those rows rather than showing dashes, and record a backend item. |
| 15 | Ask AI chooser: the "Recent" times are stale ("1 day ago" right after use). | Using a dataset updates its recent time straight away. If the time shown is the data's update time, label it that way. |
| 16 | Ask AI history: an old failure caused by the AI being unreachable shows "I couldn't match your question" and suggests the same question. | Network or unreachable errors show the "Could not reach the agent" card, including when reopened from history. Chips never repeat the user's own question. |
| 17 | An Arabic question asked in the floating panel never appeared in history; the English one did. | Find why (scope, filter, encoding, or the panel not creating a thread). Arabic questions are saved and listed like English ones. |
| 18 | Lineage: the minimap covers the bottom report nodes. | Fit and the default view keep a margin for the minimap, or the minimap can be collapsed and sits clear of the nodes. |
| 19 | Lineage list: Last refreshed shows "—" for the Demo uploads but "7 days ago" for test uploads. Switching to List also drops the focus. | The same rule for every node, and the focus kept across Graph/List. |
| 20 | Upload review: an Arabic value in the preview is pushed away from the rest of its column. | Cell text uses `dir="auto"` with consistent alignment. |
| 21 | Upload suggests "QAF upload" for "QAF-upload". | The suggested name keeps hyphens. Only the extension is removed and underscores become spaces, unless the existing rule says otherwise. |
| 22 | Connections says "Not tested" while Lineage calls the same connection healthy. | One status source, or clearly different labels ("Last test: never" vs "Sync: current"). |
| 23 | Add connection step 2: Create / Test / Cancel sit below the fold. | The footer is pinned, as on step 1. |
| 24 | Admin › Column security: rules can only be deleted; Row security also has Edit. | Add Edit if the API supports updating column rules; otherwise record a backend item. |
| 25 | Admin › SSO: "Enabled" is ticked though nothing is filled in. | Show the real stored value. If the server says enabled with an empty config, show a warning instead of a plain tick. |
| 26 | Admin › Audit trail: the Detail column shows unexplained values ("3", "1d", "?"). | Give known detail shapes a label where the frontend can (e.g. "1d" → "1 day" for expiry). Unknown ones keep the raw value with a tooltip; record "structured audit details" as a backend item. |
| 27 | Platform settings: the AI model connection fields are cramped and misaligned. | Use the same form grid as the other settings sections, EN and AR. |

## Not to change

- The model label changing from "Qwen 3.5" to "Qwen 3.8 27B" under Auto is the server's choice.
- The QA's three Ask AI chats: the owner deletes them.
