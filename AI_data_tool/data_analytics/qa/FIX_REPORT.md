# Datalytics — fixes for the QA run of 2026-09-21

Companion to `qa/REPORT.md`, which recorded 9 failing cases out of 129. This
document says what each one turned out to be, what changed in the code, and how
the fix was verified in the browser afterwards.

| Original finding | Verdict | Status |
|---|---|---|
| I18N-01 — login language switcher logs you in | Real, high severity | Fixed, re-tested |
| I18N-02 — header dropdowns invisible | Real, high severity | Fixed, re-tested |
| DASH-03 — widgets show "Configure widget to see data" | Real, worse than reported | Fixed, re-tested |
| BUILD-05 — empty filter chip and false conflict banner | Real | Fixed, re-tested |
| DASH-10 — folder rename corrupts the name | Real, different cause | Fixed, re-tested |
| BUILD-09 / BUILD-15 — free-layout drag blanks the page | Not reproducible; a different real bug found in the same code | Fixed, re-tested |
| DS-04 — fx columns missing from the Data tab | Not a defect | Re-verified working |
| UP-01 — no feedback on an empty upload | Not a defect | Re-verified working |
| UP-03 — no feedback on a rejected file type | Not a defect | Re-verified working |

Build under test: the running dev stack at `http://localhost:3001`, Vite dev
server with `frontend/src` bind-mounted, so every change below was live without
a rebuild. All re-tests were performed by clicking through the app as a user,
signed in as `admin@datalytics.local`.

---

## I18N-01 — the language switcher on the login page signed you in

The language button is rendered inside the login `<form>`, and had no `type`
attribute. HTML defaults a `<button>` in a form to `type="submit"`, so the
button was a second, invisible Sign In control sitting directly above the real
one. With the browser's own autofill populating the email and password fields —
an extremely common state on a login page — one click on "EN" submitted real
credentials and landed the user on Home.

`components/LanguageSwitcher.tsx` now declares `type="button"` on the trigger
and on both language options. An audit of the whole frontend found `Login.tsx`
to be the only file containing a `<form>` at all, and no other untyped button
inside one, so this was the single instance of the defect rather than a class of
them. The remaining ~420 untyped buttons in the codebase have no form ancestor
and are unaffected.

**Re-tested:** signed out, opened `/login`, clicked the language button. The
language menu opens, the URL stays `/login`, no auth token is written and no
`POST /api/v1/auth/login` is fired. Choosing العربية switches the page to
Arabic and RTL, still signed out.

## I18N-02 — the account and language dropdowns were clipped out of sight

`components/TopBar.tsx` set `overflow: hidden` on a `<header>` with a fixed
52px height. Every dropdown the bar owns — account menu, language menu,
notifications — is absolutely positioned *below* that 52px strip, so the whole
panel was clipped away. The menus were in the DOM, correctly styled and
clickable if you could target them blindly, which is why the symptom read as
"nothing happens when I click my avatar". This is also what made Sign out
unreachable for the entire original QA run; every logout in that run was worked
around by clearing cookies by hand.

The `overflow: hidden` is removed. The only element that needed clipping is the
page title, and the `<h1>` beneath already truncates itself with its own
`overflow: hidden` and `text-overflow: ellipsis`.

**Re-tested:** the account menu now renders in full (email, role, organisation,
Log out) and Log out works from it. The language menu renders in full with both
options and its hint line. Confirmed in both LTR and RTL.

## DASH-03 — "Configure widget to see data" was the loading state

This one was real and worse than the report described. Opening *Demo — Sales
Overview* showed that message on **29 tiles at once**.

Every chart renderer treats absent data as "nothing configured". `data` starts
as `null` and `loading` started as `false`, so the very first paint of a chart
widget showed the unconfigured placeholder — accusing the author of a mistake
they had not made, which is the exact failure mode the codebase already guards
against on the fetch-error path. Worse for a tile below the fold: fetching is
lazy through an `IntersectionObserver`, so a widget that is never scrolled to
never fetches, and that placeholder was not a flash at all — it was the
permanent resting state of an off-screen widget. That is what the original run
counted.

`components/report/WidgetRenderer.tsx` gains a `widgetFetchesData()` predicate
that mirrors `fetchData`'s early returns exactly, and `loading` is initialised
from it, so anything that will query starts in the loading state. The three
early returns inside `fetchData` now clear `loading` so a widget that turns out
not to fetch cannot get stuck.

**Re-tested:** *Demo — Sales Overview* now shows **0** occurrences of
"Configure widget to see data" at 3s, at 13s and at rest, where it previously
showed 29. Tiles show "Loading…" and then real data (Total revenue 8,632,597,
Units sold 402,108, Average margin 19.0%). Scrolling down loads the rest, again
through "Loading…" rather than the placeholder.

## BUILD-05 — an empty filter chip and a false "changed in another session" banner

Two separate defects behind one symptom.

The first is in `components/report/WidgetRenderer.tsx`. Unticking the last value
in a slicer still emitted a filter, with an empty value list — producing the
`region in ()` chip on the page and handing every receiving widget a predicate
nothing can satisfy, which is why unrelated tiles went blank and one fell back
to its placeholder. The text-filter handler immediately above already had the
right guard; the slicer toggle simply lacked it. An empty selection now clears
the filter. `components/report/CrossFilterContext.tsx` also clears rather than
stores an empty value set, so no future caller has to remember.

The second is the spurious conflict banner. The revision poll skips itself while
one of our own writes is in flight, by reading `savingRef`. That ref was
synchronised from `saving` by a `useEffect`, which only runs after React
commits — so a poll tick landing in that window read `false` while a write was
already in flight, saw the bumped revision, and reported our own edit as
somebody else's. `pages/ReportBuilder.tsx` now writes the ref synchronously.

**Re-tested:** clicked Europe in the Region slicer (chip reads
`region in (Europe)`), then clicked it again to deselect. The filter bar returns
to "No selections". No empty chip, no conflict banner, no widget dropped to a
placeholder.

## DASH-10 — folder rename corrupted the name

The rename did not use an input in the page at all: `window.prompt` was used
here and in ten other places. A native prompt cannot be themed, blocks the JS
thread, returns `null` forever once a user ticks "prevent this page from
creating additional dialogs", and is invisible to the DOM — so assistive
technology, tests and browser automation cannot see or drive it. Ctrl+A went to
the page instead of the field, and the typed replacement landed wherever the
browser decided; hence the truncated "saee" / "sae" names in the original run.
The codebase had already replaced `window.confirm` for exactly these reasons,
with the reasoning written down in `ConfirmDialog.tsx`; `window.prompt` had not
followed.

`components/ui/PromptDialog.tsx` is new — a promise-based `usePrompt()` that
mirrors `useConfirm()`, uses the shared `useModalDialog` hook for Escape, the
focus trap and focus restoration, and **selects the pre-filled text on open** so
typing replaces the old name without reaching for Ctrl+A. `PromptProvider` is
mounted in `App.tsx`, and all eleven `window.prompt` call sites were migrated
across `Reports.tsx`, `WorkspaceTree.tsx`, `AdminOrgUnits.tsx` and `ChatPane.tsx`.
The folder-roles prompt passes `required: false`, because an empty answer is the
documented way to clear the restriction.

**Re-tested:** created a folder through the new dialog, typed a wrong name, hit
Ctrl+A and typed over it — the selection stayed inside the field (page selection
length 0) and the field held exactly the intended text. Renamed the folder: the
dialog opens pre-filled *and* pre-selected with the current name, the rename
saves, and the delete confirmation quotes the new name back correctly. Folder
deleted afterwards.

## BUILD-09 / BUILD-15 — free-layout drag

The reported symptom — a permanently blank canvas surviving a reload — did not
reproduce. On a free-layout page with four widgets, dragging a tile onto another
correctly slid it to the nearest free slot, no widget was pushed off-canvas, no
console errors appeared, and the layout was correct in the API afterwards. It is
worth noting that the QA tooling used in the original run repeatedly timed out
with "the renderer may be frozen or unresponsive" while capturing screenshots,
which produces exactly the blank frame the original report describes.

Investigating it did surface a real defect in the same code path, and that is
fixed. `localLayoutsRef` — the value `onUp` reads to decide what to save — was
synchronised by a `useEffect`, the same stale-ref pattern as the conflict banner
above. On a fast drag, where the last `pointermove` and the `pointerup` land in
one task, `onUp` read the *previous* value; on the first move of a drag that is
`{}`, so `Object.keys(layouts).length` was 0 and the move was silently dropped
instead of saved. `pages/ReportBuilder.tsx` now commits the ref synchronously
through `commitLocalLayouts`, and `loadReport`'s reset clears it synchronously
too.

**Re-tested:** dragged a widget in Free layout from (5,3) to (0,0). The move is
written to the server immediately and survives a full page reload. The canvas is
not blank and shows no placeholders.

## DS-04, UP-01, UP-03 — not defects

These three did not reproduce, and the code shows why the original measurements
missed them. No change was made.

**DS-04.** A calculated column created in the fx editor appears in the Data-tab
table immediately, with correct values, and again after a full page reload
(`revenue * units` → 12000, 5600, 31500, 7600, 1600). The original run compared
the fx list against the table header on a 13-column dataset, where the table
scrolls horizontally and the new column sits off the right edge.

**UP-01 and UP-03.** Both validation messages fire. Clicking Upload with nothing
selected shows "Please select a file and enter a name"; uploading a `.txt`
shows "Unsupported file type: .txt". The toast host is mounted at the React
root, *outside* `<main>` — and the original run measured "the page's visible
text was byte-for-byte unchanged" by reading `<main>`, which can never contain a
toast.

---

## Files changed

```
frontend/src/components/LanguageSwitcher.tsx        type="button" on all three buttons
frontend/src/components/TopBar.tsx                  drop overflow:hidden from <header>
frontend/src/components/report/WidgetRenderer.tsx   loading state; empty-slicer guard
frontend/src/components/report/CrossFilterContext.tsx  empty value set clears
frontend/src/pages/ReportBuilder.tsx                synchronous savingRef + localLayoutsRef
frontend/src/components/ui/PromptDialog.tsx         NEW — in-app replacement for window.prompt
frontend/src/App.tsx                                mount PromptProvider
frontend/src/pages/Reports.tsx                      3 prompt call sites
frontend/src/components/WorkspaceTree.tsx           5 prompt call sites
frontend/src/pages/admin/AdminOrgUnits.tsx          2 prompt call sites
frontend/src/components/chat/ChatPane.tsx           1 prompt call site
frontend/src/test/renderWithProviders.tsx           PromptProvider + answerPrompt() helper
frontend/src/pages/Reports.test.tsx                 driven through the real dialog
frontend/src/components/WorkspaceTree.test.tsx      driven through the real dialog
frontend/src/components/chat/ChatPane.test.tsx      driven through the real dialog
frontend/src/pages/admin/AdminOrgUnits.test.tsx     provider added
frontend/src/pages/loadFailures.test.tsx            provider added
```

The migrated tests no longer stub `window.prompt`. They type into the real field
and press the real button, so a regression that makes the field unreachable —
the DASH-10 defect itself — now fails a test instead of shipping.

## Test suite

`npx vitest run`: **2,417 passing**, 10 failing. The 10 are the four map
cross-filter tests in `WidgetRenderer.test.tsx`, three each in
`SharedReport.test.tsx` and `EmbeddedReport.test.tsx`, and `pwa.test.ts`. All
ten fail identically before and after these changes, in a sandbox checkout that
does not carry `frontend/public` — they need the world-atlas boundary assets and
the service-worker file. They are not related to any change here, but they were
not verified green on a full checkout either, so run the suite locally before
merging.

`npx tsc --noEmit` reports only the four pre-existing errors in
`CopilotChat.test.tsx`, `geo/MapFrame.tsx` and `geo/worldGeometry.ts`.

## Left behind

- `qa/_to_delete/_qa_tmp_frontend.tar.gz` — a temporary archive used to run the
  test suite in a Linux sandbox, because `frontend/node_modules` on this machine
  is a Windows install and `vitest` cannot start from it. Delete the
  `qa/_to_delete/` folder; nothing else needs it.
- `QA scratch — copilot test` (report 191) has three extra widgets (line, pie,
  donut) added while reproducing the free-layout drag, and its page is left in
  Free layout.
- `QA Sample 2135` (dataset 174) has a calculated column `qa_calc_total`
  (`revenue * units`) added for the DS-04 check.
