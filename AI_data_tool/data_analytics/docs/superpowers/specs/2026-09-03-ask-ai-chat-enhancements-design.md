# Ask AI chat: results, history, follow-ups — design

Date: 2026-09-03. Status: implemented 2026-09-03 (all sections below except
the stated deferral). Scope: the eight enhancements requested for the Ask AI
screen after the screenshots of 2026-09-03 (see the conversation record).

## What is wrong today (verified in code)

- `ChatPane` keeps messages only in React state. It resumes the newest
  server conversation by id but never loads its messages; no endpoint returns
  them.
- `/agent/conversations/{cid}/ask` returns only `answer` text. Result rows
  never reach the browser; `GET /agent/runs/{id}` carries a row COUNT.
- `classify` and `generate_sql` see the current question only. "execute it",
  "present a table", "as a chart" are classified as new, vague questions.
- Titles are always "New conversation"; there is no rename or delete.

## Design

### 1. Rows travel with the answer (backend)

- `AgentStep.result_rows` (JSON, nullable): for SINK steps only, a capped
  snapshot `{columns: [..], rows: [[..]..], total: n, truncated: bool}`.
  Cap `RESULT_ROW_CAP = 200` rows. Cells pass through a JSON-safe scalar
  coercion (Decimal/numpy → number, datetime → ISO string, NaN → null).
  Intermediate steps stay null: their rows exist only to feed a later step.
- `AgentRun.context_objects` (JSON, nullable): the retrieval-ranked object
  names the context put first for this question (item 6, "ranked tables").
- `AgentRun.presentation` (JSON, nullable): `{format, limit}` for a
  presentation-only follow-up run (§3); null for a data run.
- Migration `0017_agent_results.py` adds the three columns; `main._migrate`
  gets the matching `ADD COLUMN IF NOT EXISTS` lines for running installs.
- `/ask` response gains `results` (the sink snapshots), `sql` (sink SQL
  list) and `presentation` (see §3). `GET /runs/{id}` gains `result_rows`
  per step and `context_objects`.

### 2. History is read back (backend + frontend)

- `GET /agent/conversations/{cid}/messages` → owner-only (404 otherwise,
  same rule as every other conversation route). Each message:
  `{id, role, content, created_at, run: {id, status, intent, error,
  results, sql, presentation} | null}`.
- `PATCH /agent/conversations/{cid}` `{title}` and
  `DELETE /agent/conversations/{cid}` (204; messages cascade, runs keep
  their rows with `conversation_id` set null by the FK).
- `GET /agent/conversations` gains `created_at`.
- First question titles the conversation: when the title is empty or the
  default "New conversation", `/ask` sets it to the question (80 chars).

### 3. Follow-ups and presentation intents (agent)

New node `nodes/followup.py: resolve(question, history, has_result, client)`
runs only when the conversation has earlier turns. JSON contract:

```
{kind: "data" | "presentation",
 question: string,            # standalone rewrite for data
 format: "table"|"bar"|"line"|"pie"|"csv"|null,
 limit: integer|null}
```

- `presentation` + a previous result exists → the run copies that result's
  snapshot (optionally sliced to `limit`) into its own step, answers with a
  one-line confirmation, `status=ok`, `intent=present`, and stores
  `presentation={format, limit}`. No classify, plan, SQL or explain.
- `presentation` with no previous result, or `data` → continue with the
  rewritten standalone question. `classify` and `generate_sql` also receive
  a compact "Conversation so far" block (last turns + last SQL) so context
  survives even if the rewrite is conservative.
- The router loads the last `HISTORY_TURNS = 6` messages BEFORE adding the
  new user message (otherwise autoflush would put the current question into
  its own history), ordered by `id` (user and assistant turns of one request
  share a timestamp), each with its run's sink SQL and result snapshots, and
  passes `history=[{role, content, sql, results}]` to `run_agent`. The most
  recent assistant entry with a non-empty `results` is the "previous result"
  a presentation follow-up re-shows.
- A presentation run carries the source run's SQL on its step so "Show SQL"
  still works, but it is never written to `query_examples`: the remember
  path is guarded on the run not being a presentation run, or "as a table"
  would be stored as a verified example for that SQL.
- Resolver failure (no JSON) degrades to today's behaviour: the question is
  used as typed, no presentation.

### 4. Clarify less (agent prompts)

`classify`: a request to SEE the data — a sample, the first N rows, "what
does this data have", all columns — over the selected scope is a plain
`lookup`, never ambiguous. Examples added to the few-shot block.
`generate_sql`: such a request is `SELECT` of the listed columns (explicit
list) with `LIMIT N`, default 10.

### 5. Frontend

- `agentApi`: `messages`, `rename`, `remove`; `AgentAnswer` gains `results`,
  `sql`, `presentation`; conversation rows gain `created_at`.
- `ChatPane` props: `conversationId?: number | null` and
  `onConversationCreated?`. Given a number it loads that conversation's
  messages on mount/change; given `null` it creates one on the first send
  and reports it; given `undefined` it keeps today's find-or-create path
  (the report-builder mount is untouched).
- Assistant messages render: the answer, then a `ResultGrid` (columns, rows,
  "N rows, showing M") or, for `presentation.format` of bar/line/pie, the
  existing chart renderers over `{name, value}` rows. Actions: Show SQL,
  Copy SQL, Download CSV, 👍/👎. "Tables considered" appears inside the
  SQL panel when `context_objects` is present.
- `AskAI` page: a conversation list for the current scope (title, date,
  New chat, rename, delete) beside the pane; selecting one loads it.
- Colours move to theme tokens (`var(--surface2)` etc.) so the pane reads
  in both themes; bubbles keep their shapes.

### Not in scope, stated plainly

"Add this result to a dashboard" needs a widget that can hold an arbitrary
SQL result; the platform's widgets all query a dataset through the widget
data pipeline. That is a new widget type and a separate task. Download CSV
and Copy SQL cover the immediate need.

## Tests

- Backend: messages/rename/delete owner-only probes; `/ask` returns results
  and sql and titles the conversation; history reaches `run_agent`;
  snapshots capped and stored on sink steps only; presentation follow-up
  skips SQL and copies rows; resolver contract; classify/generate prompt
  pins for the sample rule.
- Frontend: grid renders from `results`; history loads for a given id; copy
  SQL and CSV download; chart presentation; sidebar list/new/rename/delete.
