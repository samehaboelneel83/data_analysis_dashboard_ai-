# Dashboard copilot: edit the page in plain language — design

Date: 2026-09-03. Status: implemented 2026-09-03, live-verified against the
running app (auto-reload update, chart creation, data-question delegation,
DirectQuery source routing). Requested: a chatbot on the dashboard
builder that opens without freezing the page, uses the same LLM endpoint,
sees what the user sees, and can create and edit dashboard charts on request.

## Shape

A floating button on the report builder (edit mode, users with edit rights)
opens a chat panel. Each message goes to one new endpoint; the reply comes
back with the list of page edits the model made, and the builder reloads.
The panel is component state: nothing blocks the canvas, requests are async,
history lives in the panel for the session (this is a command surface, not a
stored conversation — unlike Ask AI, whose threads are the record of
answers; a page edit's record is the page itself plus report revisions).

## Backend

`POST /reports/{report_id}/pages/{page_id}/copilot` (new router module
`report_copilot.py`), body `{message, history?}` where history is the
panel's last few turns `[{role, content}]`.

- Auth: identical to the widget CRUD endpoints (`check_org` on the report,
  page-belongs-to-report), so the copilot can do exactly what the GUI can,
  nothing more. Counted against the same daily agent quota.
- Context is built SERVER-side (authoritative, not trusted from the client):
  report + page name, every widget on the page (id, type, title, the config
  keys the GUI writes, layout), and the report's dataset columns with dtypes
  (via the agent's existing dataset context loader; primary +
  additional_dataset_ids).
- One LLM call through `llm_service.get_client().complete_json` (the same
  configured endpoint everything else uses), `enforce=True`, contract:

```
{reply: string,
 data_question: string|null,          # set when the message asks about DATA
 actions: [{op: create|update|delete,
            widget_type: string|null, widget_id: int|null,
            title: string|null,
            config: object|null,      # scalar values only
            layout: object|null}]}    # x,y,w,h — integers
```

- **Nothing on this page is refused** (amended after the user showed the data
  chat rejecting "change Auto-reload (seconds) to 1 minute" as
  not-answerable-by-SQL). A page command becomes `actions`. A DATA question
  sets `data_question` (rewritten standalone) and the router delegates it to
  the existing `run_agent` over the report's datasets — no stored
  conversation — returning the answer and its result snapshots in the copilot
  response (`results`), which the panel draws with the same grid the chat
  uses. The two are exclusive per reply.

- Actions are validated then applied in one transaction, mirroring the GUI
  endpoints: create places at the bottom of the canvas with the catalog's
  default size for the type (backend copy of WIDGET_CATALOG defaults for the
  supported subset); update merges config; delete removes. One revision bump.
- Validation is per-action and forgiving: an unknown widget type, a column
  not in the dataset, or a widget id not on the page SKIPS that action and
  appends a note to the reply — the model's other edits still land, and the
  user reads why one did not.
- Config values are limited to SCALARS (string/number/bool/null) — that
  covers dimension/measure/agg, titles, axis labels and bounds, flags, and
  settings like `auto_reload_seconds`; structured settings (filters, display
  rules) stay in the GUI. Keys are open, not allowlisted — the model sees
  each widget's real config keys in context — except `dataset_id`, which is
  dropped from patches. `dimension`/`dimension2`/`measure`/`measure2` values
  are validated against the dataset's columns; a miss skips the action with
  a note.
- Model failure (no JSON): 502; the panel shows an honest error.

New node `services/agent/nodes/copilot.py` holds the prompt and contract —
pure, tested with a fake client like every other node.

## Frontend

- `reportsApi.copilot(reportId, pageId, {message, history})`.
- `components/report/CopilotChat.tsx`: fixed bottom-corner button (Bot icon)
  + panel (≈360px, messages, input, busy state). On a reply with applied
  actions it calls `onApplied` — the builder passes `loadReport`, so the
  canvas redraws the new state. Failures render in the panel, never block it.
- Mounted from ReportBuilder only (the "dashboard page"), only when the user
  can edit and is in edit mode.

## Out of scope, said plainly

Undo (the report revision counter and existing GUI flows are the recovery
path), cross-page edits, page/theme-level actions, and persisting copilot
chats. The action set is create/update/delete of widgets on the open page.

## Tests

Backend: node contract (schema, context carries widgets+columns+history);
router — create lands with placement and revision bump, update merges,
delete removes, unknown column/type/id are skipped with notes, cross-org
404, quota enforced, model-failure 502. Frontend: panel opens, sends
message+history, shows reply, calls onApplied only when actions applied,
error path, busy state.
