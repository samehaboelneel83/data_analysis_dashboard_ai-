"""Generate Wren MDL model YAML files from PostgreSQL public schema."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import psycopg2
import yaml
from wren.type_mapping import parse_type

PROJECT_DIR = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_DIR / "models"


def load_dotenv() -> None:
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def pg_type(data_type: str, udt_name: str, char_max: int | None, num_prec, num_scale) -> str:
    if data_type == "USER-DEFINED":
        return udt_name
    if data_type == "character varying":
        return f"varchar({char_max})" if char_max else "varchar"
    if data_type == "character":
        return f"char({char_max})" if char_max else "char"
    if data_type == "numeric" and num_prec is not None:
        if num_scale is not None:
            return f"numeric({num_prec},{num_scale})"
        return f"numeric({num_prec})"
    return data_type


def normalize_type(raw_type: str) -> str:
    return parse_type(raw_type, "postgres")


def fetch_schema(connection_url: str) -> tuple[list[str], dict, list[dict]]:
    conn = psycopg2.connect(connection_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
            tables = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                SELECT table_name, column_name, data_type, udt_name,
                       character_maximum_length, numeric_precision, numeric_scale,
                       is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            columns_by_table: dict[str, list[dict]] = {t: [] for t in tables}
            table_set = set(tables)
            for row in cur.fetchall():
                table_name, column_name, data_type, udt_name, char_max, num_prec, num_scale, is_nullable = row
                if table_name not in table_set:
                    continue
                raw = pg_type(data_type, udt_name, char_max, num_prec, num_scale)
                columns_by_table[table_name].append(
                    {
                        "name": column_name,
                        "raw_type": raw,
                        "not_null": is_nullable == "NO",
                    }
                )

            cur.execute(
                """
                SELECT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY tc.table_name, kcu.ordinal_position
                """
            )
            pk_by_table: dict[str, list[str]] = {}
            for table_name, column_name in cur.fetchall():
                pk_by_table.setdefault(table_name, []).append(column_name)

            cur.execute(
                """
                SELECT
                    tc.table_name AS fk_table,
                    kcu.column_name AS fk_column,
                    ccu.table_name AS pk_table,
                    ccu.column_name AS pk_column,
                    tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema = tc.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'FOREIGN KEY'
                ORDER BY tc.table_name, kcu.ordinal_position
                """
            )
            relationships = []
            seen: set[str] = set()
            for fk_table, fk_column, pk_table, pk_column, constraint_name in cur.fetchall():
                if fk_table not in tables or pk_table not in tables:
                    continue
                rel_name = re.sub(r"[^a-zA-Z0-9_]+", "_", constraint_name).lower()
                if rel_name in seen:
                    continue
                seen.add(rel_name)
                fk_model = fk_table
                pk_model = pk_table
                relationships.append(
                    {
                        "name": rel_name,
                        "models": [fk_model, pk_model],
                        "join_type": "MANY_TO_ONE",
                        "condition": f"{fk_model}.{fk_column} = {pk_model}.{pk_column}",
                    }
                )

            return tables, columns_by_table, pk_by_table, relationships
    finally:
        conn.close()


def write_model(table: str, columns: list[dict], pk_cols: list[str]) -> None:
    normalized = []
    for col in columns:
        normalized.append(
            {
                "name": col["name"],
                "type": normalize_type(col["raw_type"]),
                "is_calculated": False,
                "not_null": col["not_null"],
                "is_primary_key": col["name"] in pk_cols,
                "properties": {},
            }
        )

    primary_key = pk_cols[0] if len(pk_cols) == 1 else pk_cols if pk_cols else normalized[0]["name"]

    model = {
        "name": table,
        "properties": {"description": f"Table public.{table}"},
        "table_reference": {"catalog": "", "schema": "public", "table": table},
        "columns": normalized,
        "primary_key": primary_key,
        "cached": False,
    }

    model_dir = MODELS_DIR / table
    model_dir.mkdir(parents=True, exist_ok=True)
    with (model_dir / "metadata.yml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(model, f, sort_keys=False, allow_unicode=True)


def main() -> None:
    load_dotenv()
    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_PORT"]
    database = os.environ["POSTGRES_DATABASE"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    tables, columns_by_table, pk_by_table, relationships = fetch_schema(url)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for table in tables:
        write_model(table, columns_by_table[table], pk_by_table.get(table, []))

    rel_path = PROJECT_DIR / "relationships.yml"
    with rel_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump({"relationships": relationships}, f, sort_keys=False, allow_unicode=True)

    knowledge_dir = PROJECT_DIR / "knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    (knowledge_dir / "knowledge.yml").write_text("schema_version: 1\n", encoding="utf-8")

    print(json.dumps({"tables": len(tables), "relationships": len(relationships)}, indent=2))


if __name__ == "__main__":
    main()
