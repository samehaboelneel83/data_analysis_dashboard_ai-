# Publishing and sharing

How a dashboard goes from the person who built it to the people who read it,
who may do what with it, and what was built, measured and left for later.

Status: phases 1 to 4 built 2026-10-12 (uncommitted). What is not done is listed
at the end of each phase and again in section 8.

## 1. What already existed

Found by reading the code before anything was changed.

| Area | What was there | Where |
|---|---|---|
| Sign-in, organisations, roles | JWT sign-in, every row carries `org_id`, a role per user with `is_org_admin` | `core/security.py`, `dependencies.py` |
| Who may open a dashboard | One resolver: administrator, then author, then a share naming the person, then a shared folder, then published; levels `view` / `edit` / `data`; **404, never 403**, for what a person may not know exists | `core/capability.py` |
| Draft and published | A published dashboard's readers see the last *release* (a frozen copy), not the author's edits; a publish gate that refuses on review findings | `services/report_release.py`, `routers/reports.py` |
| Versions | Saved versions of the draft, with restore | `ReportVersion` |
| Sharing | A share to one person by email (`report_user_grants`); a role-wide level (`report_capabilities`); folders shared with a person, a role or a team | `routers/reports.py`, `routers/workspace.py` |
| Links without sign-in | Hashed token, 1 to 90 days, revocable, access log; the link reads data as its maker | `routers/shared.py` |
| Embedding | Host-signed embed configurations | `routers/embed.py` |
| Scheduled delivery | Schedules, deliveries log, alerts; a schedule reads data as its maker | `services/delivery.py` |
| Data security | Row rules and column rules applied where rows are read; sensitivity labels; a dataset export policy; one gate for every download | `services/row_security.py`, `routers/shared.py::download_gate` |
| Record of actions | `audit_log` through `services/audit.record`; notifications; recently viewed; pins | |

## 2. What was missing

1. A dashboard could be shared with a person only: not with a **role or a team** (only folders could).
2. A share had **no end date**.
3. **Download was not a separate permission**: whoever could view could export.
4. **Sharing on** was not a permission: only the author or an administrator could share.
5. No **archived** state: the choice was published, draft or deleted.
6. No **going back** to an earlier release (versions restored the draft, not what readers see).
7. No **handing over** to another owner.
8. No **approval** step before publishing.
9. No **category or tags**, no **favourites**.
10. No **reader's view**: the dashboards list returns every dashboard with all its pages and widgets.
11. No single answer to "what may I do with this dashboard?".

## 3. Risks found

| Risk | Why it mattered | What was done |
|---|---|---|
| Links without sign-in were **on by default** | Anyone with edit access could make one | A platform setting, **off by default**; creating one is refused (403) and existing ones stop (404) while it is off |
| A link kept working after its **maker lost access** | The link reads as its maker | Every use checks the maker is active and can still open the dashboard, and that it is not archived |
| A schedule kept **sending after access was lost** | Same reason | Every run decides again: archived, maker's access, download right. A refusal is recorded as "not sent: …" |
| **Viewing implied exporting** | A reader could take away what they were only meant to look at | Downloads are decided separately, at the one gate every download passes |
| The dashboards list is **heavy** | 941 KB for 111 dashboards | A light catalogue endpoint (section 7) |
| A share to many people was **one click** | A role or a team reaches everyone in it | Asked about first, starts at view |

## 4. Decisions

- **One resolver, extended.** No second permission system. `core/capability.py` still answers who may open what; it now also reads shares to roles and teams, ignores ended shares, and closes an archived dashboard to everyone but its owner and administrators.
- **One table for direct shares.** `report_user_grants` gained `role_id`, `org_unit_id`, `expires_at`, `can_export`, `can_share`, `created_by`; exactly one of person / role / team is set. Nothing is copied into a second table. A team share reaches the teams under it.
- **A share to a person decides alone; shares through a role or a team add up.** Naming a person is the most specific statement, so it can also narrow (for example no downloads) what their role would give.
- **Sharing never touches data security.** A share lets someone open the dashboard. Row rules, column rules, the sensitivity label and the dataset export policy are applied where they always were, for the person reading. The export right only ever narrows.
- **Sharing on gives no more than was held.** A holder of "may share" can give view only, to people only, never with "may share", never longer than their own share, never with downloads they lack.
- **Readers see releases.** Publishing and updating make a release; going back makes a new release from an old one, so history only grows and the author's draft is untouched.
- **404 for what a person may not know exists**, 403 for what they can see but may not do.
- **No new infrastructure.** No new service, queue or store.
- **Requests from another site.** The session is an httpOnly cookie; a write that arrives with the cookie alone is treated as not signed in (the existing rule in `dependencies.py`). The new endpoints use the same sign-in dependency, and a test sends such a write to each kind of them.
- **Typed text is text.** Category, tags and the share message are stored as typed, bounded in length, and shown by the screens as text, never as markup.

### What each change of state does

| Action | Readers | Shares | Links without sign-in | Schedules | Data |
|---|---|---|---|---|---|
| Unpublish | Lose "everyone in the organisation"; named shares still work | Kept, still work | Work only if the maker can still open it | Run only if the maker can still open it and download | Untouched |
| Archive | Nobody but the owner and administrators | Kept, do not work | Stop (404) | "Not sent: archived" | Untouched |
| Restore | Back as a draft; named shares work again | Work again | Work again if not expired or revoked | Run again | Untouched |
| Delete | Gone | Deleted with it | Deleted with it | Deleted with it | Datasets are not deleted |
| Remove a share | That person, role or team loses it unless another path gives it | - | Links *they* made stop | Schedules *they* made stop sending | Untouched |
| Hand over | Unchanged | Unchanged; the previous owner keeps edit | Unchanged | Unchanged | Untouched |

## 5. Phases and what proves each

### Phase 1: access rules (done)
Shares to roles and teams, end dates, download and share-on rights, archive, the answer to "what may I do".
Proof (`backend/tests/test_publishing.py`): a draft answers 404 on every route for a reader and for another organisation; a reader's owner-only requests are refused whatever they send; person, role, team and child-team shares open the dashboard and removing them closes it; an ended share gives nothing; sharing on never gives more than was held; downloads are refused (PDF, workbook, package, one chart) while viewing stays allowed, and each refusal is recorded.

### Phase 2: lifecycle (done)
Release rollback, archive and restore, handing over, approval where the organisation asks for it, category and tags.
Proof: readers see the release until the next; going back shows the older one; archive closes the dashboard, its links and its schedules, and restore brings them back; with approval required nothing is published or updated without an approval of the current revision.

### Phase 3: the reader's portal (done)
A light catalogue with sections, search, filters, paging, favourites, and what the reader's schedules sent.
Proof: the catalogue holds only what the person may open; filter values come only from those; 600 dashboards are answered in a fixed number of queries (at most 20).

### Phase 4: screens (done)
The share dialog (person / role / team, end date, rights, message, asked first for many people and for removal), a Publishing tab, the portal page, English and Arabic.
Proof: `ShareDashboardDialog.test.tsx`, `PublishingPanel.test.tsx`, `Portal.test.tsx`; looked at on screen in both languages.

### Phase 5: not built
See section 8.

## 6. Where things are

| | |
|---|---|
| Rules | `backend/app/core/capability.py` (`report_grants`, `export_refusal`, `require_export`) |
| Endpoints | `backend/app/routers/publishing.py` (`/reports/{id}/access`, `/publication`, `/archive`, `/restore`, `/releases/{rid}/rollback`, `/owner`, `/review/*`, `/grants/{gid}`; `/portal/catalog`, `/facets`, `/favorites/{id}`, `/deliveries`) |
| Download gate | `backend/app/routers/shared.py::download_gate` |
| Links | `backend/app/routers/shared.py::_resolve_link` |
| Delivery | `backend/app/services/delivery.py::run_schedule` |
| What the screen is told | `backend/app/routers/authz.py` (`download`, `share_link`) gives the same answer the action gets |
| Schema | `backend/alembic/versions/0068_publishing_sharing.py` (run up, down and up again on a scratch PostgreSQL database on 2026-10-12, and by the SQLite migration tests), and `main.py::_migrate` |
| Setting | "Allow links that open without signing in" (`guest_links_enabled`, off by default), Platform settings → Security |
| Screens | `frontend/src/components/report/share/ShareDashboardDialog.tsx`, `PublishingPanel.tsx`, `frontend/src/pages/Portal.tsx` |
| Wording | `frontend/src/i18n/pages/publishing.ts` |

## 7. Measured

On the running instance, 111 dashboards, signed in as an administrator, 12 requests each, 2026-10-12.

| Request | Median | Slowest of 12 | Size |
|---|---|---|---|
| `/reports` (the list that existed) | 48 ms | 157 ms | 941 KB |
| `/portal/catalog?limit=24` | 9 ms | 18 ms | 12 KB |
| `/portal/catalog?q=…` | 9 ms | 11 ms | 9 KB |
| `/portal/facets` | 10 ms | 11 ms | under 1 KB |
| `/reports/{id}/access` | 6 ms | 19 ms | under 1 KB |
| `/reports/{id}/publication` | 7 ms | 11 ms | 1 KB |

The catalogue is a new endpoint beside the old list, not a faster version of it: the old list is unchanged and still used by the Dashboards page.

Not measured: many people at once; a catalogue of thousands on the running instance (only the query count was checked, on 600, in a test); opening a dashboard, which this work did not change.

## 8. Not done

- **Notices by email.** A share notifies inside the application only.
- **Asking for access.** Someone who cannot open a dashboard cannot request it.
- **Comments and subscriptions** by readers.
- **A named reviewer.** Approval is decided by any administrator (who also turns the rule on, in the Publishing tab); there is no reviewer role, no queue page, no reminder.
- **The catalogue filters in Python** after one query for the organisation's dashboards. Fine at hundreds; at tens of thousands it should filter in the database.
- **The Dashboards page still uses the heavy list.** Moving it to the catalogue is its own change.
- **Readers of a link without sign-in** are not offered the portal, by design.
- **Download right per format** (for example PDF but not rows): one switch covers all.
- **Bulk sharing** of several dashboards at once.
- **Archived dashboards are not removed after a time**; nothing is deleted automatically.
- **Load test** with many readers at once.
- **One share per role or team is kept by the endpoint, not by the database.** The unique rule in the table covers a person; two identical requests for the same role at the same instant could make two rows.
