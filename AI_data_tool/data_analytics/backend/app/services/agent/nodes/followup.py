"""A new message, read against the conversation so far.

Before this node every message was classified cold. The screenshots that
motivated it: "execute query and i need to see result" and "can you present
a table" -- both about a result that already existed -- came back as "needs
more detail", and "do you have a chat history" was taken for a question
about a table called chat history.

Four kinds, one JSON contract:

- `presentation`: the message only wants the LAST RESULT shown differently
  (a table, a chart, a CSV, fewer rows). The graph re-shows the rows it
  already has; nothing is classified, planned or queried.
- `describe`: the message wants the LAST RESULT EXPLAINED -- "explain this
  chart", "what does this mean", "summarise that". It needs no new data
  either: the rows are already here, and the answer is prose about them.
  Before this kind existed the word "explain" reached classify, which has an
  `explain` intent meaning the key-influencers ANALYSIS, and "explain this
  chart" came back as "the response needs at least two distinct numeric
  values" -- an answer to a question nobody asked.
- `chat`: the message asks nothing at all -- "thanks", "ok", "what can you
  do". The first message of a thread reaches classify's `chat` intent for
  this; a later one has to be caught here, or it is rewritten into a
  standalone data question and queried. Both doors, or neither works.
- `data`: the message needs a query. It is rewritten as ONE standalone
  question carrying over what it leans on from earlier turns ("the same for
  Cairo" → "how many orders per city, for Cairo only"), so classify, plan
  and generate keep seeing complete questions -- their contracts do not
  change, they just stop being handed fragments.

Runs only when there IS a conversation; the first question in a thread is
never a follow-up.
"""
from __future__ import annotations

FOLLOWUP_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string",
                 "enum": ["data", "presentation", "describe", "chat"]},
        "question": {"type": "string"},
        # No enum here: a null inside an enum is the kind of shape a strict
        # provider-side schema mode rejects, and a rejected schema would make
        # this whole node silently vanish (resolve returns None, the run
        # proceeds cold). The value set is enforced in `resolve` instead.
        "format": {"type": ["string", "null"]},
        "limit": {"type": ["integer", "null"]},
        # The two columns a chart message named, when it named them ("chart
        # revenue by region"). No enum: the column list is per-result, and a
        # name that is not a column of THIS result is dropped by
        # charts.validated_axes rather than trusted.
        "x": {"type": ["string", "null"]},
        "y": {"type": ["string", "null"]},
    },
    "required": ["kind", "question", "format", "limit", "x", "y"],
    "additionalProperties": False,
}

FORMATS = ("table", "bar", "line", "pie", "csv")

#: What one turn may contribute to the block, and what the whole block may
#: take -- bounded so a long chat never grows the prompt without limit.
_TURN_CHARS = 400
_BLOCK_CHARS = 1800

_EXAMPLES = """Examples, after a conversation where the user asked "orders per city" and the assistant answered from SQL that returned 2 rows:
New message: can you present a table -> {"kind": "presentation", "question": "Show the orders per city as a table", "format": "table", "limit": null, "x": null, "y": null}
New message: as a bar chart -> {"kind": "presentation", "question": "Show the orders per city as a bar chart", "format": "bar", "limit": null, "x": null, "y": null}
New message: download it as csv -> {"kind": "presentation", "question": "Download the orders per city as CSV", "format": "csv", "limit": null, "x": null, "y": null}
New message: execute the query and show me the result -> {"kind": "presentation", "question": "Show the rows the orders per city query returned", "format": "table", "limit": null, "x": null, "y": null}
New message: only the first one -> {"kind": "presentation", "question": "Show the first row of the orders per city result", "format": "table", "limit": 1, "x": null, "y": null}
New message: chart for samples -> {"kind": "presentation", "question": "Draw the orders per city result as a chart", "format": "bar", "limit": null, "x": null, "y": null}
New message: Chart n by city -> {"kind": "presentation", "question": "Draw n by city as a bar chart", "format": "bar", "limit": null, "x": "city", "y": "n"}
New message: plot revenue against month as a line -> {"kind": "presentation", "question": "Draw revenue by month as a line chart", "format": "line", "limit": null, "x": "month", "y": "revenue"}
-- when the message NAMES the two columns, `x` is the one that labels the
-- marks and `y` the one that sizes them -- "chart Y by X". Copy the names
-- exactly as written; leave both null when the message does not say.
New message: give me some suggested charts -> {"kind": "presentation", "question": "Draw the orders per city result as a chart", "format": "bar", "limit": null, "x": null, "y": null}
-- asking to CHART, PLOT or VISUALISE what was just shown -- or for chart
-- suggestions about it -- re-draws the LAST RESULT as a chart (bar unless
-- another type is named). It is never a query against a table that happens
-- to be called "charts".
New message: explain this chart -> {"kind": "describe", "question": "Explain the orders per city result", "format": null, "limit": null, "x": null, "y": null}
New message: what does this mean -> {"kind": "describe", "question": "Explain the orders per city result", "format": null, "limit": null, "x": null, "y": null}
-- asking what the LAST RESULT MEANS, or to explain, interpret, summarise or
-- comment on it, is answered in words from rows that already exist. It needs
-- no query, and "explain" here does not mean a statistical analysis.
New message: i need chart -> {"kind": "presentation", "question": "Draw a chart of this data", "format": "bar", "limit": null, "x": null, "y": null}
-- a request to CHART, PLOT, VISUALISE or draw a widget is ALWAYS
-- presentation, even when nothing has been queried yet and even when it
-- names no columns. It is never chat: it asks for something to be done with
-- the data. WHAT to draw is settled after this, from the data itself.
New message: what does this data contain -> {"kind": "data", "question": "what does this data contain", "format": null, "limit": null, "x": null, "y": null}
New message: describe this dataset -> {"kind": "data", "question": "describe this dataset", "format": null, "limit": null, "x": null, "y": null}
-- a question about what the DATA is, not about you. Measured live: the same
-- question was answered from the catalog on one turn and with real counts on
-- another, purely because of how it was worded. It is a data question every
-- time.
New message: thanks -> {"kind": "chat", "question": "thanks", "format": null, "limit": null, "x": null, "y": null}
New message: ok great, what can you do -> {"kind": "chat", "question": "ok great, what can you do", "format": null, "limit": null, "x": null, "y": null}
-- a message that asks nothing about the data: a greeting, a thank-you, small
-- talk, a question about you. `question` comes back exactly as typed; there
-- is nothing to rewrite. A message that DOES ask for data is never chat, even
-- when it is wrapped in politeness.
New message: the same for Cairo only -> {"kind": "data", "question": "How many orders are there per city, for the city Cairo only?", "format": null, "limit": null, "x": null, "y": null}
New message: show 50 rows -> {"kind": "data", "question": "Show the first 50 rows of orders per city", "format": null, "limit": null, "x": null, "y": null}
-- more rows than the last result returned is a new query, not a re-show.
New message: what is the total revenue by region -> {"kind": "data", "question": "what is the total revenue by region", "format": null, "limit": null, "x": null, "y": null}
-- already standalone: returned unchanged."""


def render_history(history: list[dict] | None) -> str:
    """The conversation as a compact block: each turn's text, and for an
    assistant turn the SQL it ran and how many rows came back. The row count
    is what lets "show 5 rows" (re-show) be told from "show 500 rows" (a new
    query). Newest turns are kept when the budget runs out."""
    lines: list[str] = []
    used = 0
    for turn in reversed(history or []):
        who = "User" if turn.get("role") == "user" else "Assistant"
        text = str(turn.get("content") or "").strip().replace("\n", " ")
        if len(text) > _TURN_CHARS:
            text = text[:_TURN_CHARS] + "…"
        entry = [f"{who}: {text}"]
        sqls = [s for s in (turn.get("sql") or []) if s]
        if sqls:
            entry.append("  SQL: " + " ; ".join(s.replace("\n", " ") for s in sqls))
        results = turn.get("results") or []
        if results:
            entry.append("  (" + ", ".join(
                f"returned {r.get('total', 0)} rows" for r in results) + ")")
        chunk = "\n".join(entry)
        if used + len(chunk) > _BLOCK_CHARS:
            break
        used += len(chunk) + 1
        lines.append(chunk)
    return "\n".join(reversed(lines))


def _rows(result: dict) -> int:
    return result.get("total") or 0


def last_result(history: list[dict] | None, *,
                chartable: bool = False) -> dict | None:
    """The most recent assistant turn whose result actually HAS rows -- the
    thing a presentation follow-up re-shows. Empty results are skipped, not
    just missing ones: traced live, a query against an (aptly named, empty)
    `charts` table produced a 0-row "result", and "chart for samples" then
    re-showed nothing instead of reaching back to the sample the user meant.
    You cannot chart nothing; the turn before it is what they are pointing
    at. None when the conversation has produced no rows at all.

    `chartable=True` additionally skips a turn whose only rows came from the
    CATALOG -- the listing behind "what is this data", whose columns are
    `column`/`type`/`description`. Those rows describe the data; they are not
    the data. Traced live over four turns: after a describe, "i need suggest
    charts", "btwen region and count" and "dount" each tried to chart the
    listing, each refused with "only column, type varies", and each offered
    the same "Show the rows as a table" -- which showed the listing again.
    The person broke the loop by pasting their own numbers into the chat.
    A chart request is about the DATA, so it must reach past the description
    to the last real result, or to no result at all -- which sends it to
    `_chart_from_scratch`, where the dataset itself is read.
    """
    for turn in reversed(history or []):
        if turn.get("role") != "assistant":
            continue
        results = turn.get("results") or []
        if chartable:
            results = [r for r in results if r.get("source") != "catalog"]
        if any(_rows(r) > 0 for r in results):
            return turn
    return None


async def resolve(question: str, history: list[dict], client) -> dict | None:
    """`{kind, question, format, limit}`, or None when the model could not
    be reached or never satisfied the contract -- the caller then proceeds
    with the message as typed, which is exactly today's behaviour."""
    got = await client.complete_json(
        [{"role": "system", "content": (
            "You read a NEW chat message against the conversation so far, "
            "for an agent that answers questions about a database by "
            "writing SQL.\n"
            "Return kind=\"presentation\" when the message only asks to "
            "SHOW THE LAST RESULT DIFFERENTLY and needs no new data: as a "
            "table or grid, as a chart (bar, line, pie) -- including 'chart "
            "this', 'suggest charts', 'visualise it' -- as a CSV / download "
            "/ export, 'execute it and show the result' when that result "
            "already exists, or FEWER rows than the last result returned. "
            "Set `format` to table, bar, line, pie or csv and `limit` to the "
            "number of rows asked for (else null); `question` restates the "
            "request briefly.\n"
            "Return kind=\"describe\" when the message asks what the LAST "
            "RESULT MEANS rather than for new data: 'explain this chart', "
            "'what does this mean', 'summarise that', 'is that good'. "
            "`format` and `limit` are null; `question` restates the request "
            "briefly.\n"
            "Return kind=\"chat\" when the message asks nothing about the "
            "data at all: a greeting, a thank-you, small talk, or a question "
            "about you and what you can do. `question` comes back exactly as "
            "typed, `format` and `limit` null. A message that asks for data "
            "is never chat, however politely it is wrapped — and a "
            "message asking for a chart, plot, graph, widget or "
            "visualisation is never chat either: it is a presentation, "
            "even when nothing has been shown yet and even when it does "
            "not say what to draw. Asking what the DATA is — describe this "
            "data, what does it contain, what tables or columns are there — "
            "is a data question, not chat: chat is only for messages about "
            "YOU or about nothing.\n"
            "Return kind=\"data\" for anything that needs a query: a new "
            "question, or a follow-up that leans on earlier turns ('it', "
            "'that', 'the same for Cairo', 'now by month', more rows than "
            "were returned). Rewrite `question` as ONE complete standalone "
            "question carrying over every table, column, filter, limit and "
            "metric it depends on, in the earlier turns' exact words. A "
            "message that already stands alone comes back unchanged. Never "
            "invent tables, columns or filters the conversation did not "
            "mention. `format`, `limit`, `x` and `y` are null for data.\n"
            "`x` and `y` are set ONLY when a chart message names the two "
            "columns to use -- `x` labels the marks, `y` sizes them, as "
            "in \"chart Y by X\". Copy the names exactly as the message "
            "wrote them; never guess a column it did not name.\n" + _EXAMPLES)},
         {"role": "user", "content": (
             f"Conversation so far:\n{render_history(history)}\n\n"
             f"New message: {question}")}],
        FOLLOWUP_SCHEMA, enforce=True, max_tokens=300, temperature=0.0)
    if not got:
        return None
    kind = got.get("kind")
    rewritten = str(got.get("question") or "").strip() or question
    limit = got.get("limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        limit = None
    charting = str(got.get("format") or "").lower() in ("bar", "line", "pie")
    if (kind in ("presentation", "describe") and not charting
            and last_result(history) is None):
        # Nothing to re-show or explain: asking the database is the only
        # honest move. Both kinds answer FROM rows, so both need rows.
        #
        # A CHART is the exception and stays `presentation`: "i need chart"
        # before anything has been queried is not a vague new question -- it
        # is a request whose missing piece, which two columns, the graph
        # settles from the data or asks about. Sent through as `data` it came
        # back as an invented question or, worse, as small talk: "I can't
        # generate charts directly", said by a product whose job is charts.
        kind = "data"
    if kind == "chat":
        # Nothing to rewrite -- there is no question in it to make standalone,
        # and the reply is to what was actually typed.
        return {"kind": "chat", "question": question, "format": None,
                "limit": None, "x": None, "y": None}
    if kind == "describe":
        return {"kind": "describe", "question": rewritten,
                "format": None, "limit": None, "x": None, "y": None}
    if kind != "presentation":
        return {"kind": "data", "question": rewritten, "format": None,
                "limit": None, "x": None, "y": None}
    fmt = str(got.get("format") or "table").lower()

    def axis(key):
        """The column name as the message wrote it, or None.

        Not checked against a column list here -- this node does not know
        which columns the result has. charts.validated_axes does that, and
        drops anything that is not one of them."""
        value = got.get(key)
        return (str(value).strip() or None) if isinstance(value, str) else None

    return {"kind": "presentation", "question": rewritten,
            "format": fmt if fmt in FORMATS else "table", "limit": limit,
            "x": axis("x"), "y": axis("y")}
