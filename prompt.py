"""Chat UI: NL question → Qwen SQL → Wren execute → results."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
MAPS_PROJECT = APP_DIR / "maps_project"
MDL_PATH = MAPS_PROJECT / "target" / "mdl.json"
CHAT_COMPLETIONS_URL = "http://10.125.18.189:8000/v1/chat/completions"
DEFAULT_MODEL = "qwen3.5"
WREN_CMD = shutil.which("wren") or r"C:\Users\EBAGZ\anaconda3\envs\db\Scripts\wren.exe"

app = FastAPI(title="Wren AI Chat")


class ChatRequest(BaseModel):
    message: str
    model: str = DEFAULT_MODEL
    max_tokens: int = Field(default=1024, ge=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    reply: str
    sql: str | None = None
    rows: list[dict[str, Any]] | None = None
    row_count: int = 0
    error: str | None = None


def load_schema_summary() -> str:
    if not MDL_PATH.exists():
        return "Schema unavailable — run `wren context build` in maps_project."

    data = json.loads(MDL_PATH.read_text(encoding="utf-8"))
    lines: list[str] = []
    for model in data.get("models", []):
        cols = ", ".join(c["name"] for c in model.get("columns", []))
        lines.append(f"- {model['name']}({cols})")
    rels = data.get("relationships") or []
    if rels:
        lines.append("\nRelationships:")
        for rel in rels[:15]:
            models = rel.get("models", [])
            if len(models) == 2:
                lines.append(f"- {models[0]} -> {models[1]}: {rel.get('condition', '')}")
    return "\n".join(lines)


def build_sql_system_prompt(schema: str) -> str:
    return f"""You are a SQL assistant for a PostgreSQL database accessed through Wren AI.

Use ONLY these Wren MDL model names (not raw public.table names unless they match):
{schema}

Rules:
1. Return ONLY one SQL query inside a ```sql code block.
2. Use SELECT or WITH only. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE.
3. Prefer model names from the list above.
4. Add LIMIT 100 unless the user asks for all rows or uses aggregation only.
5. No explanation outside the sql block."""


def extract_sql(text: str) -> str | None:
    block = re.search(r"```(?:sql)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    candidate = block.group(1).strip() if block else text.strip()
    candidate = candidate.strip("`").strip()
    if not candidate:
        return None
    # Use first statement if multiple
    parts = [p.strip() for p in candidate.split(";") if p.strip()]
    return parts[0] if parts else None


def is_readonly_sql(sql: str) -> bool:
    normalized = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL).strip().upper()
    forbidden = (
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "DROP ",
        "ALTER ",
        "TRUNCATE ",
        "CREATE ",
        "GRANT ",
        "REVOKE ",
    )
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        return False
    return not any(tok in normalized for tok in forbidden)


def call_llm(messages: list[dict[str, str]], model: str, max_tokens: int, temperature: float) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.95,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    response = requests.post(
        CHAT_COMPLETIONS_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=180,
    )
    if not response.ok:
        try:
            detail = response.json()
        except json.JSONDecodeError:
            detail = response.text
        raise HTTPException(status_code=502, detail=f"Model API error: {detail}")

    data = response.json()
    choice = data.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content") or choice.get("text") or ""
    return content.strip()


def run_wren_query(sql: str) -> tuple[list[dict[str, Any]], str | None]:
    proc = subprocess.run(
        [WREN_CMD, "query", "--sql", sql, "-o", "json", "--quiet"],
        cwd=str(MAPS_PROJECT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "Wren query failed").strip()
        return [], err

    rows: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows, None


def summarize_results(question: str, sql: str, rows: list[dict[str, Any]], model: str) -> str:
    preview = rows[:20]
    payload_rows = json.dumps(preview, ensure_ascii=False, default=str)
    messages = [
        {
            "role": "system",
            "content": "Summarize SQL query results briefly for the user in plain language. Be concise.",
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\nSQL: {sql}\n"
                f"Rows returned: {len(rows)}\nData (sample):\n{payload_rows}"
            ),
        },
    ]
    try:
        return call_llm(messages, model, max_tokens=512, temperature=0.3)
    except HTTPException:
        if not rows:
            return "Query ran successfully but returned no rows."
        return f"Query returned {len(rows)} row(s)."


@app.get("/")
def chat_page() -> FileResponse:
    return FileResponse(APP_DIR / "chat.html")


@app.get("/prompt-ui")
def prompt_page() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    question = body.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Message is required.")

    schema = load_schema_summary()
    sql_raw = call_llm(
        [
            {"role": "system", "content": build_sql_system_prompt(schema)},
            {"role": "user", "content": question},
        ],
        body.model,
        body.max_tokens,
        body.temperature,
    )

    sql = extract_sql(sql_raw)
    if not sql:
        return ChatResponse(
            reply="Could not extract SQL from the model response.",
            error=sql_raw[:2000],
        )

    if not is_readonly_sql(sql):
        return ChatResponse(
            reply="Only read-only SELECT queries are allowed.",
            sql=sql,
            error="Blocked non-SELECT statement.",
        )

    rows, wren_error = run_wren_query(sql)
    if wren_error:
        return ChatResponse(
            reply="SQL was generated but Wren failed to execute it.",
            sql=sql,
            error=wren_error,
        )

    summary = summarize_results(question, sql, rows, body.model)
    return ChatResponse(
        reply=summary,
        sql=sql,
        rows=rows,
        row_count=len(rows),
    )


# Keep legacy raw prompt proxy
class CompletionRequest(BaseModel):
    prompt: str
    model: str = DEFAULT_MODEL
    max_tokens: int = Field(default=512, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    stream: bool = False


@app.post("/api/completions")
def completions(body: CompletionRequest) -> dict[str, Any]:
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required.")

    payload = {
        "model": body.model or DEFAULT_MODEL,
        "messages": [{"role": "user", "content": body.prompt}],
        "max_tokens": body.max_tokens,
        "temperature": body.temperature,
        "top_p": body.top_p,
        "stream": body.stream,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    response = requests.post(CHAT_COMPLETIONS_URL, json=payload, timeout=120)
    data = response.json()
    if not response.ok:
        raise HTTPException(status_code=response.status_code, detail=data)
    choice = data.get("choices", [{}])[0]
    message = choice.get("message") or {}
    if message.get("content") is not None:
        choice["text"] = message["content"]
    return data


if __name__ == "__main__":
    uvicorn.run("prompt:app", host="0.0.0.0", port=5000, reload=True)
