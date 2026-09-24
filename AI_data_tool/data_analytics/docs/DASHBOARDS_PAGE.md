# The Dashboards page

**Route** `/reports` (and the alias `/dashboards`) · **Source** `frontend/src/pages/Reports.tsx` · **Tests** `frontend/src/pages/Reports.test.tsx`

Every statement here is read from the code. Where a rule is enforced server-side, the endpoint is named — the page only ever *mirrors* a permission, it never decides one.

---

## 1. What this page is for

The inventory of dashboards you can open. It answers three questions and nothing else: **what exists**, **what am I allowed to do with it**, and **how do I make another one**. Designing a dashboard happens on `/reports/:id`; this page only lists, creates, shares, publishes and deletes.

---

## 2. Page header

| Element | Behaviour |
|---|---|
| **Dashboards** | `t('nav.dashboards')` |
| Subtitle | "Design multi-page interactive dashboards — drafts stay private until you publish or share them" (`t('dashboards.subtitle')`). It states the privacy default, which is the single most misunderstood thing on the page. |
| **Search dashboards** | `useListFilter` over each report's **name and description**. Client-side — the list endpoint takes no `limit`/`offset`. **It only appears once there are 8 or more dashboards**; below that the box is chrome competing with the list it filters. |
| **+ New dashboard** | Opens the inline create form below the header. Always available to any member. |

---

## 3. Creating a dashboard

`+ New dashboard` reveals a card with three fields:

- **Dashboard name*** — the only required field; **Create & Open** stays disabled until it is non-empty.
- **Description (optional)** — shown on the card afterwards.
- **Dataset** — a `<select>` of every dataset you can read, defaulting to **"— No dataset (add later) —"**. A dashboard with no dataset is legal; its widgets pick one later.

On success: `POST /reports`, a toast, the form closes, and the new dashboard is **prepended** to the grid so it appears where you are already looking. It does **not** navigate you into the designer — you stay on the list.

---

## 4. The three states, which are three different claims

These are deliberately distinct and must never be collapsed into one another.

| State | What renders | What it means |
|---|---|---|
| **Loading** | "Loading…" | The request is in flight. |
| **Error** | `LoadError` block with **Try again** | The request failed. |
| **Empty** | Card with a chart icon, "No dashboards yet", and **Create your first dashboard** | The request succeeded and you genuinely have none. |

The error state exists because of a specific bug: without the `.catch`, a server error cleared `loading` and fell through to "No dashboards yet" — telling someone with fifty dashboards that they had none, and inviting them to rebuild work that already existed.

**No matches** is a fourth, separate message ("Nothing matches …"). A search that finds nothing is not the same claim as owning nothing, so it never borrows the empty state's copy.

---

## 5. Grouping — My workspaces / Granted to me

The grid splits on **authorship**, not permission:

- **My workspaces** — `is_mine === true`
- **Granted to me** — everything else, under the line *"Published or shared with you by others. View-only dashboards open without design controls."*

**Both headings appear only when both groups are non-empty.** If you authored everything, you get a plain unlabelled grid — a lone "My workspaces" heading over your entire list says nothing. Same contract as the workspace tree in the rail.

Why authorship and not permission: an org admin can administer *every* dashboard in the organisation, so grouping on capability would file the whole company under "mine".

---

## 6. The card, element by element

```
┌─────────────────────────────────────────────┐
│ Dashboard name          [view only] [PUBLISHED] │  ← title + status
│                         ⧉  📣  🗑  ⋯            │  ← controls
│ Description                                  │
│                                              │
│ [dataset chip]                      date     │  ← footer
│ ┌──────────────────────────────────────────┐ │
│ │           Open designer →                │ │
│ └──────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

| Element | Source | Notes |
|---|---|---|
| **Name** | `r.name` | A link to `/reports/:id`. |
| **Description** | `r.description` | Omitted entirely when absent. Dashboards built by *Suggest dashboards* carry "Suggested from the data" here — that is a description, not a special badge. |
| **view only** chip | `my_capability === 'view'` | You can open it but not design it. |
| **PUBLISHED** chip | `created_by != null && published` | Everyone in the organisation can open it, view-only. |
| **Dataset chip** | `datasets.find(d => d.id === r.dataset_id)` | Falls back to the words **"No dataset"** when the dashboard has none, or when its dataset is not one you can read. |
| **Date** | `r.created_at`, locale-formatted | This is the **created** date, not last-modified. |
| **Open designer →** | link to `/reports/:id` | Reads **"Open →"** instead when you cannot edit — a "designer" link onto a dashboard whose every edit the server refuses is a dead control with extra steps. |

---

## 7. The four controls, and who sees each

Three different flags gate them. They are not interchangeable.

```
canEdit        = (my_capability ?? 'view') !== 'view'
owned          = created_by != null
canAdminister  = owned && (is_mine || viewer is an org admin)
```

| Control | Shown when | Does |
|---|---|---|
| **Share** ⧉ | `canAdminister` | Opens the share dialog (§8). |
| **Publish / Unpublish** 📣 | `canAdminister` | `POST /reports/{id}/publish`. Toggles org-wide view-only access. |
| **Delete** 🗑 | `canEdit` | Confirms, then `DELETE /reports/{id}`. |
| **⋯ menu** | `canEdit` | Holds one item: **Delete dashboard**. |

Two things worth understanding:

**`owned` excludes legacy rows.** A dashboard created before authorship existed has `created_by === null`. The publish-and-grant regime does not apply to it at all, so Publish and Share are absent — offering them would be a button the server answers 400 to.

**`canEdit` and `canAdminister` are different questions.** Someone granted `edit` on *your* dashboard can delete it but cannot publish or share it: administering the audience stays with the author (and admins). Conversely an admin can administer a dashboard they cannot… well, they can edit everything, but the distinction is real for granted non-admin editors.

Every one of these mirrors a server rule. The page hides what the server refuses; it never grants anything by showing a button.

---

## 8. Publish vs Share — the distinction the page exists to make clear

These are two different mechanisms and the subtitle, the dialog copy and the toasts all repeat the difference on purpose.

| | **Publish** | **Share** |
|---|---|---|
| Audience | Everyone in the organisation | One named person, by email |
| Strength | View-only, always | `view`, `edit`, or `edit + data` |
| Reaches a draft? | No — publishing *is* what stops it being a draft | **Yes** — a grant opens a private draft to that person |
| Reversible | Yes, Unpublish returns it to a private draft | Yes, Remove drops the grant |
| Endpoint | `POST /reports/{id}/publish` | `POST` / `DELETE /reports/{id}/grants` |

**Grants are the only way another user gets design rights on a dashboard.** Publishing can never give edit access, no matter the audience.

---

## 9. The Share dialog

Opened by ⧉. Titled *Share "<name>"*, with the standing explanation: *"Sharing gives one person access — including to a draft. Publishing (separate) makes it view-only for the whole organisation."*

- **Email field** — by email, deliberately, never a picker of everyone in the organisation. A share dialog that lists every colleague is also a directory listing, and this product does not publish one.
- **Level** — `Can view` / `Can edit` / `Can edit + data`. The `<option value>`s are `view` / `edit` / `data` and are an API contract; the labels are free text.
- **Enter** in the email field submits.
- Below, the current grants, each with **Remove**. Three states of its own: `Loading…`, "Not shared with anyone yet.", or the list.
- Re-sharing with someone who already has a grant **replaces** their level rather than adding a second row.

It is a real modal: focus trap, Escape to close, focus restored on exit, via the shared `useModalDialog` hook that every overlay in the app uses.

---

## 10. What this page deliberately does not do

- **No pagination.** The grid renders every dashboard you can see. (The Datasets page pages at 8; this one does not.)
- **No sort control.** Order comes from the server.
- **No export or download.** Nothing here produces a file.
- **No navigation after create.** You stay on the list and choose when to open.
- **No last-modified date.** The footer date is creation.

---

## 11. Where the behaviour actually lives

| Concern | File |
|---|---|
| The page | `frontend/src/pages/Reports.tsx` |
| Search box | `frontend/src/components/ui/ListFilter.tsx` |
| Confirm dialog | `frontend/src/components/ui/ConfirmDialog.tsx` |
| Overflow menu | `frontend/src/components/ActionMenu.tsx` |
| Error block | `frontend/src/components/ui/LoadError.tsx` |
| Modal focus trap | `frontend/src/components/ui/useModalDialog.ts` |
| List, create, delete, publish, grants | `backend/app/routers/reports.py` |
| Who may do what | `backend/app/core/capability.py` |

---

## 12. Known quirks, recorded rather than hidden

**Delete appears twice on every editable card** — once as the red trash button and once as the only item in the ⋯ menu. This is intentional and pinned by a test (*"the ⋯ menu delete item fires the same handler as the icon button"*), but it does mean the overflow menu currently holds nothing the row does not already show. If the menu gains a second action the redundancy resolves itself; if it does not, one of the two is removable.

**The search box hides below 8 dashboards.** Someone with 7 dashboards and a colleague with 9 see different chrome. That is `useListFilter`'s deliberate threshold, not a bug, but it surprises people comparing screens.

**The dataset chip silently reads "No dataset" in two different situations** — the dashboard genuinely has none, *or* it points at a dataset this viewer cannot read. The card cannot tell the two apart because the lookup is a local `find` over the datasets you can see.

**The date is creation, not modification.** A dashboard edited this morning can show a date from March.
