# Layer 4 — AI Agent Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Question in, correct answer out — a DAG-based agent that plans, generates SQL, validates through the V1–V5 ladder, repairs boundedly, executes with row policies injected into the AST, and answers with provenance.

**Architecture:** A hand-rolled asyncio executor runs a typed step DAG in topological layers under one bounded gate (task parallelism); several runs may proceed at once (agent parallelism). Every LLM contract uses `response_format: json_schema` — the one mechanism verified as grammar-enforced on this endpoint. V3 admits only `confirmed`/`declared` joins; row policies are injected into the sqlglot AST, never concatenated, never post-filtered.

**Tech Stack:** FastAPI, SQLAlchemy (async), sqlglot (the only new dependency), the existing `services/llm.py` client against vLLM/Qwen at `http://10.125.18.189:8000/v1`, React + vitest for the chat pane.

**Spec:** `docs/superpowers/specs/2026-08-25-layer-4-agent-orchestration-design.md` — read it first; every decision below argues from it.

## Global Constraints

- **No git repository exists.** Wherever this plan says "Checkpoint", run the named test command instead of committing. Durability = files on disk.
- **All backend tests run in Docker:**
  `docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <args>`
  (run from PowerShell; Git Bash mangles the volume path).
- **BOM files:** `app/models/models.py`, `app/main.py`, `app/core/config.py` must be read AND written with `encoding="utf-8-sig"`. Everything else is plain `utf-8`.
- **Additive only.** No table renamed, no existing service rewritten, no existing test weakened. Baseline: **1769 backend + 707 frontend tests pass**; they must still pass after every task.
- **Org scoping returns 404, never 403** for cross-org access (`check_org` convention — 403 confirms existence).
- **LLM JSON contracts**: always `response_format: {type: "json_schema", ...}` via the new `complete_json(..., enforce=True)` from Task 3. Never `guided_json` (silently ignored by the endpoint), never prompt-begging alone.
- **New settings** follow the existing style: lowercase, `Field(default=..., ge=...)`, with a comment carrying the measured rationale (`app/core/config.py`).
- **Existing symbols this plan consumes** (verified signatures):
  - `LLMClient.complete(messages, *, max_tokens=1024, temperature=0.2) -> str | None`
  - `LLMClient.complete_json(messages, schema, *, retries=2, max_tokens=1024, temperature=0.2) -> dict | None`
  - `llm_service.get_client() -> LLMClient` (`app/services/llm.py:254`)
  - `get_engine(cfg) -> Engine` / `get_metadata_engine(cfg) -> Engine` (`app/services/direct_query.py`)
  - `store.CONFIRMED / DECLARED / INFERRED` (`app/services/metadata/store.py:42-44`)
  - `SourceObject`, `SourceColumn`, `SourceRelationship`, `ColumnStats` (`app/models/models.py`)
  - `check_org(obj, user, msg)` (`app/core/org_scope.py`), `get_db`, `get_current_user` (`app/dependencies.py`)
  - Async test fixtures: `db_session` (from `tests/conftest.py`, `expire_on_commit=False`)

---

### Task 1: sqlglot dependency + test image rebuild

**Files:**
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_agent_deps.py`

**Interfaces:**
- Produces: `import sqlglot` works everywhere; `sqlglot.parse_one(sql, dialect=...)` available to Tasks 7, 8, 10.

- [ ] **Step 1: Add the dependency**

Append to `backend/requirements.txt`:

```
sqlglot>=25.0
```

- [ ] **Step 2: Rebuild the test image and the running backend**

Run (PowerShell):
```powershell
docker build -t datalytics-backend:test "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics\backend"
docker exec datalytics_backend pip install "sqlglot>=25.0"
```

- [ ] **Step 3: Write the guard test**

`backend/tests/test_agent_deps.py`:

```python
"""sqlglot is the agent's one new dependency — and its only parser.

The spec (F4) forbids string concatenation and post-filtering for row
policies; sqlglot's AST is the mechanism. If this import breaks, every
ladder rung V1-V5 breaks with it, so it gets its own loud test.
"""


def test_sqlglot_is_importable_and_parses():
    import sqlglot

    tree = sqlglot.parse_one("SELECT a FROM t WHERE b = 1", dialect="postgres")
    assert tree is not None
    assert "SELECT" in tree.sql(dialect="postgres").upper()


def test_sqlglot_round_trips_a_join():
    import sqlglot

    sql = "SELECT o.id FROM orders AS o JOIN customers AS c ON o.customer_id = c.id"
    rendered = sqlglot.parse_one(sql, dialect="postgres").sql(dialect="postgres")
    assert "JOIN" in rendered.upper()
```

- [ ] **Step 4: Run it**

Run: `... python -m pytest tests/test_agent_deps.py -q`
Expected: 2 passed.

- [ ] **Step 5: Checkpoint** — full suite still green: `... python -m pytest -q` → 1771 passed (1769 + 2), 3 skipped.

---

### Task 2: Data model — six new tables

**Files:**
- Modify: `backend/app/models/models.py` (**utf-8-sig**)
- Test: `backend/tests/test_agent_models.py`

**Interfaces:**
- Produces (ORM classes, exact names): `Conversation`, `AgentMessage`, `AgentRun`, `AgentStep`, `QueryExample`, `ObjectRowPolicy`. All later tasks import these from `app.models.models`.
- New tables are created by the existing `create_all` on startup — **no `_migrate` lines needed** (those are only for new columns on existing tables).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_agent_models.py`:

```python
"""The agent's data model.

`agent_steps` is not optional bookkeeping (spec, Data model section): without
a per-node record of what SQL ran, what the ladder rejected and how many
repairs it took, neither the eval gate nor a support conversation has
anything to work from.
"""
import pytest
from sqlalchemy import select

from app.models.models import (AgentMessage, AgentRun, AgentStep, Conversation,
                               DataSource, ObjectRowPolicy, Organization,
                               QueryExample, Role, User)


@pytest.fixture
async def org(db_session):
    o = Organization(name="Acme")
    db_session.add(o)
    await db_session.flush()
    return o


class TestConversationShape:
    async def test_a_conversation_belongs_to_an_org_and_user(self, db_session, org):
        role = Role(name="analyst", org_id=org.id)
        db_session.add(role)
        await db_session.flush()
        user = User(email="a@corp.com", hashed_password="x",
                    org_id=org.id, role_id=role.id)
        db_session.add(user)
        await db_session.flush()

        conv = Conversation(org_id=org.id, user_id=user.id, title="Revenue Qs")
        db_session.add(conv)
        await db_session.commit()

        row = (await db_session.execute(select(Conversation))).scalar_one()
        assert row.org_id == org.id
        assert row.title == "Revenue Qs"

    async def test_messages_cascade_with_their_conversation(self, db_session, org):
        conv = Conversation(org_id=org.id, user_id=None, title="t")
        db_session.add(conv)
        await db_session.flush()
        db_session.add(AgentMessage(conversation_id=conv.id, role="user",
                                    content="how many orders?"))
        await db_session.commit()
        await db_session.delete(conv)
        await db_session.commit()
        assert (await db_session.execute(select(AgentMessage))).scalars().all() == []


class TestRunRecord:
    async def test_a_run_records_plan_answer_and_status(self, db_session, org):
        run = AgentRun(org_id=org.id, question="total sales by city",
                       status="ok", intent="aggregate",
                       plan=[{"id": "s1", "question": "total sales by city"}],
                       answer="Sales total 12,400 across 3 cities.")
        db_session.add(run)
        await db_session.commit()
        row = (await db_session.execute(select(AgentRun))).scalar_one()
        assert row.plan[0]["id"] == "s1"
        assert row.status == "ok"

    async def test_a_step_records_what_the_ladder_did(self, db_session, org):
        run = AgentRun(org_id=org.id, question="q", status="ok")
        db_session.add(run)
        await db_session.flush()
        db_session.add(AgentStep(
            agent_run_id=run.id, node="s1", status="ok",
            sql="SELECT count(*) FROM orders", rows_returned=1,
            validation_failures=[{"rung": "V2", "detail": "no such column x"}],
            repair_attempts=1, ms=840))
        await db_session.commit()
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.validation_failures[0]["rung"] == "V2"
        assert step.repair_attempts == 1


class TestPolicyAndMemory:
    async def test_a_row_policy_binds_role_to_source_object(self, db_session, org):
        role = Role(name="viewer", org_id=org.id)
        ds = DataSource(name="s", type="postgresql", org_id=org.id, config={})
        db_session.add_all([role, ds])
        await db_session.flush()
        from app.models.models import SourceObject
        obj = SourceObject(data_source_id=ds.id, org_id=org.id,
                           name="orders", kind="table")
        db_session.add(obj)
        await db_session.flush()

        db_session.add(ObjectRowPolicy(org_id=org.id, source_object_id=obj.id,
                                       role_id=role.id,
                                       predicate="region = 'west'"))
        await db_session.commit()
        pol = (await db_session.execute(select(ObjectRowPolicy))).scalar_one()
        assert pol.predicate == "region = 'west'"

    async def test_query_examples_store_the_verified_pair(self, db_session, org):
        db_session.add(QueryExample(org_id=org.id, question="orders per city",
                                    sql="SELECT city, count(*) FROM orders GROUP BY city"))
        await db_session.commit()
        ex = (await db_session.execute(select(QueryExample))).scalar_one()
        assert "GROUP BY" in ex.sql
```

- [ ] **Step 2: Run to verify it fails**

Run: `... python -m pytest tests/test_agent_models.py -q`
Expected: ImportError — `Conversation` not defined.

- [ ] **Step 3: Add the models**

Append to `backend/app/models/models.py` (read/write **utf-8-sig**; match the file's existing column-alignment style):

```python
class Conversation(Base):
    """One chat thread in the report builder. Messages cascade with it."""
    __tablename__ = "conversations"
    id             = Column(Integer, primary_key=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True)
    title          = Column(String(200), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)


class AgentMessage(Base):
    """`messages` in the spec — prefixed to avoid colliding with notification
    models. role: user | assistant | system."""
    __tablename__ = "agent_messages"
    id              = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role            = Column(String(20), nullable=False)
    content         = Column(Text, nullable=False)
    agent_run_id    = Column(Integer, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


class AgentRun(Base):
    """One question's journey through the graph. status: ok | failed |
    needs_clarification."""
    __tablename__ = "agent_runs"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    question        = Column(Text, nullable=False)
    status          = Column(String(30), nullable=False, default="running")
    intent          = Column(String(30), nullable=True)
    plan            = Column(JSON, nullable=True)
    answer          = Column(Text, nullable=True)
    error           = Column(Text, nullable=True)
    ms              = Column(Integer, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


class AgentStep(Base):
    """Per-node evidence. Without this neither the eval gate nor a support
    conversation has anything to work from."""
    __tablename__ = "agent_steps"
    id                  = Column(Integer, primary_key=True)
    agent_run_id        = Column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    node                = Column(String(80), nullable=False)
    status              = Column(String(30), nullable=False)
    sql                 = Column(Text, nullable=True)
    rows_returned       = Column(Integer, nullable=True)
    validation_failures = Column(JSON, nullable=True)
    repair_attempts     = Column(Integer, nullable=False, default=0)
    ms                  = Column(Integer, nullable=True)


class QueryExample(Base):
    """Verified question→SQL memory (spec: memory.py reads and writes this)."""
    __tablename__ = "query_examples"
    id             = Column(Integer, primary_key=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=True)
    question       = Column(Text, nullable=False)
    sql            = Column(Text, nullable=False)
    confirmed_by   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)


class ObjectRowPolicy(Base):
    """Row policy keyed to a SOURCE OBJECT, not a dataset (spec F3).

    `RowSecurityRule` above cannot bind to agent SQL: the agent queries the
    catalog with arbitrary joins, and no dataset exists for that. The
    predicate is a SQL boolean expression injected into the parsed AST by
    agent/policy.py — never concatenated, never post-filtered (spec F4).
    """
    __tablename__ = "object_row_policies"
    id               = Column(Integer, primary_key=True)
    org_id           = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_object_id = Column(Integer, ForeignKey("source_objects.id", ondelete="CASCADE"), nullable=False)
    role_id          = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    predicate        = Column(Text, nullable=False)
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__   = (UniqueConstraint("source_object_id", "role_id",
                                         name="uq_object_role_policy"),)
```

- [ ] **Step 4: Run to verify it passes** — `... pytest tests/test_agent_models.py -q` → all pass.

- [ ] **Step 5: Checkpoint** — `... pytest tests/test_agent_models.py tests/test_catalog_sync.py -q` (models file was touched; catalog tests prove nothing broke).

---

### Task 3: The global LLM gate + enforced JSON contract

**Files:**
- Modify: `backend/app/services/llm.py`
- Modify: `backend/app/core/config.py` (**utf-8-sig**)
- Modify: `backend/app/services/metadata/catalog_sync.py` (describe stage rewires to the gate)
- Test: `backend/tests/test_llm_gate.py`

**Interfaces:**
- Produces: `LLMClient.complete(..., background: bool = False)` and `complete_json(..., background: bool = False, enforce: bool = False)`. `enforce=True` sends `response_format: {type:"json_schema"}` (F2). Module function `llm_gate_state() -> dict` for tests/observability.
- Settings: `llm_max_concurrency: int = 12`, `llm_reserved_interactive: int = 2`.
- Consumes: nothing new.

Design (spec F5, reserved-headroom option): one per-event-loop semaphore of `llm_max_concurrency` slots. `background=True` callers additionally hold a second semaphore of `llm_max_concurrency - llm_reserved_interactive` slots — so background work can never occupy the last `llm_reserved_interactive` slots, and an interactive question never queues behind a whole sync. Per-loop weak-keyed (the `widget_data.py:39-55` pattern) because the test suite creates a fresh loop per test.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_llm_gate.py`:

```python
"""One Qwen box serves the sync AND the agent (spec F5).

Two independent semaphores against one endpoint is a queue nobody manages: a
sync during an agent run doubles the load and the person's question waits
behind 82 table descriptions. The gate lives in the CLIENT, so every caller
is bounded by construction — and background work is capped below the total,
leaving reserved headroom so an interactive question never starves.
"""
import asyncio

import httpx
import pytest

from app.core.config import settings
from app.services.llm import LLMClient


def make_client(inflight, peak, delay=0.05):
    """A client whose transport records concurrency instead of calling out."""
    async def handler(request):
        inflight.append(1)
        peak[0] = max(peak[0], len(inflight))
        await asyncio.sleep(delay)
        inflight.pop()
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })
    return LLMClient(base_url="http://test/v1", model="m",
                     transport=httpx.MockTransport(handler))


MSGS = [{"role": "user", "content": "hi"}]


class TestTheGateBounds:
    async def test_total_concurrency_never_exceeds_the_setting(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_max_concurrency", 3)
        monkeypatch.setattr(settings, "llm_reserved_interactive", 1)
        inflight, peak = [], [0]
        client = make_client(inflight, peak)
        await asyncio.gather(*(client.complete(MSGS) for _ in range(10)))
        assert peak[0] <= 3

    async def test_background_work_cannot_take_the_reserved_slots(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_max_concurrency", 4)
        monkeypatch.setattr(settings, "llm_reserved_interactive", 2)
        inflight, peak = [], [0]
        client = make_client(inflight, peak)
        await asyncio.gather(*(client.complete(MSGS, background=True)
                               for _ in range(10)))
        assert peak[0] <= 2, (
            "background callers filled the whole gate; an interactive "
            "question would queue behind a sync"
        )

    async def test_interactive_work_may_use_every_slot(self, monkeypatch):
        monkeypatch.setattr(settings, "llm_max_concurrency", 4)
        monkeypatch.setattr(settings, "llm_reserved_interactive", 2)
        inflight, peak = [], [0]
        client = make_client(inflight, peak)
        await asyncio.gather(*(client.complete(MSGS) for _ in range(10)))
        assert peak[0] > 2, "the reservation throttled interactive work too"


class TestEnforcedJson:
    async def test_enforce_sends_response_format_json_schema(self):
        seen = {}

        async def handler(request):
            import json
            seen.update(json.loads(request.content))
            return httpx.Response(200, json={
                "choices": [{"message": {"content": '{"x": 1}'}}], "usage": {}})

        client = LLMClient(base_url="http://test/v1", model="m",
                           transport=httpx.MockTransport(handler))
        schema = {"type": "object", "properties": {"x": {"type": "integer"}},
                  "required": ["x"]}
        got = await client.complete_json(MSGS, schema, enforce=True)
        assert got == {"x": 1}
        # F2: json_schema is the ONE enforced mechanism on this endpoint.
        # guided_json is silently ignored — asserting it is absent guards
        # against someone "upgrading" to the documented-but-dead parameter.
        assert seen["response_format"]["type"] == "json_schema"
        assert "guided_json" not in seen
```

- [ ] **Step 2: Run to verify failure** — `... pytest tests/test_llm_gate.py -q` → TypeError: unexpected keyword `background` / `enforce`.

- [ ] **Step 3: Implement the gate in `llm.py`**

Add near the top of `app/services/llm.py` (after imports):

```python
import weakref

#: Per-event-loop gates, weakly keyed — the widget_data.py pattern, for the
#: same reason: the test suite creates a fresh loop per test, and a semaphore
#: is bound to the loop it was created on.
_GATES: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _gates() -> tuple[asyncio.Semaphore, asyncio.Semaphore]:
    """(total, background) for the current loop.

    Reserved headroom (spec F5): background callers hold BOTH, so they can
    never occupy the last `llm_reserved_interactive` slots. Interactive
    callers hold only the total. The reservation is a promise to the person
    waiting on an answer, enforced by construction rather than by priority.
    """
    from ..core.config import settings

    loop = asyncio.get_running_loop()
    made = _GATES.get(loop)
    total_n = settings.llm_max_concurrency
    back_n = max(1, total_n - settings.llm_reserved_interactive)
    if made is None or made[2] != (total_n, back_n):
        made = (asyncio.Semaphore(total_n), asyncio.Semaphore(back_n),
                (total_n, back_n))
        _GATES[loop] = made
    return made[0], made[1]
```

(Add `import asyncio` to the file's imports if absent.)

Change `complete`'s signature and body:

```python
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        background: bool = False,
        response_format: dict | None = None,
    ) -> str | None:
```

and wrap the HTTP call (the existing `try: async with httpx.AsyncClient...` block) like this — acquire order is background-then-total, so a background caller blocked on its cap holds nothing:

```python
        total, back = _gates()
        if background:
            async with back, total:
                return await self._post(payload)
        async with total:
            return await self._post(payload)
```

Extract the existing HTTP block verbatim into `async def _post(self, payload) -> str | None` (the code from `self.call_count += 1` through `return content.strip()` — unchanged, just moved). Before that, in payload construction, add:

```python
        if response_format is not None:
            payload["response_format"] = response_format
```

Change `complete_json`'s signature to add `background: bool = False, enforce: bool = False`, and pass through:

```python
            raw = await self.complete(
                attempt_messages, max_tokens=max_tokens, temperature=temperature,
                background=background,
                response_format=(
                    {"type": "json_schema",
                     "json_schema": {"name": "reply", "schema": schema}}
                    if enforce else None),
            )
```

Add to `app/core/config.py` (**utf-8-sig**), next to `llm_base_url`:

```python
    # Total in-flight requests to the model endpoint, ACROSS features -- the
    # sync's describe stage and agent runs share one box. Measured on the Qwen
    # endpoint: throughput 0.31 / 1.35 / 2.32 req/s at concurrency 1 / 6 / 12,
    # per-call latency rising only 3.2s -> 5.1s (continuous batching working).
    llm_max_concurrency: int = Field(default=12, ge=1)
    # Slots background work may never occupy, so a person's question does not
    # queue behind 82 table descriptions. Reserved headroom, not priority:
    # exact by construction, worst case bounded.
    llm_reserved_interactive: int = Field(default=2, ge=0)
```

- [ ] **Step 4: Rewire the sync's describe stage as a background caller**

In `app/services/metadata/catalog_sync.py`, `stage_describe`: delete the local `semaphore = asyncio.Semaphore(settings.metadata_describe_concurrency)` and its `async with semaphore:` — the calls into `infer_semantic.describe_with_llm` / `describe_source_with_llm` now rely on the client gate. In `app/services/metadata/infer_semantic.py`, pass `background=True` in both `complete_json` calls. Keep `metadata_describe_concurrency` in config with a deprecation comment pointing at `llm_max_concurrency` (removing a setting someone may have in `.env` is not additive).

- [ ] **Step 5: Run** — `... pytest tests/test_llm_gate.py tests/test_infer_semantic.py tests/test_catalog_sync.py -q` → all pass.

- [ ] **Step 6: Checkpoint** — full backend suite green.

---

### Task 4: The DAG executor

**Files:**
- Create: `backend/app/services/agent/__init__.py` (empty), `backend/app/services/agent/state.py`, `backend/app/services/agent/dag.py`
- Test: `backend/tests/test_agent_dag.py`

**Interfaces:**
- Produces:
  - `state.py`: `@dataclass StepSpec(id: str, question: str, depends_on: list[str])`; `@dataclass StepResult(step_id: str, status: str, sql: str | None, rows: list[dict] | None, error: str | None, validation_failures: list[dict], repair_attempts: int, ms: int)` (status: `ok | failed | skipped_dependency`).
  - `dag.py`: `async run_dag(steps: list[StepSpec], run_node, gate: asyncio.Semaphore) -> dict[str, StepResult]` where `run_node(step: StepSpec, parents: dict[str, StepResult]) -> StepResult` is an async callable. Raises `ValueError` on a cycle or unknown dependency **before** running anything.
- Consumed by: Task 11 (`graph.py`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_dag.py`:

```python
"""The executor: topological layers, one bounded gate, failures contained.

Mirrors stage_sample's proven shape (gather + semaphore + every outcome a
value). What is new is dependency handling: a failed node fails its
DEPENDENTS and never its SIBLINGS — the property the whole plan/execute
split rests on.
"""
import asyncio

import pytest

from app.services.agent.dag import run_dag
from app.services.agent.state import StepResult, StepSpec


def ok(step, parents):
    return StepResult(step_id=step.id, status="ok", sql=None, rows=[{"n": 1}],
                      error=None, validation_failures=[], repair_attempts=0, ms=1)


class TestTopology:
    async def test_independent_steps_overlap(self):
        live, peak = [], [0]

        async def slow(step, parents):
            live.append(step.id); peak[0] = max(peak[0], len(live))
            await asyncio.sleep(0.05)
            live.remove(step.id)
            return ok(step, parents)

        steps = [StepSpec(id=f"s{i}", question="q", depends_on=[]) for i in range(4)]
        await run_dag(steps, slow, asyncio.Semaphore(4))
        assert peak[0] > 1, "independent steps ran one at a time"

    async def test_the_gate_bounds_width(self):
        live, peak = [], [0]

        async def slow(step, parents):
            live.append(step.id); peak[0] = max(peak[0], len(live))
            await asyncio.sleep(0.05)
            live.remove(step.id)
            return ok(step, parents)

        steps = [StepSpec(id=f"s{i}", question="q", depends_on=[]) for i in range(8)]
        await run_dag(steps, slow, asyncio.Semaphore(2))
        assert peak[0] <= 2

    async def test_a_dependent_sees_its_parents_result(self):
        seen = {}

        async def node(step, parents):
            seen[step.id] = {k: v.rows for k, v in parents.items()}
            return ok(step, parents)

        await run_dag([StepSpec("a", "q", []), StepSpec("b", "q", ["a"])],
                      node, asyncio.Semaphore(4))
        assert seen["b"] == {"a": [{"n": 1}]}

    async def test_a_parent_completes_before_its_child_starts(self):
        order = []

        async def node(step, parents):
            order.append(("start", step.id))
            await asyncio.sleep(0.02)
            order.append(("end", step.id))
            return ok(step, parents)

        await run_dag([StepSpec("a", "q", []), StepSpec("b", "q", ["a"])],
                      node, asyncio.Semaphore(4))
        assert order.index(("end", "a")) < order.index(("start", "b"))


class TestFailureContainment:
    async def test_a_failed_node_fails_dependents_not_siblings(self):
        async def node(step, parents):
            if step.id == "bad":
                raise RuntimeError("boom")
            return ok(step, parents)

        results = await run_dag(
            [StepSpec("bad", "q", []), StepSpec("sibling", "q", []),
             StepSpec("child_of_bad", "q", ["bad"])],
            node, asyncio.Semaphore(4))

        assert results["sibling"].status == "ok"
        assert results["bad"].status == "failed"
        assert results["child_of_bad"].status == "skipped_dependency"

    async def test_a_node_returning_failed_also_skips_dependents(self):
        async def node(step, parents):
            if step.id == "a":
                return StepResult(step_id="a", status="failed", sql=None,
                                  rows=None, error="ladder rejected", 
                                  validation_failures=[], repair_attempts=3, ms=1)
            return ok(step, parents)

        results = await run_dag([StepSpec("a", "q", []), StepSpec("b", "q", ["a"])],
                                node, asyncio.Semaphore(4))
        assert results["b"].status == "skipped_dependency"


class TestBadGraphsAreRefusedUpFront:
    async def test_a_cycle_is_an_error_before_anything_runs(self):
        ran = []

        async def node(step, parents):
            ran.append(step.id)
            return ok(step, parents)

        with pytest.raises(ValueError, match="cycle"):
            await run_dag([StepSpec("a", "q", ["b"]), StepSpec("b", "q", ["a"])],
                          node, asyncio.Semaphore(4))
        assert ran == []

    async def test_an_unknown_dependency_is_an_error(self):
        with pytest.raises(ValueError, match="unknown"):
            await run_dag([StepSpec("a", "q", ["ghost"])],
                          lambda s, p: None, asyncio.Semaphore(4))
```

- [ ] **Step 2: Run to verify failure** — ModuleNotFoundError.

- [ ] **Step 3: Implement**

`backend/app/services/agent/state.py`:

```python
"""Typed state passed between the agent's nodes.

Plain dataclasses, not ORM objects: results cross task boundaries and (in the
executor) sometimes thread boundaries, and the catalog-sync work already
established the rule — plain data over the seam, always.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepSpec:
    """One planned step. `depends_on` names other steps whose results this one
    needs — an empty list means it can run in the first layer."""
    id: str
    question: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class StepResult:
    """Every outcome is a value (ok | failed | skipped_dependency), so the
    caller aggregates without interpreting exceptions — the stage_sample
    convention."""
    step_id: str
    status: str
    sql: str | None
    rows: list[dict] | None
    error: str | None
    validation_failures: list[dict]
    repair_attempts: int
    ms: int
```

`backend/app/services/agent/dag.py`:

```python
"""Run a step DAG in topological layers under one bounded gate.

Deliberately ~80 lines and owned, not LangGraph (spec S5): every concurrency
path in this codebase is hand-rolled gather + Semaphore, this graph is
acyclic by construction, and the one loop (repair) lives INSIDE a node.

ONE gate for the whole run, not one per layer: the bound is a promise about
load on the customer's database, and a per-layer semaphore would let a wide
layer exceed it.
"""
from __future__ import annotations

import asyncio

from .state import StepResult, StepSpec


def topological_layers(steps: list[StepSpec]) -> list[list[StepSpec]]:
    """Kahn's algorithm, validated: unknown deps and cycles are refused BEFORE
    anything runs — a planner bug must fail the run, never hang it."""
    by_id = {s.id: s for s in steps}
    for s in steps:
        for dep in s.depends_on:
            if dep not in by_id:
                raise ValueError(f"step {s.id!r} depends on unknown step {dep!r}")

    remaining = dict(by_id)
    done: set[str] = set()
    layers: list[list[StepSpec]] = []
    while remaining:
        ready = [s for s in remaining.values()
                 if all(d in done for d in s.depends_on)]
        if not ready:
            raise ValueError(
                f"cycle among steps: {sorted(remaining)}")
        layers.append(ready)
        for s in ready:
            done.add(s.id)
            del remaining[s.id]
    return layers


async def run_dag(steps: list[StepSpec], run_node, gate: asyncio.Semaphore,
                  ) -> dict[str, StepResult]:
    """`run_node(step, parents)` is awaited for each runnable step; `parents`
    maps each dependency id to its StepResult. A failed node fails its
    dependents (skipped_dependency) and never its siblings."""
    layers = topological_layers(steps)
    results: dict[str, StepResult] = {}

    async def one(step: StepSpec) -> StepResult:
        parents = {d: results[d] for d in step.depends_on}
        if any(p.status != "ok" for p in parents.values()):
            blocked = [d for d, p in parents.items() if p.status != "ok"]
            return StepResult(step_id=step.id, status="skipped_dependency",
                              sql=None, rows=None,
                              error=f"dependency failed: {', '.join(blocked)}",
                              validation_failures=[], repair_attempts=0, ms=0)
        async with gate:
            return await run_node(step, parents)

    for layer in layers:
        outcomes = await asyncio.gather(*(one(s) for s in layer),
                                        return_exceptions=True)
        for step, outcome in zip(layer, outcomes):
            if isinstance(outcome, BaseException):
                outcome = StepResult(
                    step_id=step.id, status="failed", sql=None, rows=None,
                    error=f"{type(outcome).__name__}: {outcome}",
                    validation_failures=[], repair_attempts=0, ms=0)
            results[step.id] = outcome
    return results
```

- [ ] **Step 4: Run** — `... pytest tests/test_agent_dag.py -q` → all pass.

---

### Task 5: The context interface (Layer 3 stand-in)

**Files:**
- Create: `backend/app/services/agent/context.py`
- Test: `backend/tests/test_agent_context.py`

**Interfaces:**
- Produces:
  - `@dataclass SchemaContext(objects: dict[str, ObjectInfo], joins: list[JoinInfo], source_id: int, family: str)` where `ObjectInfo(name, kind, columns: dict[str, str])` (column name → dtype) and `JoinInfo(from_table, from_column, to_table, to_column, provenance)`.
  - `async load_context(db, source_id: int, org_id: int) -> SchemaContext` — **only `confirmed`/`declared` relationships enter `joins`** (spec F1).
  - `SchemaContext.render(max_chars: int = 8000) -> str` — the prompt block.
  - `SchemaContext.has_table(name)`, `has_column(table, name)`, `join_allowed(t1, c1, t2, c2) -> bool` (order-insensitive) — V2/V3 read these.
- Consumed by: Tasks 6, 7, 9, 11.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_context.py`:

```python
"""What the agent knows about a source — and what it must NOT know.

The catalog (Layer 1) is the v1 implementation of Layer 3 (spec F6). The
critical property is F1: inferred relationships are PROPOSALS and never enter
the join whitelist. 105 of the live source's 133 relationships are inferred;
an agent that joined on them would return plausible wrong numbers.
"""
import pytest

from app.models.models import (DataSource, Organization, SourceColumn,
                               SourceObject, SourceRelationship)
from app.services.agent.context import load_context


@pytest.fixture
async def catalog(db_session):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    ds = DataSource(name="shop", type="postgresql", org_id=org.id, config={})
    db_session.add(ds)
    await db_session.flush()

    objs = {}
    for name, kind, cols in [
        ("customers", "table", [("id", "integer"), ("city", "text")]),
        ("orders", "table", [("id", "integer"), ("customer_id", "integer"),
                             ("total", "numeric")]),
        ("v_sales", "view", [("city", "text"), ("revenue", "numeric")]),
    ]:
        o = SourceObject(data_source_id=ds.id, org_id=org.id, name=name,
                         kind=kind, description=f"About {name}.")
        db_session.add(o)
        await db_session.flush()
        objs[name] = o
        for cname, dtype in cols:
            db_session.add(SourceColumn(source_object_id=o.id, name=cname,
                                        dtype=dtype))

    db_session.add(SourceRelationship(
        data_source_id=ds.id, org_id=org.id,
        from_object_id=objs["orders"].id, from_column="customer_id",
        to_object_id=objs["customers"].id, to_column="id",
        source="declared", confidence=1.0))
    db_session.add(SourceRelationship(
        data_source_id=ds.id, org_id=org.id,
        from_object_id=objs["v_sales"].id, from_column="city",
        to_object_id=objs["customers"].id, to_column="city",
        source="inferred", confidence=0.9))
    await db_session.commit()
    return {"org": org, "ds": ds}


class TestWhatTheAgentKnows:
    async def test_every_object_and_column_is_visible(self, db_session, catalog):
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        assert ctx.has_table("orders")
        assert ctx.has_column("orders", "customer_id")
        assert not ctx.has_table("ghost")
        assert not ctx.has_column("orders", "ghost")

    async def test_the_render_carries_descriptions_and_kinds(self, db_session, catalog):
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        text = ctx.render()
        assert "About orders." in text
        assert "view" in text.lower()   # v_sales is labelled as what it is


class TestTheProvenanceRule:
    async def test_a_declared_join_is_allowed(self, db_session, catalog):
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        assert ctx.join_allowed("orders", "customer_id", "customers", "id")
        # Order-insensitive: a JOIN may be written either way round.
        assert ctx.join_allowed("customers", "id", "orders", "customer_id")

    async def test_an_inferred_join_is_not_in_the_whitelist(self, db_session, catalog):
        """THE most important assertion in the layer (spec F1). An inferred
        edge is a proposal for a human, not a fact for the agent."""
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        assert not ctx.join_allowed("v_sales", "city", "customers", "city")

    async def test_the_render_never_offers_an_inferred_join(self, db_session, catalog):
        ctx = await load_context(db_session, catalog["ds"].id, catalog["org"].id)
        assert "v_sales.city" not in ctx.render().split("Joins")[-1]


class TestOrgScoping:
    async def test_another_orgs_source_yields_nothing(self, db_session, catalog):
        other = Organization(name="Rival")
        db_session.add(other)
        await db_session.commit()
        ctx = await load_context(db_session, catalog["ds"].id, other.id)
        assert ctx.objects == {}
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `context.py`**

```python
"""What the agent may know about a source.

This is an INTERFACE with a v1 implementation (spec F6): Layer 3 — entities,
glossary, embeddings, retrieval — does not exist, and the Layer 1 catalog is
its serviceable stand-in. A real semantic layer replaces `load_context`
without touching the graph.

The one rule that must survive any replacement is F1: only `confirmed` and
`declared` relationships enter `joins`. Inference proposes; a human confirms;
the agent executes only on what survived that ladder.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from ...models.models import (DataSource, SourceColumn, SourceObject,
                              SourceRelationship)
from ..metadata import store


@dataclass
class ObjectInfo:
    name: str
    kind: str
    description: str | None
    columns: dict[str, str] = field(default_factory=dict)


@dataclass
class JoinInfo:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    provenance: str


@dataclass
class SchemaContext:
    source_id: int
    family: str
    objects: dict[str, ObjectInfo] = field(default_factory=dict)
    joins: list[JoinInfo] = field(default_factory=list)

    def has_table(self, name: str) -> bool:
        return name in self.objects

    def has_column(self, table: str, column: str) -> bool:
        info = self.objects.get(table)
        return bool(info) and column in info.columns

    def join_allowed(self, t1: str, c1: str, t2: str, c2: str) -> bool:
        """Order-insensitive: SQL may write either side first."""
        want = {(t1, c1), (t2, c2)}
        return any({(j.from_table, j.from_column),
                    (j.to_table, j.to_column)} == want for j in self.joins)

    def render(self, max_chars: int = 8000) -> str:
        """The prompt block. Tables before views, kinds labelled, and ONLY
        allowed joins listed — offering an inferred join in the prompt would
        invite the model to write SQL that V3 then rejects."""
        lines = []
        ordered = sorted(self.objects.values(),
                         key=lambda o: (o.kind != "table", o.name))
        for o in ordered:
            cols = ", ".join(f"{n} {t}" for n, t in o.columns.items())
            desc = f" -- {o.description}" if o.description else ""
            lines.append(f"- {o.name} ({o.kind}): {cols}{desc}")
        joins = [f"- {j.from_table}.{j.from_column} = {j.to_table}.{j.to_column}"
                 for j in self.joins]
        text = "Objects:\n" + "\n".join(lines)
        if joins:
            text += "\n\nJoins you may use (the ONLY joins allowed):\n" + "\n".join(joins)
        return text[:max_chars]


async def load_context(db, source_id: int, org_id: int) -> SchemaContext:
    source = await db.get(DataSource, source_id)
    family = source.type if source and source.org_id == org_id else "postgresql"

    ctx = SchemaContext(source_id=source_id, family=family or "postgresql")
    if source is None or source.org_id != org_id:
        # Same shape as check_org's 404: reveal nothing, not even emptiness
        # semantics. The router turns an empty context into "not found".
        return ctx

    objects = (await db.execute(select(SourceObject).where(
        SourceObject.data_source_id == source_id,
        SourceObject.org_id == org_id))).scalars().all()
    by_id = {}
    for o in objects:
        info = ObjectInfo(name=o.name, kind=o.kind or "table",
                          description=o.comment or o.description)
        ctx.objects[o.name] = info
        by_id[o.id] = info

    if by_id:
        columns = (await db.execute(select(SourceColumn).where(
            SourceColumn.source_object_id.in_(list(by_id))))).scalars().all()
        for c in columns:
            by_id[c.source_object_id].columns[c.name] = c.dtype or "unknown"

        rels = (await db.execute(select(SourceRelationship).where(
            SourceRelationship.data_source_id == source_id,
            SourceRelationship.source.in_([store.CONFIRMED, store.DECLARED]),
        ))).scalars().all()
        for r in rels:
            f, t = by_id.get(r.from_object_id), by_id.get(r.to_object_id)
            if f and t:
                ctx.joins.append(JoinInfo(f.name, r.from_column,
                                          t.name, r.to_column, r.source))
    return ctx
```

- [ ] **Step 4: Run** — all pass. **Step 5: Checkpoint** — `... pytest tests/test_agent_context.py tests/test_agent_dag.py -q`.

---

### Task 6: classify + clarify nodes

**Files:**
- Create: `backend/app/services/agent/nodes/__init__.py` (empty), `backend/app/services/agent/nodes/classify.py`, `backend/app/services/agent/nodes/clarify.py`
- Test: `backend/tests/test_agent_classify.py`

**Interfaces:**
- Produces: `async classify(question: str, context: SchemaContext, client) -> dict | None` returning `{"intent": one of lookup|aggregate|trend|compare|explain, "ambiguous": bool, "ambiguity_reason": str|None}`; `async clarify(question: str, reason: str, client) -> str | None` (the question to ask back). Both return `None` on LLM failure — the graph treats that as run failure with an honest error, never a guess.
- Consumes: `SchemaContext.render()` (Task 5); `complete_json(..., enforce=True)` (Task 3).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_classify.py`:

```python
"""Intent + the D4.3 rule: clarify when ambiguous, never guess.

A wrong confident answer destroys trust faster than a question costs
patience (spec / ARCHITECTURE.md D4.3). The tests fake the client — what is
under test is the CONTRACT: the schema sent, enforce=True, and honest None
propagation.
"""
from app.services.agent.context import ObjectInfo, SchemaContext
from app.services.agent.nodes.classify import CLASSIFY_SCHEMA, classify
from app.services.agent.nodes.clarify import clarify


def ctx():
    c = SchemaContext(source_id=1, family="postgresql")
    c.objects["orders"] = ObjectInfo("orders", "table", None,
                                     {"id": "integer", "total": "numeric"})
    return c


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append({"messages": messages, "schema": schema, **kw})
        return self.reply

    async def complete(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        return self.reply if isinstance(self.reply, str) else None


class TestClassify:
    async def test_returns_the_models_verdict(self):
        client = FakeClient({"intent": "aggregate", "ambiguous": False,
                             "ambiguity_reason": None})
        got = await classify("total sales by city", ctx(), client)
        assert got["intent"] == "aggregate"
        assert got["ambiguous"] is False

    async def test_uses_the_enforced_contract(self):
        """F2: grammar enforcement is the only mechanism that held up under
        adversarial probing. Prompt-begging alone is not a contract."""
        client = FakeClient({"intent": "lookup", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("q", ctx(), client)
        call = client.calls[0]
        assert call["enforce"] is True
        assert call["schema"] is CLASSIFY_SCHEMA
        assert call["schema"]["properties"]["intent"]["enum"] == [
            "lookup", "aggregate", "trend", "compare", "explain"]

    async def test_the_schema_context_reaches_the_prompt(self):
        client = FakeClient({"intent": "lookup", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("q", ctx(), client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "orders" in text

    async def test_llm_failure_is_none_not_a_guess(self):
        assert await classify("q", ctx(), FakeClient(None)) is None


class TestClarify:
    async def test_produces_a_question_from_the_reason(self):
        client = FakeClient("Did you mean order total or order count?")
        got = await clarify("show me the orders number",
                            "could be count of orders or order totals", client)
        assert got.endswith("?")

    async def test_llm_failure_is_none(self):
        assert await clarify("q", "r", FakeClient(None)) is None
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

`nodes/classify.py`:

```python
"""Intent + ambiguity, under the enforced JSON contract.

Enforcement is structural, not semantic (spec F2 — a trend question came back
as valid JSON calling itself `lookup` with confidence 0). So the prompt
carries few-shot examples per intent, and the eval gate in evals/ is what
actually polices quality. This node only guarantees the SHAPE.
"""
from __future__ import annotations

from ..context import SchemaContext

INTENTS = ["lookup", "aggregate", "trend", "compare", "explain"]

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "ambiguous": {"type": "boolean"},
        "ambiguity_reason": {"type": ["string", "null"]},
    },
    "required": ["intent", "ambiguous", "ambiguity_reason"],
    "additionalProperties": False,
}

_EXAMPLES = """Examples:
Q: what is customer 8842's email -> {"intent": "lookup", "ambiguous": false, "ambiguity_reason": null}
Q: total revenue by region -> {"intent": "aggregate", "ambiguous": false, "ambiguity_reason": null}
Q: how did signups change month over month -> {"intent": "trend", "ambiguous": false, "ambiguity_reason": null}
Q: cairo vs giza sales -> {"intent": "compare", "ambiguous": false, "ambiguity_reason": null}
Q: why did returns spike -> {"intent": "explain", "ambiguous": false, "ambiguity_reason": null}
Q: show me the numbers -> {"intent": "lookup", "ambiguous": true, "ambiguity_reason": "which numbers — no metric or table named"}"""


async def classify(question: str, context: SchemaContext, client) -> dict | None:
    """Returns the verdict dict, or None when the model could not be reached
    or never satisfied the contract. None means the RUN fails honestly —
    guessing an intent is exactly what D4.3 forbids."""
    messages = [
        {"role": "system", "content": (
            "You classify a business question against a database so an agent "
            "can plan a query. `ambiguous` is true when the question maps to "
            "two or more materially different queries — two plausible metrics, "
            "two date columns, an unnamed table. When in doubt, prefer "
            "ambiguous=true: a clarifying question costs a moment, a wrong "
            "confident answer costs trust.\n" + _EXAMPLES)},
        {"role": "user", "content": (
            f"Database:\n{context.render(max_chars=4000)}\n\n"
            f"Question: {question}")},
    ]
    return await client.complete_json(messages, CLASSIFY_SCHEMA,
                                      enforce=True, max_tokens=200,
                                      temperature=0.0)
```

`nodes/clarify.py`:

```python
"""D4.3: ask, do not guess. This node turns the classifier's ambiguity
reason into one short question for the person; the run ends with status
`needs_clarification`, and the user's reply arrives as a fresh question."""
from __future__ import annotations


async def clarify(question: str, reason: str, client) -> str | None:
    got = await client.complete(
        [{"role": "system", "content": (
            "A user's question was ambiguous. Write ONE short clarifying "
            "question offering the concrete interpretations. No preamble.")},
         {"role": "user", "content":
            f"Question: {question}\nWhy it is ambiguous: {reason}"}],
        max_tokens=120, temperature=0.2)
    return got.strip() if got else None
```

- [ ] **Step 4: Run** — all pass.

---

### Task 7: The validation ladder V1–V3

**Files:**
- Create: `backend/app/services/agent/validate.py`
- Test: `backend/tests/test_agent_validate.py`

**Interfaces:**
- Produces: `@dataclass ValidationFailure(rung: str, detail: str)`; `validate_sql(sql: str, context: SchemaContext) -> ValidationFailure | None` (runs V1 parse → V1.5 select-only → V2 schema → V3 joins, returns the FIRST failure); helper `_dialect(family: str) -> str` mapping `postgresql→postgres, mysql→mysql, mssql→tsql, oracle→oracle, sqlite→sqlite`.
- Consumes: `SchemaContext` (Task 5), sqlglot (Task 1).
- Consumed by: Tasks 8, 10, 11.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_validate.py`:

```python
"""The ladder, cheapest first (D4.1) — each rung caught AT that rung.

Cheapest-first only matters if it holds: a syntax error must be V1, not a
confusing V2 miss. And V3 is the single most important test in the layer
(spec F1): a join whose only support is an INFERRED relationship must be
rejected — 105 of the live source's 133 edges are proposals, and executing
on one returns a plausible wrong number.
"""
from app.services.agent.context import JoinInfo, ObjectInfo, SchemaContext
from app.services.agent.validate import validate_sql


def ctx():
    c = SchemaContext(source_id=1, family="postgresql")
    c.objects["customers"] = ObjectInfo("customers", "table", None,
                                        {"id": "integer", "city": "text"})
    c.objects["orders"] = ObjectInfo("orders", "table", None,
                                     {"id": "integer", "customer_id": "integer",
                                      "total": "numeric"})
    c.joins.append(JoinInfo("orders", "customer_id", "customers", "id", "declared"))
    return c


class TestV1Parse:
    def test_garbage_fails_at_v1(self):
        failure = validate_sql("SELEC totl FRM", ctx())
        assert failure.rung == "V1"

    def test_only_select_is_allowed(self):
        """The agent reads; it never writes. A model that emits DELETE has
        been prompt-injected or has hallucinated — either way, refuse."""
        for sql in ("DELETE FROM orders", "UPDATE orders SET total = 0",
                    "DROP TABLE orders", "INSERT INTO orders VALUES (1)"):
            failure = validate_sql(sql, ctx())
            assert failure is not None and failure.rung == "V1", sql


class TestV2Schema:
    def test_a_hallucinated_table_fails_at_v2(self):
        failure = validate_sql("SELECT * FROM shipments", ctx())
        assert failure.rung == "V2"
        assert "shipments" in failure.detail

    def test_a_hallucinated_column_fails_at_v2(self):
        failure = validate_sql("SELECT discount FROM orders", ctx())
        assert failure.rung == "V2"
        assert "discount" in failure.detail

    def test_aliases_resolve_before_checking(self):
        assert validate_sql(
            "SELECT o.total FROM orders AS o", ctx()) is None


class TestV3Joins:
    def test_a_declared_join_passes(self):
        assert validate_sql(
            "SELECT c.city, sum(o.total) FROM orders o "
            "JOIN customers c ON o.customer_id = c.id GROUP BY c.city",
            ctx()) is None

    def test_the_join_passes_written_either_way_round(self):
        assert validate_sql(
            "SELECT 1 FROM customers c JOIN orders o ON c.id = o.customer_id",
            ctx()) is None

    def test_an_unconfirmed_join_fails_at_v3(self):
        """THE spec-F1 test. orders.total = customers.id is nonsense the
        schema cannot catch — both exist — only provenance can."""
        failure = validate_sql(
            "SELECT 1 FROM orders o JOIN customers c ON o.total = c.id", ctx())
        assert failure.rung == "V3"

    def test_an_inferred_only_join_fails_at_v3(self):
        c = ctx()
        # An inferred edge exists in the DB but never entered ctx.joins —
        # load_context filtered it. Simulate the SQL a model might still write.
        failure = validate_sql(
            "SELECT 1 FROM orders o JOIN customers c ON o.id = c.id", c)
        assert failure.rung == "V3"


class TestOrder:
    def test_a_query_with_both_problems_reports_the_cheaper_rung(self):
        # unknown table AND bad join: V2 fires first — cheapest-first.
        failure = validate_sql(
            "SELECT 1 FROM shipments s JOIN customers c ON s.x = c.city", ctx())
        assert failure.rung == "V2"
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `validate.py`**

```python
"""The V1-V5 ladder, rungs V1-V3 (V4 is policy.py, V5 lives in executor.py).

Cheapest first (D4.1): parse costs microseconds, schema costs a dict lookup
(the Layer 1 catalog already holds all columns — V2 alone eliminates the most
common failure, hallucinated names), joins cost a set lookup against the
provenance-filtered whitelist. Most failures never reach a database.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from .context import SchemaContext


@dataclass
class ValidationFailure:
    rung: str
    detail: str


_DIALECTS = {"postgresql": "postgres", "mysql": "mysql", "mssql": "tsql",
             "oracle": "oracle", "sqlite": "sqlite"}


def _dialect(family: str) -> str:
    return _DIALECTS.get((family or "").lower(), "postgres")


def validate_sql(sql: str, context: SchemaContext) -> ValidationFailure | None:
    """First failure wins; None means rungs V1-V3 all passed."""
    # ── V1: parse, and SELECT-only ─────────────────────────────────────────
    try:
        tree = sqlglot.parse_one(sql, dialect=_dialect(context.family))
    except Exception as exc:
        return ValidationFailure("V1", f"does not parse: {exc}")
    if tree is None or not isinstance(tree, (exp.Select, exp.Union)):
        return ValidationFailure(
            "V1", "only SELECT statements are allowed; the agent reads, never writes")

    # ── V2: every table and column must exist in the catalog ───────────────
    alias_to_table: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        name = table.name
        if not context.has_table(name):
            return ValidationFailure("V2", f"no such table: {name}")
        alias_to_table[(table.alias or name)] = name

    for column in tree.find_all(exp.Column):
        cname = column.name
        qualifier = column.table  # empty string when unqualified
        if qualifier:
            table = alias_to_table.get(qualifier)
            if table is None:
                return ValidationFailure("V2", f"unknown alias: {qualifier}")
            if not context.has_column(table, cname):
                return ValidationFailure(
                    "V2", f"no such column: {qualifier}.{cname} "
                          f"(table {table})")
        else:
            if not any(context.has_column(t, cname)
                       for t in alias_to_table.values()):
                return ValidationFailure("V2", f"no such column: {cname}")

    # ── V3: every join must be a confirmed or declared edge ────────────────
    def _resolve(col: exp.Column) -> tuple[str, str] | None:
        if col.table:
            t = alias_to_table.get(col.table)
            return (t, col.name) if t else None
        owners = [t for t in alias_to_table.values()
                  if context.has_column(t, col.name)]
        return (owners[0], col.name) if len(owners) == 1 else None

    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            return ValidationFailure("V3", "JOIN without an ON condition")
        for eq in on.find_all(exp.EQ):
            left, right = eq.left, eq.right
            if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                lt, rt = _resolve(left), _resolve(right)
                if lt is None or rt is None:
                    return ValidationFailure("V3", f"cannot resolve join: {eq.sql()}")
                if not context.join_allowed(lt[0], lt[1], rt[0], rt[1]):
                    return ValidationFailure(
                        "V3",
                        f"join {lt[0]}.{lt[1]} = {rt[0]}.{rt[1]} is not a "
                        "confirmed or declared relationship. Inferred "
                        "relationships are proposals awaiting human review "
                        "and may not be executed on.")
    return None
```

- [ ] **Step 4: Run** — all pass. If sqlglot's API differs on any assertion (e.g. `exp.Union` naming across versions), fix the implementation, never weaken a test.

---

### Task 8: Row-policy AST injection (V4)

**Files:**
- Create: `backend/app/services/agent/policy.py`
- Test: `backend/tests/test_agent_policy.py`

**Interfaces:**
- Produces: `apply_policies(sql: str, policies: dict[str, str], family: str) -> str` — `policies` maps table name → predicate SQL; returns re-rendered SQL with each predicate AND-ed into the WHERE of every SELECT that references the table (qualified by alias). Raises `PolicyError` (subclass of `Exception`) when a policied table appears somewhere the predicate cannot be safely attached.
- `async load_policies(db, context: SchemaContext, user) -> dict[str, str]` — empty for `user.role.is_org_admin` (same bypass as `resolve_rls_expr`); resolves `USEREMAIL()`/`USERID()` via the existing `apply_user_context` from `app/core/rls.py`.
- Consumed by: Task 11.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_policy.py`:

```python
"""V4: predicates into the AST — never concatenated, never post-filtered.

ARCHITECTURE.md calls this the security-critical flow of the whole platform,
and forbids the two easy ways out: string concatenation (injectable) and
post-filtering (leaks row counts, aggregates and existence — an aggregate
computed before the filter is already the wrong number). The import path's
apply_rls_filter post-filters; the agent path must never call it (spec F4).
"""
import pytest
import sqlglot

from app.services.agent.policy import PolicyError, apply_policies


class TestInjection:
    def test_the_predicate_lands_inside_where(self):
        out = apply_policies("SELECT total FROM orders",
                             {"orders": "region = 'west'"}, "postgresql")
        tree = sqlglot.parse_one(out, dialect="postgres")
        assert "region = 'west'" in tree.args["where"].sql(dialect="postgres")

    def test_an_existing_where_is_preserved_with_and(self):
        out = apply_policies("SELECT total FROM orders WHERE total > 10",
                             {"orders": "region = 'west'"}, "postgresql")
        where = sqlglot.parse_one(out, dialect="postgres").args["where"].sql()
        assert "total > 10" in where and "region = 'west'" in where
        assert "AND" in where.upper()

    def test_aggregates_are_filtered_before_aggregation(self):
        """The whole point of AST injection over post-filtering: the WHERE
        applies before GROUP BY, so the aggregate itself is computed over
        only the permitted rows."""
        out = apply_policies(
            "SELECT city, sum(total) FROM orders GROUP BY city",
            {"orders": "region = 'west'"}, "postgresql")
        rendered = out.upper()
        assert rendered.index("WHERE") < rendered.index("GROUP BY")

    def test_the_predicate_is_qualified_by_the_tables_alias(self):
        out = apply_policies(
            "SELECT o.total FROM orders AS o JOIN customers AS c "
            "ON o.customer_id = c.id",
            {"orders": "region = 'west'"}, "postgresql")
        assert "o.region = 'west'" in out

    def test_each_policied_table_gets_its_own_predicate(self):
        out = apply_policies(
            "SELECT o.total FROM orders o JOIN customers c "
            "ON o.customer_id = c.id",
            {"orders": "region = 'west'", "customers": "tier = 'gold'"},
            "postgresql")
        assert "o.region = 'west'" in out and "c.tier = 'gold'" in out

    def test_unpolicied_tables_are_untouched(self):
        sql = "SELECT city FROM customers"
        assert apply_policies(sql, {"orders": "region = 'west'"},
                              "postgresql").upper().count("WHERE") == 0


class TestRefusalOverLeakage:
    def test_a_malformed_predicate_refuses_rather_than_concatenates(self):
        """A predicate that does not parse must fail the QUERY, not be pasted
        in as text — failing open here is the vulnerability."""
        with pytest.raises(PolicyError):
            apply_policies("SELECT total FROM orders",
                           {"orders": "region = 'west"}, "postgresql")

    def test_a_policied_table_inside_a_subquery_still_gets_filtered(self):
        out = apply_policies(
            "SELECT * FROM (SELECT total FROM orders) t",
            {"orders": "region = 'west'"}, "postgresql")
        assert "region = 'west'" in out
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `policy.py`**

```python
"""V4 — row policies injected into the parsed AST.

Never concatenated: the predicate is itself PARSED, and a predicate that does
not parse fails the query (PolicyError) rather than being pasted in as text.
Never post-filtered: injection happens inside every SELECT that references
the table, so WHERE applies before GROUP BY and the aggregate is computed
over only the permitted rows. The import path's `apply_rls_filter`
post-filters a DataFrame; the agent path must never import it (spec F4).
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from .validate import _dialect


class PolicyError(Exception):
    """A policy could not be applied safely. The query is refused — failing
    open is the vulnerability this module exists to prevent."""


def apply_policies(sql: str, policies: dict[str, str], family: str) -> str:
    if not policies:
        return sql
    dialect = _dialect(family)
    tree = sqlglot.parse_one(sql, dialect=dialect)

    parsed_predicates: dict[str, exp.Expression] = {}
    for table, predicate in policies.items():
        try:
            parsed_predicates[table] = sqlglot.parse_one(
                predicate, dialect=dialect, into=exp.Condition)
        except Exception as exc:
            raise PolicyError(
                f"policy predicate for {table!r} does not parse: {exc}") from exc

    applied: set[int] = set()
    # Walk every SELECT (subqueries included) and AND the predicate into the
    # WHERE of each one that references a policied table.
    for select in tree.find_all(exp.Select):
        for table in select.find_all(exp.Table):
            pred = parsed_predicates.get(table.name)
            if pred is None:
                continue
            owner = table.find_ancestor(exp.Select)
            if owner is not select:
                continue  # this table belongs to a nested select; handled there
            alias = table.alias or table.name
            qualified = _qualify(pred.copy(), alias)
            select.where(qualified, append=True, copy=False)
            applied.add(id(table))

    for table in tree.find_all(exp.Table):
        if table.name in parsed_predicates and id(table) not in applied:
            raise PolicyError(
                f"table {table.name!r} appears where its row policy cannot "
                "be attached; refusing the query")

    return tree.sql(dialect=dialect)


def _qualify(condition: exp.Expression, alias: str) -> exp.Expression:
    """Prefix unqualified column references with the table's alias, so the
    predicate binds to the policied table even in a multi-table query."""
    for column in condition.find_all(exp.Column):
        if not column.table:
            column.set("table", exp.to_identifier(alias))
    return condition


async def load_policies(db, context, user) -> dict[str, str]:
    """The calling user's predicates, table name -> SQL. Org admins bypass —
    the same rule resolve_rls_expr applies (app/core/rls.py)."""
    from sqlalchemy import select

    from ...core.rls import apply_user_context
    from ...models.models import ObjectRowPolicy, SourceObject

    if user.role.is_org_admin:
        return {}
    rows = (await db.execute(
        select(ObjectRowPolicy, SourceObject.name)
        .join(SourceObject, SourceObject.id == ObjectRowPolicy.source_object_id)
        .where(ObjectRowPolicy.role_id == user.role_id,
               ObjectRowPolicy.org_id == user.org_id,
               SourceObject.data_source_id == context.source_id))).all()
    return {name: apply_user_context(pol.predicate, email=user.email,
                                     user_id=user.id)
            for pol, name in rows}
```

Note for the implementer: if `select.where(..., append=True)` or `find_ancestor` differ in the installed sqlglot version, adapt the *implementation* (e.g. build `exp.and_(existing, qualified)` and `select.set("where", ...)`) until the tests pass — the tests are the contract, and they assert rendered SQL, not sqlglot internals.

- [ ] **Step 4: Run** — all pass. **Step 5: Checkpoint** — `... pytest tests/test_agent_policy.py tests/test_agent_validate.py -q`.

---

### Task 9: generate + repair

**Files:**
- Create: `backend/app/services/agent/nodes/generate.py`
- Create: `backend/app/services/agent/memory.py`
- Test: `backend/tests/test_agent_generate.py`

**Interfaces:**
- Produces:
  - `generate.py`: `GENERATE_SCHEMA` (json_schema: `{"sql": string}`); `async generate_sql(question, context, examples: list[dict], client, *, feedback: str | None = None) -> str | None` — `feedback` carries the previous attempt's specific ladder failure (D4.4's "each with the specific error fed back"); `examples` is `[{"question": ..., "sql": ...}]`.
  - `memory.py`: `async recall(db, org_id, source_id, limit=5) -> list[dict]` (newest first) and `async remember(db, org_id, source_id, question, sql, user_id=None)` — reads/writes `QueryExample`.
- Consumes: `SchemaContext.render()`, `complete_json(..., enforce=True)`.
- Consumed by: Task 11 (which owns the ≤3-attempt repair LOOP; this node is one attempt).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_generate.py`:

```python
"""One generation attempt, and the memory it draws on.

The repair LOOP lives in graph.py; this node is a single attempt whose
prompt carries (a) only the allowed joins, (b) verified examples, and
(c) on retry, the SPECIFIC ladder failure — a model told exactly what was
wrong corrects far more often than one told to try again (D4.4).
"""
from app.models.models import Organization
from app.services.agent.context import JoinInfo, ObjectInfo, SchemaContext
from app.services.agent.memory import recall, remember
from app.services.agent.nodes.generate import GENERATE_SCHEMA, generate_sql


def ctx():
    c = SchemaContext(source_id=1, family="postgresql")
    c.objects["orders"] = ObjectInfo("orders", "table", "Order lines.",
                                     {"id": "integer", "total": "numeric"})
    return c


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append({"messages": messages, "schema": schema, **kw})
        return self.reply


class TestGenerate:
    async def test_returns_the_sql(self):
        client = FakeClient({"sql": "SELECT sum(total) FROM orders"})
        got = await generate_sql("total sales", ctx(), [], client)
        assert got == "SELECT sum(total) FROM orders"

    async def test_enforced_contract_and_schema(self):
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client)
        assert client.calls[0]["enforce"] is True
        assert client.calls[0]["schema"] is GENERATE_SCHEMA

    async def test_examples_reach_the_prompt(self):
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(),
                           [{"question": "orders per city",
                             "sql": "SELECT city, count(*) FROM orders GROUP BY city"}],
                           client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "orders per city" in text

    async def test_repair_feedback_reaches_the_prompt(self):
        client = FakeClient({"sql": "SELECT 1"})
        await generate_sql("q", ctx(), [], client,
                           feedback="V2: no such column: discount")
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "no such column: discount" in text

    async def test_llm_failure_is_none(self):
        assert await generate_sql("q", ctx(), [], FakeClient(None)) is None


class TestMemory:
    async def test_remember_then_recall_round_trips(self, db_session):
        org = Organization(name="Acme")
        db_session.add(org)
        await db_session.flush()
        await remember(db_session, org.id, None, "orders per city",
                       "SELECT city, count(*) FROM orders GROUP BY city")
        await db_session.commit()
        got = await recall(db_session, org.id, None)
        assert got == [{"question": "orders per city",
                        "sql": "SELECT city, count(*) FROM orders GROUP BY city"}]

    async def test_recall_is_org_scoped(self, db_session):
        a, b = Organization(name="A"), Organization(name="B")
        db_session.add_all([a, b])
        await db_session.flush()
        await remember(db_session, a.id, None, "q", "SELECT 1")
        await db_session.commit()
        assert await recall(db_session, b.id, None) == []
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

`nodes/generate.py`:

```python
"""SQL generation — one attempt, under the enforced contract."""
from __future__ import annotations

from ..context import SchemaContext

GENERATE_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string"}},
    "required": ["sql"],
    "additionalProperties": False,
}


async def generate_sql(question: str, context: SchemaContext,
                       examples: list[dict], client, *,
                       feedback: str | None = None) -> str | None:
    parts = [
        "You write ONE SQL SELECT statement answering a business question.",
        "Rules: use only the listed objects and columns; join ONLY on the "
        "listed joins; never write anything but SELECT; prefer explicit "
        "column lists over *.",
        f"\n{context.render()}",
    ]
    if examples:
        shown = "\n".join(f"Q: {e['question']}\nSQL: {e['sql']}"
                          for e in examples)
        parts.append(f"\nVerified examples from this database:\n{shown}")
    messages = [{"role": "system", "content": "\n".join(parts)},
                {"role": "user", "content": f"Question: {question}"}]
    if feedback:
        # D4.4: the specific error, not "try again".
        messages.append({"role": "user", "content": (
            "Your previous attempt was rejected by validation: "
            f"{feedback}. Write a corrected SELECT.")})
    got = await client.complete_json(messages, GENERATE_SCHEMA,
                                     enforce=True, max_tokens=600,
                                     temperature=0.1)
    return (got or {}).get("sql") or None
```

`memory.py`:

```python
"""query_examples: verified question->SQL pairs, recalled as few-shot.

Written only on a successful, sane run (graph.py) — a failed query in the
memory would teach the model its own mistakes.
"""
from __future__ import annotations

from sqlalchemy import select

from ...models.models import QueryExample


async def recall(db, org_id: int, source_id: int | None, limit: int = 5) -> list[dict]:
    q = (select(QueryExample)
         .where(QueryExample.org_id == org_id)
         .order_by(QueryExample.id.desc()).limit(limit))
    if source_id is not None:
        q = q.where(QueryExample.data_source_id == source_id)
    rows = (await db.execute(q)).scalars().all()
    return [{"question": r.question, "sql": r.sql} for r in rows]


async def remember(db, org_id: int, source_id: int | None,
                   question: str, sql: str, user_id: int | None = None) -> None:
    db.add(QueryExample(org_id=org_id, data_source_id=source_id,
                        question=question, sql=sql, confirmed_by=user_id))
```

- [ ] **Step 4: Run** — all pass.

---

### Task 10: Executor — V5 dry run, execute, sanity

**Files:**
- Create: `backend/app/services/agent/executor.py`
- Modify: `backend/app/core/config.py` (**utf-8-sig**) — `agent_row_cap: int = Field(default=5000, ge=1)`, `agent_statement_timeout_s: int = Field(default=30, ge=1)`
- Test: `backend/tests/test_agent_executor.py`

**Interfaces:**
- Produces: `async execute_sql(sql: str, cfg: dict, family: str) -> tuple[list[dict] | None, str | None]` — `(rows, None)` on success, `(None, error)` on failure. Runs entirely in `asyncio.to_thread`; applies the statement timeout (`sample.statement_timeout_sql`, reused from the metadata work), injects `LIMIT agent_row_cap` via sqlglot when no LIMIT is present, dry-runs `EXPLAIN` first (V5), invalidates the connection on failure (the poisoned-connection lesson). `sanity_check(rows, question) -> str | None` — returns a human-readable concern for empty / oversized / all-null results, else None.
- Consumes: `get_engine(cfg)` from `direct_query` (the interactive pool — a person is waiting), `_dialect` from validate.
- Consumed by: Task 11.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_executor.py`:

```python
"""V5 and execution: bounded, timed, off the event loop, honest about limits.

The metadata work's hard-won lessons apply verbatim: blocking DB work goes
through to_thread (a stuck query must not freeze the app), a cancelled
statement poisons its connection (invalidate, do not return it), and every
result is capped — an agent that selects a million rows must cost a LIMIT,
not an OOM.
"""
import pytest
from sqlalchemy import create_engine, text

from app.services.agent import executor
from app.services.agent.executor import execute_sql, sanity_check


@pytest.fixture
def source_db(tmp_path, monkeypatch):
    path = tmp_path / "s.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER, total REAL)"))
        for i in range(20):
            conn.execute(text("INSERT INTO orders VALUES (:i, :t)"),
                         {"i": i, "t": i * 1.5})
    monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)
    yield {"type": "sqlite", "filepath": str(path)}
    eng.dispose()


class TestExecution:
    async def test_a_query_returns_rows(self, source_db):
        rows, err = await execute_sql("SELECT total FROM orders WHERE id = 3",
                                      source_db, "sqlite")
        assert err is None
        assert rows == [{"total": 4.5}]

    async def test_the_row_cap_is_injected_when_no_limit_present(
            self, source_db, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "agent_row_cap", 5)
        rows, err = await execute_sql("SELECT id FROM orders", source_db, "sqlite")
        assert err is None
        assert len(rows) == 5

    async def test_an_existing_smaller_limit_is_respected(self, source_db):
        rows, _ = await execute_sql("SELECT id FROM orders LIMIT 2",
                                    source_db, "sqlite")
        assert len(rows) == 2

    async def test_a_broken_query_returns_the_error_as_a_value(self, source_db):
        rows, err = await execute_sql("SELECT ghost FROM orders",
                                      source_db, "sqlite")
        assert rows is None
        assert "ghost" in err

    async def test_the_error_keeps_the_first_line_only(self, source_db):
        """Same rule as catalog_sync._error_summary: driver messages append
        the failing SQL, and SQL can carry values."""
        rows, err = await execute_sql("SELECT ghost FROM orders",
                                      source_db, "sqlite")
        assert "\n" not in err


class TestSanity:
    def test_empty_is_flagged(self):
        assert "no rows" in sanity_check([], "total sales")

    def test_a_normal_result_passes(self):
        assert sanity_check([{"n": 42}], "total sales") is None

    def test_all_null_is_flagged(self):
        concern = sanity_check([{"n": None}, {"n": None}], "total sales")
        assert concern is not None

    def test_at_the_row_cap_is_flagged_as_probably_truncated(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "agent_row_cap", 3)
        concern = sanity_check([{"n": 1}, {"n": 2}, {"n": 3}], "list orders")
        assert "cap" in concern
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `executor.py`**

```python
"""V5 (dry run) + execution + sanity — the only module that touches the
customer's database, and it does so bounded in three ways: a statement
timeout, an injected row cap, and to_thread so a slow query never holds the
event loop (the lesson the whole app relearned when infer_keys froze it for
four minutes).
"""
from __future__ import annotations

import asyncio

import sqlglot
from sqlglot import exp

from ..metadata import sample
from .validate import _dialect


def _engine_for(cfg: dict):
    """Seam, monkeypatched in tests — the interactive pool, because a person
    is waiting on this answer (the metadata pool is for background work)."""
    from ..direct_query import get_engine
    return get_engine(cfg)


def _cap_rows(sql: str, family: str, cap: int) -> str:
    tree = sqlglot.parse_one(sql, dialect=_dialect(family))
    existing = tree.args.get("limit")
    if existing is None:
        return tree.limit(cap).sql(dialect=_dialect(family))
    return sql


def _first_line(exc: Exception) -> str:
    lines = str(exc).strip().splitlines()
    return (lines[0].strip()[:200] if lines else type(exc).__name__)


def _run(sql: str, cfg: dict, family: str) -> tuple[list[dict] | None, str | None]:
    from sqlalchemy import text

    from ...core.config import settings

    engine = _engine_for(cfg)
    conn = engine.connect()
    try:
        deadline = sample.statement_timeout_sql(
            family, settings.agent_statement_timeout_s)
        if deadline:
            conn.execute(text(deadline))
        capped = _cap_rows(sql, family, settings.agent_row_cap)
        # V5: EXPLAIN first — type errors, ambiguous columns and permission
        # failures surface here without touching a single row.
        conn.execute(text(f"EXPLAIN {capped}"))
        rows = [dict(r._mapping) for r in conn.execute(text(capped))]
        return rows, None
    except Exception as exc:
        # A cancelled statement leaves the connection in an aborted
        # transaction that pool_pre_ping cannot see. Discard it.
        conn.invalidate()
        return None, _first_line(exc)
    finally:
        conn.close()


async def execute_sql(sql: str, cfg: dict, family: str,
                      ) -> tuple[list[dict] | None, str | None]:
    return await asyncio.to_thread(_run, sql, cfg, family)


def sanity_check(rows: list[dict], question: str) -> str | None:
    """Empty / absurd / oversized (spec: sanity node). A concern is a string
    for the answer to CARRY, not a failure — an empty result may be the true
    answer, but the person deserves to know it looked odd."""
    from ...core.config import settings

    if not rows:
        return "the query returned no rows — the answer may be 'none', or a filter may be wrong"
    if len(rows) >= settings.agent_row_cap:
        return (f"the result hit the {settings.agent_row_cap}-row cap and is "
                "probably truncated")
    values = [v for r in rows for v in r.values()]
    if values and all(v is None for v in values):
        return "every value in the result is NULL"
    return None
```

Add the two settings to `config.py` (**utf-8-sig**):

```python
    # The agent's per-query bounds. A generated query is a guess wrapped in a
    # ladder; these are the two promises execution keeps regardless: no query
    # holds the source longer than this, and no result is unbounded.
    agent_statement_timeout_s: int = Field(default=30, ge=1)
    agent_row_cap: int = Field(default=5000, ge=1)
```

- [ ] **Step 4: Run** — all pass. Note: SQLite has no `statement_timeout_sql` (returns None/""), which is why the timeout line is conditional — the tests exercise that path implicitly.

---

### Task 11: The graph — wiring one run end to end

**Files:**
- Create: `backend/app/services/agent/graph.py`, `backend/app/services/agent/plan.py`, `backend/app/services/agent/nodes/explain.py`
- Test: `backend/tests/test_agent_graph.py`

**Interfaces:**
- Produces: `async run_agent(db, *, question: str, source: DataSource, user, client, conversation_id: int | None = None) -> AgentRun` — persists the `AgentRun` + `AgentStep` rows (committed by the caller), status one of `ok | failed | needs_clarification`. On `needs_clarification`, `answer` holds the clarifying question.
- `plan.py`: `PLAN_SCHEMA`; `async plan_steps(question, intent, context, client) -> list[StepSpec]` — falls back to a single step (`[StepSpec("s1", question, [])]`) when the model fails or returns an invalid DAG (a planner failure must degrade to "answer it as one query", never kill the run).
- `nodes/explain.py`: `async explain(question, results: dict[str, StepResult], concerns: list[str], client) -> str | None`; deterministic fallback `render_fallback(results, concerns) -> str` (the numbers, stated plainly) when the LLM is unreachable — a computed answer must not be discarded because prose generation failed.
- Repair loop (lives here, D4.4): per step, up to `3` total generate attempts; each retry feeds `f"{failure.rung}: {failure.detail}"` back into `generate_sql(feedback=...)`. After the third rejection the step fails with the full failure list recorded.
- Consumes: everything from Tasks 3–10 by the exact names given there.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_graph.py`:

```python
"""One question, end to end, with a scripted model and a real SQLite source.

The LLM is faked (deterministic, per-call scripts); the database, catalog,
ladder, policies and executor are real. What these tests pin is the CONTROL
FLOW the spec draws: clarify ends a run, repair is bounded at three, a
failed step never sinks its siblings, and every step leaves an AgentStep row.
"""
import pytest
from sqlalchemy import create_engine, select, text

from app.models.models import (AgentRun, AgentStep, DataSource, Organization,
                               QueryExample, Role, SourceColumn, SourceObject,
                               SourceRelationship, User)
from app.services.agent import executor, graph
from app.services.agent.graph import run_agent


class ScriptedClient:
    """complete_json pops from a script keyed by which schema was asked for."""

    def __init__(self, classify=None, plan=None, generate=None, prose="Answer."):
        self.script = {"classify": list(classify or []),
                       "plan": list(plan or []),
                       "generate": list(generate or [])}
        self.prose = prose
        self.generate_calls = []

    async def complete_json(self, messages, schema, **kw):
        props = set(schema.get("properties", {}))
        if "intent" in props:
            return self.script["classify"].pop(0) if self.script["classify"] else None
        if "steps" in props:
            return self.script["plan"].pop(0) if self.script["plan"] else None
        if "sql" in props:
            self.generate_calls.append("".join(m["content"] for m in messages))
            return self.script["generate"].pop(0) if self.script["generate"] else None
        return None

    async def complete(self, messages, **kw):
        return self.prose


@pytest.fixture
async def world(db_session, tmp_path, monkeypatch):
    """An org, a user, a live SQLite source, and its catalog."""
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    role = Role(name="analyst", org_id=org.id)
    db_session.add(role)
    await db_session.flush()
    user = User(email="a@corp.com", hashed_password="x", org_id=org.id,
                role_id=role.id)
    db_session.add(user)

    path = tmp_path / "shop.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER, total REAL, region TEXT)"))
        conn.execute(text("INSERT INTO orders VALUES (1, 10, 'west'), (2, 20, 'east')"))
    monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)

    ds = DataSource(name="shop", type="sqlite", org_id=org.id,
                    config={"filepath": str(path)})
    db_session.add(ds)
    await db_session.flush()
    obj = SourceObject(data_source_id=ds.id, org_id=org.id, name="orders",
                       kind="table")
    db_session.add(obj)
    await db_session.flush()
    for name, dtype in [("id", "integer"), ("total", "numeric"),
                        ("region", "text")]:
        db_session.add(SourceColumn(source_object_id=obj.id, name=name,
                                    dtype=dtype))
    await db_session.commit()
    yield {"org": org, "user": user, "ds": ds, "obj": obj, "role": role}
    eng.dispose()


NOT_AMBIGUOUS = {"intent": "aggregate", "ambiguous": False, "ambiguity_reason": None}
ONE_STEP = {"steps": [{"id": "s1", "question": "total sales", "depends_on": []}]}


class TestTheHappyPath:
    async def test_question_in_answer_out(self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert run.answer == "Answer."
        steps = (await db_session.execute(select(AgentStep))).scalars().all()
        assert len(steps) == 1
        assert steps[0].sql == "SELECT sum(total) AS total FROM orders"
        assert steps[0].rows_returned == 1

    async def test_a_good_answer_is_remembered(self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        await run_agent(db_session, question="total sales",
                        source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        ex = (await db_session.execute(select(QueryExample))).scalars().all()
        assert len(ex) == 1 and ex[0].question == "total sales"


class TestClarification:
    async def test_an_ambiguous_question_ends_with_a_question(self, db_session, world):
        client = ScriptedClient(
            classify=[{"intent": "lookup", "ambiguous": True,
                       "ambiguity_reason": "no metric named"}],
            prose="Did you mean revenue or order count?")
        run = await run_agent(db_session, question="show me the numbers",
                              source=world["ds"], user=world["user"],
                              client=client)
        assert run.status == "needs_clarification"
        assert run.answer.endswith("?")
        # Nothing was planned, generated or executed.
        assert client.generate_calls == []


class TestRepairIsBounded:
    async def test_a_rejected_query_is_repaired_with_the_specific_error(
            self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT discount FROM orders"},          # V2 fails
                      {"sql": "SELECT sum(total) AS t FROM orders"}])  # fixed
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert "discount" in client.generate_calls[1], (
            "the retry was not told the specific failure")
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.repair_attempts == 1
        assert step.validation_failures[0]["rung"] == "V2"

    async def test_three_rejections_fail_honestly(self, db_session, world):
        bad = {"sql": "SELECT ghost FROM orders"}
        client = ScriptedClient(classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
                                generate=[bad, bad, bad, bad])
        run = await run_agent(db_session, question="q", source=world["ds"],
                              user=world["user"], client=client)
        assert run.status == "failed"
        assert len(client.generate_calls) == 3, "repair is bounded at 3 total attempts"


class TestPoliciesBind:
    async def test_a_row_policy_filters_the_agents_query(self, db_session, world):
        from app.models.models import ObjectRowPolicy
        db_session.add(ObjectRowPolicy(org_id=world["org"].id,
                                       source_object_id=world["obj"].id,
                                       role_id=world["role"].id,
                                       predicate="region = 'west'"))
        await db_session.commit()
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        await db_session.commit()
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        # west only: 10, not 30 — filtered BEFORE aggregation.
        assert step.rows_returned == 1
        assert "region = 'west'" in step.sql


class TestPlannerDegradesGracefully:
    async def test_a_failed_plan_becomes_a_single_step(self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[None],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client)
        assert run.status == "ok"
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

`plan.py`:

```python
"""Question -> typed step DAG.

'Decomposition into ordered steps' (ARCHITECTURE.md plan.py) generalised: a
dependency DAG whose degenerate case is one step — and one step is also the
FALLBACK, because a planner failure must degrade to 'answer it as a single
query', never kill the run.
"""
from __future__ import annotations

from .context import SchemaContext
from .dag import topological_layers
from .state import StepSpec

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array", "minItems": 1, "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "question": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "question", "depends_on"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["steps"],
    "additionalProperties": False,
}


async def plan_steps(question: str, intent: str, context: SchemaContext,
                     client) -> list[StepSpec]:
    fallback = [StepSpec(id="s1", question=question, depends_on=[])]

    got = await client.complete_json(
        [{"role": "system", "content": (
            "Decompose a business question into 1-6 SQL-answerable steps. "
            "Most questions are ONE step; only decompose when sub-answers "
            "genuinely feed each other (a compare of two computed figures, "
            "a filter derived from another query). `depends_on` lists step "
            "ids whose results a step needs.")},
         {"role": "user", "content": (
             f"Database:\n{context.render(max_chars=3000)}\n\n"
             f"Intent: {intent}\nQuestion: {question}")}],
        PLAN_SCHEMA, enforce=True, max_tokens=400, temperature=0.0)
    if not got:
        return fallback

    steps = [StepSpec(id=s["id"], question=s["question"],
                      depends_on=list(s["depends_on"])) for s in got["steps"]]
    try:
        topological_layers(steps)  # validates ids and acyclicity
    except ValueError:
        return fallback
    return steps
```

`nodes/explain.py`:

```python
"""The answer, with provenance — and a deterministic fallback, because a
correctly computed result must not be discarded when prose generation fails."""
from __future__ import annotations

from ..state import StepResult


def _facts(results: dict[str, StepResult]) -> str:
    lines = []
    for r in results.values():
        if r.status == "ok" and r.rows is not None:
            lines.append(f"step {r.step_id}: {r.rows[:20]!r}")
    return "\n".join(lines)


def render_fallback(results: dict[str, StepResult], concerns: list[str]) -> str:
    text = "Result:\n" + _facts(results)
    if concerns:
        text += "\nNotes: " + "; ".join(concerns)
    return text


async def explain(question: str, results: dict[str, StepResult],
                  concerns: list[str], client) -> str | None:
    got = await client.complete(
        [{"role": "system", "content": (
            "Answer the user's question in 1-3 sentences from ONLY the "
            "figures given. State numbers exactly; do not invent any. If "
            "notes are present, work them into the answer honestly.")},
         {"role": "user", "content": (
             f"Question: {question}\n\nFigures:\n{_facts(results)}\n\n"
             f"Notes: {'; '.join(concerns) or 'none'}")}],
        max_tokens=250, temperature=0.2)
    return got.strip() if got else None
```

`graph.py`:

```python
"""One question's journey: classify -> (clarify) -> context -> plan -> DAG of
[generate -> ladder -> policy -> execute -> sanity] -> explain.

The repair loop (D4.4) lives HERE, inside the per-step node: at most
MAX_ATTEMPTS generations, each retry fed the specific rung and detail that
rejected the last. It is a bounded retry inside a node, not a graph edge —
which is precisely why the graph stays acyclic and the executor stays 80
lines (spec S5).
"""
from __future__ import annotations

import asyncio
import time

from ...core.config import settings
from ...models.models import AgentRun, AgentStep, DataSource
from . import memory
from .context import load_context
from .dag import run_dag
from .executor import execute_sql, sanity_check
from .nodes.classify import classify
from .nodes.clarify import clarify
from .nodes.explain import explain, render_fallback
from .nodes.generate import generate_sql
from .plan import plan_steps
from .policy import PolicyError, apply_policies, load_policies
from .state import StepResult, StepSpec
from .validate import validate_sql

#: Total generation attempts per step — the original plus two repairs (D4.4:
#: "maximum three repair attempts, each with the specific error fed back.
#: Then fail honestly with what was tried.")
MAX_ATTEMPTS = 3


async def run_agent(db, *, question: str, source: DataSource, user, client,
                    conversation_id: int | None = None) -> AgentRun:
    started = time.monotonic()
    run = AgentRun(org_id=user.org_id, conversation_id=conversation_id,
                   question=question, status="running")
    db.add(run)
    await db.flush()

    verdict = await classify(question,
                             await load_context(db, source.id, user.org_id),
                             client)
    if verdict is None:
        return _finish(run, started, status="failed",
                       error="the model endpoint could not classify the question")
    run.intent = verdict["intent"]

    if verdict["ambiguous"]:
        ask = await clarify(question, verdict["ambiguity_reason"] or "", client)
        return _finish(run, started, status="needs_clarification",
                       answer=ask or "Could you make the question more specific?")

    context = await load_context(db, source.id, user.org_id)
    if not context.objects:
        return _finish(run, started, status="failed",
                       error="no catalog for this source — run a metadata sync first")

    steps = await plan_steps(question, run.intent, context, client)
    run.plan = [{"id": s.id, "question": s.question,
                 "depends_on": s.depends_on} for s in steps]

    policies = await load_policies(db, context, user)
    examples = await memory.recall(db, user.org_id, source.id)
    cfg = dict(source.config or {})
    cfg["type"] = source.type

    async def node(step: StepSpec, parents: dict[str, StepResult]) -> StepResult:
        node_start = time.monotonic()
        failures: list[dict] = []
        feedback: str | None = None
        parent_facts = "".join(
            f"\nKnown from step {pid}: {p.rows[:5]!r}"
            for pid, p in parents.items() if p.rows)

        for attempt in range(MAX_ATTEMPTS):
            sql = await generate_sql(step.question + parent_facts, context,
                                     examples, client, feedback=feedback)
            if sql is None:
                failures.append({"rung": "generate", "detail": "no SQL produced"})
                break

            failure = validate_sql(sql, context)
            if failure is not None:
                failures.append({"rung": failure.rung, "detail": failure.detail})
                feedback = f"{failure.rung}: {failure.detail}"
                continue

            try:
                final_sql = apply_policies(sql, policies, context.family)
            except PolicyError as exc:
                # A policy that cannot bind is a REFUSAL, not a repair target:
                # the model cannot fix a predicate it never sees.
                failures.append({"rung": "V4", "detail": str(exc)})
                break

            rows, error = await execute_sql(final_sql, cfg, context.family)
            if error is not None:
                failures.append({"rung": "V5", "detail": error})
                feedback = f"execution failed: {error}"
                continue

            return StepResult(step_id=step.id, status="ok", sql=final_sql,
                              rows=rows, error=None,
                              validation_failures=failures,
                              repair_attempts=attempt,
                              ms=int((time.monotonic() - node_start) * 1000))

        return StepResult(step_id=step.id, status="failed", sql=None, rows=None,
                          error=failures[-1]["detail"] if failures else "unknown",
                          validation_failures=failures,
                          repair_attempts=len(failures),
                          ms=int((time.monotonic() - node_start) * 1000))

    gate = asyncio.Semaphore(settings.metadata_sample_concurrency)
    results = await run_dag(steps, node, gate)

    for r in results.values():
        db.add(AgentStep(agent_run_id=run.id, node=r.step_id, status=r.status,
                         sql=r.sql, rows_returned=len(r.rows or []) if r.rows is not None else None,
                         validation_failures=r.validation_failures or None,
                         repair_attempts=r.repair_attempts, ms=r.ms))

    if any(r.status != "ok" for r in results.values()):
        first_bad = next(r for r in results.values() if r.status != "ok")
        return _finish(run, started, status="failed",
                       error=f"step {first_bad.step_id}: {first_bad.error}")

    concerns = [c for r in results.values()
                if (c := sanity_check(r.rows or [], step_question(steps, r.step_id)))]
    answer = await explain(question, results, concerns, client)
    run.answer = answer or render_fallback(results, concerns)

    if not concerns:
        # Only a sane, successful answer is worth teaching from.
        single = [r for r in results.values() if r.sql]
        if len(single) == 1:
            await memory.remember(db, user.org_id, source.id, question,
                                  single[0].sql, user_id=user.id)
    return _finish(run, started, status="ok")


def step_question(steps: list[StepSpec], step_id: str) -> str:
    return next((s.question for s in steps if s.id == step_id), "")


def _finish(run: AgentRun, started: float, *, status: str,
            answer: str | None = None, error: str | None = None) -> AgentRun:
    run.status = status
    if answer is not None:
        run.answer = answer
    if error is not None:
        run.error = error
    run.ms = int((time.monotonic() - started) * 1000)
    return run
```

- [ ] **Step 4: Run** — `... pytest tests/test_agent_graph.py -q` → all pass. This is the task most likely to need small adjustments (e.g. sqlite EXPLAIN syntax is `EXPLAIN QUERY PLAN`-compatible with bare `EXPLAIN`, which works); adjust implementation only.

- [ ] **Step 5: Checkpoint** — `... pytest tests/test_agent_graph.py tests/test_agent_dag.py tests/test_agent_validate.py tests/test_agent_policy.py tests/test_agent_executor.py -q`.

---

### Task 12: Router + startup probe

**Files:**
- Create: `backend/app/routers/agent.py`
- Modify: `backend/app/main.py` (**utf-8-sig**) — register router; add startup probe
- Test: `backend/tests/test_agent_api.py`

**Interfaces:**
- Produces (paths, exact):
  - `POST /agent/conversations` body `{"data_source_id": int, "title": str|None}` → `{"id", "title"}`
  - `GET /agent/conversations` → list for the caller's org
  - `POST /agent/conversations/{cid}/ask` body `{"question": str}` → runs the agent **inline** (v1: the request waits; streaming is deferred) → `{"run_id", "status", "answer", "intent", "error"}` and appends the user + assistant `AgentMessage` rows
  - `GET /agent/runs/{run_id}` → run + its steps (sql, status, failures, ms)
- All lookups follow `check_org` — cross-org is 404.
- Startup probe (spec, Risks): on app startup, fire one `complete_json(..., enforce=True)` against a trivial schema in a background task; if the reply violates the schema, `logger.error` — **the contract broke silently once (`guided_json`); it must never break silently again.** Never blocks startup.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_api.py` (follow the existing API-test idiom in `tests/` — `async_client` fixture with auth headers; copy the setup shape from `tests/test_metadata_api.py` if names differ, but keep these behaviours):

```python
"""The chat API. Org-scoping is the security property under test: every
cross-org probe answers 404 — a 403 would confirm the resource exists."""
import pytest
from sqlalchemy import select

from app.models.models import AgentMessage, AgentRun
from app.services.agent import graph as graph_module


@pytest.fixture
def scripted_ok(monkeypatch):
    """Replace run_agent with a deterministic stand-in: the router's job is
    plumbing and scoping, not the graph (Task 11 owns that)."""
    async def fake_run(db, *, question, source, user, client,
                       conversation_id=None):
        run = AgentRun(org_id=user.org_id, conversation_id=conversation_id,
                       question=question, status="ok", intent="aggregate",
                       answer="Total is 30.")
        db.add(run)
        await db.flush()
        return run
    monkeypatch.setattr("app.routers.agent.run_agent", fake_run)
    return fake_run


class TestConversations:
    async def test_create_and_list(self, async_client, admin_headers, seeded_source):
        r = await async_client.post("/agent/conversations",
                                    json={"data_source_id": seeded_source.id,
                                          "title": "Sales"},
                                    headers=admin_headers)
        assert r.status_code == 200
        listed = await async_client.get("/agent/conversations",
                                        headers=admin_headers)
        assert [c["title"] for c in listed.json()] == ["Sales"]

    async def test_another_orgs_conversation_is_404(self, async_client,
                                                    admin_headers,
                                                    other_org_headers,
                                                    seeded_source):
        r = await async_client.post("/agent/conversations",
                                    json={"data_source_id": seeded_source.id},
                                    headers=admin_headers)
        cid = r.json()["id"]
        probe = await async_client.post(f"/agent/conversations/{cid}/ask",
                                        json={"question": "q"},
                                        headers=other_org_headers)
        assert probe.status_code == 404


class TestAsk:
    async def test_ask_returns_the_answer_and_persists_both_messages(
            self, async_client, admin_headers, seeded_source, scripted_ok,
            db_session):
        r = await async_client.post("/agent/conversations",
                                    json={"data_source_id": seeded_source.id},
                                    headers=admin_headers)
        cid = r.json()["id"]
        got = await async_client.post(f"/agent/conversations/{cid}/ask",
                                      json={"question": "total sales"},
                                      headers=admin_headers)
        assert got.status_code == 200
        assert got.json()["answer"] == "Total is 30."
        msgs = (await db_session.execute(select(AgentMessage))).scalars().all()
        assert [m.role for m in msgs] == ["user", "assistant"]

    async def test_a_run_is_readable_with_its_steps(self, async_client,
                                                    admin_headers,
                                                    seeded_source, scripted_ok):
        r = await async_client.post("/agent/conversations",
                                    json={"data_source_id": seeded_source.id},
                                    headers=admin_headers)
        cid = r.json()["id"]
        run_id = (await async_client.post(f"/agent/conversations/{cid}/ask",
                                          json={"question": "q"},
                                          headers=admin_headers)).json()["run_id"]
        detail = await async_client.get(f"/agent/runs/{run_id}",
                                        headers=admin_headers)
        assert detail.status_code == 200
        assert detail.json()["status"] == "ok"
```

(If the suite's fixture names differ — `async_client`, `admin_headers`, `other_org_headers`, `seeded_source` — reuse whatever `tests/test_metadata_api.py` actually uses; behaviours, not names, are the contract.)

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `routers/agent.py`**

```python
"""The chat surface's API. The pane lives inside the report builder (user's
choice, session of 2026-08-24); v1 answers INLINE — the request waits for
the run — because streaming adds a transport decision that changes nothing
about correctness. The run record makes any later streaming retrofit purely
additive.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import (AgentMessage, AgentRun, AgentStep, Conversation,
                             DataSource, User)
from ..services import llm as llm_service
from ..services.agent.graph import run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class ConversationIn(BaseModel):
    data_source_id: int
    title: str | None = None


class AskIn(BaseModel):
    question: str


@router.post("/conversations")
async def create_conversation(body: ConversationIn,
                              db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    source = await db.get(DataSource, body.data_source_id)
    check_org(source, user, "Data source not found")
    conv = Conversation(org_id=user.org_id, user_id=user.id,
                        data_source_id=source.id,
                        title=body.title or "New conversation")
    db.add(conv)
    await db.commit()
    return {"id": conv.id, "title": conv.title}


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(Conversation).where(Conversation.org_id == user.org_id)
        .order_by(Conversation.id.desc()))).scalars().all()
    return [{"id": c.id, "title": c.title,
             "data_source_id": c.data_source_id} for c in rows]


@router.post("/conversations/{cid}/ask")
async def ask(cid: int, body: AskIn, db: AsyncSession = Depends(get_db),
              user: User = Depends(get_current_user)):
    conv = await db.get(Conversation, cid)
    check_org(conv, user, "Conversation not found")
    source = await db.get(DataSource, conv.data_source_id)
    check_org(source, user, "Conversation not found")

    db.add(AgentMessage(conversation_id=conv.id, role="user",
                        content=body.question))

    run = await run_agent(db, question=body.question, source=source,
                          user=user, client=llm_service.get_client(),
                          conversation_id=conv.id)

    db.add(AgentMessage(conversation_id=conv.id, role="assistant",
                        content=run.answer or run.error or "",
                        agent_run_id=run.id))
    await db.commit()
    return {"run_id": run.id, "status": run.status, "answer": run.answer,
            "intent": run.intent, "error": run.error}


@router.get("/runs/{run_id}")
async def run_detail(run_id: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    run = await db.get(AgentRun, run_id)
    check_org(run, user, "Run not found")
    steps = (await db.execute(select(AgentStep).where(
        AgentStep.agent_run_id == run.id))).scalars().all()
    return {"id": run.id, "status": run.status, "question": run.question,
            "intent": run.intent, "answer": run.answer, "error": run.error,
            "plan": run.plan, "ms": run.ms,
            "steps": [{"node": s.node, "status": s.status, "sql": s.sql,
                       "rows_returned": s.rows_returned,
                       "validation_failures": s.validation_failures,
                       "repair_attempts": s.repair_attempts, "ms": s.ms}
                      for s in steps]}
```

Register in `main.py` (**utf-8-sig**) next to the other routers:

```python
from .routers import agent as agent_router
app.include_router(agent_router.router)
```

And the startup probe, in `main.py`'s existing startup hook:

```python
    async def _probe_llm_contract():
        """F2's silent failure must never recur silently. One tiny enforced
        call; a schema violation is logged at ERROR and nothing else happens —
        the app must start regardless."""
        try:
            from .services import llm as llm_service
            client = llm_service.get_client()
            got = await client.complete_json(
                [{"role": "user", "content": "Reply with the number one."}],
                {"type": "object", "properties": {"n": {"type": "integer"}},
                 "required": ["n"], "additionalProperties": False},
                enforce=True, background=True, max_tokens=30, retries=0)
            if got is None or set(got) != {"n"}:
                logging.getLogger(__name__).error(
                    "LLM json_schema enforcement PROBE FAILED — agent SQL "
                    "contracts are not being grammar-enforced (last_error=%s)",
                    client.last_error)
        except Exception:
            logging.getLogger(__name__).exception("LLM contract probe crashed")

    asyncio.get_running_loop().create_task(_probe_llm_contract())
```

- [ ] **Step 4: Run** — `... pytest tests/test_agent_api.py -q` → all pass.
- [ ] **Step 5: Checkpoint** — **full backend suite** green.

---

### Task 13: Eval harness + CI gate

**Files:**
- Create: `backend/evals/__init__.py` (empty), `backend/evals/run_eval.py`, `backend/evals/golden/fixture.jsonl`
- Test: `backend/tests/test_agent_eval.py`

**Interfaces:**
- Produces: `evals/run_eval.py`: `evaluate(pairs: list[dict], execute) -> dict` where each pair is `{"question", "golden_sql", "generated_sql", "intent"}` and `execute(sql) -> list[dict]`; returns `{"total", "correct", "accuracy", "by_intent": {intent: {"total", "correct"}}}`. **Execution accuracy, not string match**: two queries are equal iff their result sets are equal order-insensitively (sorted rows, values normalised via `str()`).
- `golden/fixture.jsonl` — 10 pairs against the CI fixture schema below (real `maps` golden set is Task 15, generated against the live source).
- Consumed by: CI (`tests/test_agent_eval.py` IS the gate), Task 15.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_agent_eval.py`:

```python
"""The accuracy gate. Structural enforcement was MEASURED passing
semantically wrong answers (spec F2: a trend question classified `lookup`,
valid JSON, confidence 0) — this harness is the only defence, which is why
it is a test and not a script someone remembers to run.

Execution accuracy, not string match: `SELECT sum(total)` and
`SELECT SUM(orders.total)` are the same answer.
"""
from evals.run_eval import evaluate, rows_equal


class TestRowComparison:
    def test_identical_rows_match(self):
        assert rows_equal([{"n": 1}], [{"n": 1}])

    def test_order_does_not_matter(self):
        assert rows_equal([{"c": "a"}, {"c": "b"}], [{"c": "b"}, {"c": "a"}])

    def test_column_names_do_not_matter_values_do(self):
        """Aliases differ between golden and generated SQL; the ANSWER is the
        values, not the labels."""
        assert rows_equal([{"total": 30}], [{"sum": 30}])

    def test_different_values_do_not_match(self):
        assert not rows_equal([{"n": 1}], [{"n": 2}])

    def test_numeric_text_equivalence(self):
        assert rows_equal([{"n": 30}], [{"n": 30.0}])


class TestEvaluate:
    def test_accuracy_and_per_intent_breakdown(self):
        def execute(sql):
            return {"SELECT 1 AS n": [{"n": 1}],
                    "SELECT 2 AS n": [{"n": 2}]}[sql]

        report = evaluate(
            [{"question": "q1", "golden_sql": "SELECT 1 AS n",
              "generated_sql": "SELECT 1 AS n", "intent": "lookup"},
             {"question": "q2", "golden_sql": "SELECT 1 AS n",
              "generated_sql": "SELECT 2 AS n", "intent": "trend"}],
            execute)
        assert report["accuracy"] == 0.5
        assert report["by_intent"]["lookup"]["correct"] == 1
        assert report["by_intent"]["trend"]["correct"] == 0

    def test_a_generated_query_that_crashes_counts_as_wrong(self):
        def execute(sql):
            if sql == "BROKEN":
                raise RuntimeError("nope")
            return [{"n": 1}]

        report = evaluate([{"question": "q", "golden_sql": "SELECT 1",
                            "generated_sql": "BROKEN", "intent": "lookup"}],
                          execute)
        assert report["correct"] == 0
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `evals/run_eval.py`**

```python
"""Execution-accuracy evaluation (spec: 'results, not strings').

The report is broken down BY INTENT because a model change that helps
lookups and breaks trends is invisible in an average.
"""
from __future__ import annotations


def _normalise(rows: list[dict]) -> list[tuple]:
    def norm(v):
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v)
    return sorted(tuple(norm(v) for v in row.values()) for row in rows)


def rows_equal(a: list[dict], b: list[dict]) -> bool:
    """Order-insensitive, alias-insensitive, type-tolerant equality — the
    answer is the VALUES, not the labels or the row order."""
    return _normalise(a) == _normalise(b)


def evaluate(pairs: list[dict], execute) -> dict:
    by_intent: dict[str, dict] = {}
    correct = 0
    for pair in pairs:
        intent = pair.get("intent") or "unknown"
        slot = by_intent.setdefault(intent, {"total": 0, "correct": 0})
        slot["total"] += 1
        try:
            golden = execute(pair["golden_sql"])
            generated = execute(pair["generated_sql"])
            ok = rows_equal(golden, generated)
        except Exception:
            ok = False
        if ok:
            correct += 1
            slot["correct"] += 1
    total = len(pairs)
    return {"total": total, "correct": correct,
            "accuracy": (correct / total) if total else 0.0,
            "by_intent": by_intent}
```

- [ ] **Step 4: Create `evals/golden/fixture.jsonl`** — 10 lines, one JSON object each, against this fixture schema (the same shop schema Task 11's tests build): `orders(id, total, region)`. Example lines (write all 10, two per intent):

```jsonl
{"question": "total sales", "sql": "SELECT sum(total) FROM orders", "intent": "aggregate"}
{"question": "sales in the west", "sql": "SELECT sum(total) FROM orders WHERE region = 'west'", "intent": "aggregate"}
{"question": "how many orders are there", "sql": "SELECT count(*) FROM orders", "intent": "lookup"}
{"question": "what is the total of order 1", "sql": "SELECT total FROM orders WHERE id = 1", "intent": "lookup"}
{"question": "sales by region", "sql": "SELECT region, sum(total) FROM orders GROUP BY region", "intent": "compare"}
{"question": "west versus east sales", "sql": "SELECT region, sum(total) FROM orders WHERE region IN ('west','east') GROUP BY region", "intent": "compare"}
{"question": "orders from largest to smallest", "sql": "SELECT id, total FROM orders ORDER BY total DESC", "intent": "trend"}
{"question": "the three biggest orders", "sql": "SELECT id, total FROM orders ORDER BY total DESC LIMIT 3", "intent": "trend"}
{"question": "which region has the higher sales", "sql": "SELECT region FROM orders GROUP BY region ORDER BY sum(total) DESC LIMIT 1", "intent": "explain"}
{"question": "average order value", "sql": "SELECT avg(total) FROM orders", "intent": "explain"}
```

- [ ] **Step 5: Run** — `... pytest tests/test_agent_eval.py -q` → all pass. **Checkpoint** — full suite.

---

### Task 14: The chat pane

**Files:**
- Create: `frontend/src/components/chat/ChatPane.tsx`
- Modify: `frontend/src/services/api.ts` (add `agentApi`)
- Modify: the report-builder page that hosts panes (locate the container in `frontend/src/pages/` that renders the widget palette — add a "Ask" toggle following the file's existing pane pattern)
- Test: `frontend/src/components/chat/ChatPane.test.tsx`

**Interfaces:**
- Produces: `agentApi = { createConversation(dataSourceId, title?), listConversations(), ask(conversationId, question), runDetail(runId) }` in `api.ts`, typed:

```typescript
export interface AgentAnswer {
  run_id: number
  status: 'ok' | 'failed' | 'needs_clarification'
  answer: string | null
  intent: string | null
  error: string | null
}
export const agentApi = {
  createConversation: (dataSourceId: number, title?: string) =>
    api.post<{ id: number; title: string }>('/agent/conversations',
      { data_source_id: dataSourceId, title }).then(r => r.data),
  listConversations: () =>
    api.get<{ id: number; title: string; data_source_id: number }[]>(
      '/agent/conversations').then(r => r.data),
  ask: (conversationId: number, question: string) =>
    api.post<AgentAnswer>(`/agent/conversations/${conversationId}/ask`,
      { question }).then(r => r.data),
  runDetail: (runId: number) =>
    api.get<{ steps: { sql: string | null; status: string }[] }>(
      `/agent/runs/${runId}`).then(r => r.data),
}
```

- `ChatPane` props: `{ dataSourceId: number }`. Behaviours (each is a test): renders an input and send button; a sent question appears as a user bubble and the answer as an assistant bubble; `needs_clarification` renders the question with a distinct "needs more detail" affordance (the user's next message answers it as a fresh question); `failed` shows the error honestly, styled as an error, never as an answer; a "show SQL" disclosure per answered message fetches `runDetail` and renders the SQL — provenance is the spec's requirement, not a debug extra.

- [ ] **Step 1: Write the failing tests** (`ChatPane.test.tsx`; mock `agentApi` with `vi.spyOn`, follow the idiom of `SourceReview.live.test.tsx`):

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ChatPane from './ChatPane'
import { agentApi } from '../../services/api'

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(agentApi, 'createConversation').mockResolvedValue({ id: 7, title: 'New conversation' })
})

async function send(question: string) {
  render(<ChatPane dataSourceId={2} />)
  fireEvent.change(screen.getByPlaceholderText(/ask/i), { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: /send|ask/i }))
}

describe('asking a question', () => {
  it('shows the question and then the answer', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 1, status: 'ok', answer: 'Total sales are 12,400.',
      intent: 'aggregate', error: null })
    await send('total sales')
    await waitFor(() =>
      expect(screen.getByText('Total sales are 12,400.')).toBeInTheDocument())
    expect(screen.getByText('total sales')).toBeInTheDocument()
  })

  it('renders a clarifying question as a question, not an answer', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 2, status: 'needs_clarification',
      answer: 'Did you mean revenue or order count?', intent: null, error: null })
    await send('show me the numbers')
    await waitFor(() =>
      expect(screen.getByText(/did you mean/i)).toBeInTheDocument())
    expect(screen.getByText(/needs more detail/i)).toBeInTheDocument()
  })

  it('a failure reads as a failure, never as an answer', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 3, status: 'failed', answer: null, intent: null,
      error: 'step s1: no such column: discount' })
    await send('total discounts')
    await waitFor(() =>
      expect(screen.getByText(/no such column/i)).toBeInTheDocument())
  })

  it('show SQL reveals the provenance', async () => {
    vi.spyOn(agentApi, 'ask').mockResolvedValue({
      run_id: 4, status: 'ok', answer: 'Answer.', intent: 'lookup', error: null })
    vi.spyOn(agentApi, 'runDetail').mockResolvedValue({
      steps: [{ sql: 'SELECT sum(total) FROM orders', status: 'ok' }] })
    await send('total sales')
    await waitFor(() => screen.getByText('Answer.'))
    fireEvent.click(screen.getByText(/show sql/i))
    await waitFor(() =>
      expect(screen.getByText(/SELECT sum\(total\)/)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run** — `npx vitest run src/components/chat/ChatPane.test.tsx` → fails (no component).

- [ ] **Step 3: Implement `ChatPane.tsx`** — a lazily created conversation (first send calls `createConversation`, id kept in state), a message list (`{role, text, kind: 'answer'|'clarify'|'error', runId?}`), the input row, and a per-message `details`-style "Show SQL" that calls `runDetail` on first open. Match the styling idiom of `SourceOverview.tsx` (inline styles, same palette). Wire into the report builder behind an "Ask" toggle following that page's existing pane-switching pattern.

- [ ] **Step 4: Run the component tests, then the whole frontend suite** — `npx vitest run` → 707 + new all green.

---

### Task 15: Live verification + golden set against `maps`

**Files:**
- Create: `backend/evals/golden/maps.jsonl` (~25 pairs, generated at execution time)
- No production code changes.

This task is measurement, not construction — the plan's definition of done.

- [ ] **Step 1: Restart the backend so all new code loads**: `docker restart datalytics_backend`.
- [ ] **Step 2: Author ~25 golden pairs against the live `maps` catalog** (read table/column names from the review payload; write questions a real user of a map-grading system would ask — counts of student solutions per state, average scores, symbol counts, comparisons across institutes). **Verify every golden SQL by executing it** against the source before it enters the file; discard any that error or return nothing explainable.
- [ ] **Step 3: Run the agent end-to-end on each golden question** via `POST /agent/conversations/{id}/ask` (script it through `docker exec`, minting a token with the existing `mint_token.py` scratchpad pattern), collect generated SQL from `GET /agent/runs/{id}`, and feed pairs through `evaluate()`.
- [ ] **Step 4: Record the report** (accuracy overall + per intent) in a new section appended to the Layer 4 spec, alongside: number of clarification stops, repair-loop engagement rate, and median run latency.
- [ ] **Step 5: Full suites one last time** — backend + frontend green, and confirm the startup probe logged no enforcement error in `docker logs datalytics_backend`.
- [ ] **Step 6: Update `ARCHITECTURE_COMPARISON.md`** — Layer 4 rescored with measured accuracy attached, HTML rebuilt via `python build_html.py`.

---

## Self-Review (performed while writing)

- **Spec coverage:** classify/clarify (T6), plan/DAG (T4, T11), generate (T9), V1–V3 (T7), V4 (T8), V5+execute+sanity (T10), repair loop (T11), explain (T11), memory (T9), tables (T2), global gate (T3), startup probe (T12), router+surface (T12, T14), eval gate (T13, T15), golden set (T15). Deferred per spec: streaming, Python/ML nodes, Layer 3 retrieval. The reserved-headroom option the spec left open is decided here (T3) — reserved headroom, as the spec itself recommended.
- **Type consistency:** `StepSpec`/`StepResult` defined in T4, consumed by exact field names in T11; `SchemaContext.has_table/has_column/join_allowed/render` defined in T5, consumed in T6/T7/T9; `ValidationFailure(rung, detail)` in T7 consumed in T11; `apply_policies(sql, policies, family)` in T8 consumed in T11; `execute_sql -> (rows, error)` in T10 consumed in T11; `run_agent` in T11 consumed in T12; `agentApi` names in T14 match T12's paths.
- **Placeholder scan:** none — every step carries code or an exact command. The two "adapt the implementation, never the test" notes (T7, T8) are contingency instructions, not placeholders.

---

# Amendment — the agent answers over ALL THREE data modes (Tasks 16–18)

The platform has three ways of holding data, and the user has required all
three (2026-08-25): **DirectQuery** (live SQL — what Tasks 1–15 build),
**import from source**, and **multiple uploaded files**. Imported and uploaded
data live as files loaded by `analytics.load_file(path) -> DataFrame`
(`app/services/analytics.py:20`), with `Dataset.mode = import | directquery`.

**Design: one SQL surface.** duckdb 1.5.5 is already in the app environment
(the metadata cache uses it), and DuckDB queries registered pandas DataFrames
directly. So dataset mode = load the frames, apply each dataset's existing RLS
to the BASE rows, register them as DuckDB tables, and run the generated SQL
with `dialect="duckdb"`. The ladder, repair loop, DAG and explain nodes are
untouched — only context and execution gain a second implementation each,
which is exactly what their interfaces (Tasks 5, 10) exist for.

**RLS note (why this does not violate F4):** post-filtering is forbidden
*after aggregation*. Filtering the base frame BEFORE the agent's SQL runs is
semantically identical to WHERE injection — the aggregate computes over only
permitted rows. Dataset mode reuses `resolve_rls_expr` + `apply_rls_filter`
on the base frames, before registration.

### Task 16: Dataset context — `load_dataset_context`

**Files:**
- Modify: `backend/app/services/agent/context.py`
- Test: `backend/tests/test_agent_dataset_context.py`

**Interfaces:**
- Produces: `async load_dataset_context(db, dataset_ids: list[int], org_id: int) -> SchemaContext` with `family="duckdb"`, `source_id=0`. Each dataset becomes an ObjectInfo named by `_table_name(dataset.name)` (lowercase, non-alphanumeric → `_`, deduplicated with `_2`, `_3`…); columns come from the dataset's stored column metadata (reuse whatever `routers/datasets.py` uses to list columns — `column_meta` + detected dtypes); `description` from `Dataset.description`. Joins: `Relationship` rows between the chosen datasets where `source in (confirmed, declared)` — F1 applies identically.
- Also produces: `_table_name(name: str) -> str` (exported for Task 17's executor to name the registered frames identically — the two MUST agree, so it lives in context.py and executor imports it).

Tests (write first, same style as `test_agent_context.py`): two datasets with columns appear as tables; kinds render as "dataset"; an inferred `Relationship` never enters `joins`; a confirmed one does; datasets from another org yield an empty context; name collisions ("Sales 2024" and "Sales-2024") get distinct table names.

### Task 17: DuckDB execution + graph/router plumbing for dataset mode

**Files:**
- Modify: `backend/app/services/agent/executor.py` — add `async execute_on_datasets(sql: str, frames: dict[str, "pd.DataFrame"]) -> tuple[list[dict] | None, str | None]`: in `asyncio.to_thread`, open `duckdb.connect()` (in-memory, per call), `conn.register(name, frame)` for each, apply the row cap via `_cap_rows(sql, "duckdb", cap)`, execute, `conn.close()`. Same error contract (first line only).
- Modify: `backend/app/services/agent/validate.py` — add `"duckdb": "duckdb"` to `_DIALECTS`.
- Modify: `backend/app/services/agent/graph.py` — `run_agent` gains `datasets: list[Dataset] | None = None` (XOR with `source`). Dataset branch: context from `load_dataset_context`; frames loaded ONCE per run in `to_thread` via `analytics.load_file(ds.filename)`, then per-dataset RLS applied with `resolve_rls_expr(db, user, ds.id)` + `apply_rls_filter(frame, expr)` BEFORE registration; `node()` calls `execute_on_datasets` instead of `execute_sql`; `load_policies` is skipped (dataset RLS already applied at the base). Memory writes record `data_source_id=None`.
- Modify: `backend/app/routers/agent.py` — `ConversationIn` becomes `{data_source_id: int | None, dataset_ids: list[int] | None, title: str | None}` (exactly one of the two required, else 422); `Conversation` gains nothing (store `dataset_ids` in a new JSON column `dataset_ids` on Conversation — add to the Task 2 model + this is a NEW column on a NEW table, still no `_migrate` needed if done before first deploy; otherwise add the `_migrate` line `"ALTER TABLE conversations ADD COLUMN IF NOT EXISTS dataset_ids JSON"`). `ask` resolves whichever target the conversation holds, org-checking EVERY dataset id (404 on any miss).
- Test: `backend/tests/test_agent_dataset_mode.py`

Tests (write first): end-to-end scripted-client run over TWO in-memory CSV datasets (write real temp CSVs, point `Dataset.filename` at them) — a join across the two files answers correctly when a confirmed Relationship exists; the same join is rejected at V3 when the relationship is only inferred; a dataset RLS rule filters the answer's aggregate (west-only sum, the Task 11 pattern); a conversation with a dataset id from another org is 404; `execute_on_datasets` respects the row cap.

### Task 18: Chat pane picks the target

**Files:**
- Modify: `frontend/src/components/chat/ChatPane.tsx`, `frontend/src/services/api.ts`
- Test: extend `frontend/src/components/chat/ChatPane.test.tsx`

`agentApi.createConversation(target: {dataSourceId?: number; datasetIds?: number[]}, title?)` replaces the Task 14 signature (update its call sites in the same edit). `ChatPane` props become `{ dataSourceId?: number; datasetIds?: number[] }` — the report builder passes whatever the report is bound to (its dataset ids — including several for multi-file reports — or its source). Tests: asking with `datasetIds=[3,4]` sends them in `createConversation`; the existing four behaviours still pass unchanged.

**Definition of done for the amendment:** Task 15's live verification additionally runs one multi-file scenario — two uploaded CSVs joined by a confirmed relationship, one question answered through the chat pane — and records it in the spec appendix alongside the maps numbers.
