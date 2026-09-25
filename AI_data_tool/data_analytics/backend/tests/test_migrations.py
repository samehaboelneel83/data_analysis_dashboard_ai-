"""T1/T2's ALTER-IF-NOT-EXISTS lines in app.main._migrate.

create_all makes new TABLES for free, but never adds a column to a table that
already exists in a live database -- that is what this function is for. A
column added to the ORM model with nothing here is invisible on every
deployed database until someone notices the 500s.
"""
from app.main import _migrate


class _RecordingConn:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, stmt):
        # SQLAlchemy `text()` clauses stringify back to the SQL they hold.
        self.statements.append(str(stmt))


class TestMigrate:
    async def test_source_objects_gets_is_canonical(self):
        conn = _RecordingConn()
        await _migrate(conn)
        assert any(
            "source_objects" in s and "is_canonical" in s and "BOOLEAN" in s
            for s in conn.statements
        )

    async def test_source_columns_gets_enum_labels_and_its_provenance(self):
        conn = _RecordingConn()
        await _migrate(conn)
        assert any(
            "source_columns" in s and "enum_labels" in s and "JSON" in s
            and "enum_labels_source" not in s
            for s in conn.statements
        )
        assert any(
            "source_columns" in s and "enum_labels_source" in s and "VARCHAR" in s
            for s in conn.statements
        )

    async def test_datasets_gets_query_model_and_is_idempotent(self):
        """D1: the builder graph column, and the whole migration list is safe to
        run twice -- every statement is IF NOT EXISTS, so a second startup against
        an already-migrated database is a no-op, not an error."""
        conn = _RecordingConn()
        await _migrate(conn)
        assert any(
            "datasets" in s and "query_model" in s and "JSON" in s and "IF NOT EXISTS" in s
            for s in conn.statements
        )
        first_run = list(conn.statements)
        await _migrate(conn)
        assert conn.statements == first_run + first_run

    async def test_datasets_gets_custom_functions_column(self):
        """Custom calculated-column functions: Dataset.custom_functions must be
        added to an already-deployed database via _migrate, the same way
        calculated_columns/measures are -- Alembic alone does not reach existing
        deployments (see main.py's _migrate docstring)."""
        conn = _RecordingConn()
        await _migrate(conn)
        assert any(
            "datasets" in s and "custom_functions" in s and "JSON" in s and "IF NOT EXISTS" in s
            for s in conn.statements
        )

    async def test_data_sources_gets_custom_connector_id_column(self):
        """Custom connector framework: data_sources.custom_connector_id must be
        added to an already-deployed database via _migrate, the same way
        created_by was (see main.py's _migrate docstring)."""
        conn = _RecordingConn()
        await _migrate(conn)
        assert any(
            "data_sources" in s and "custom_connector_id" in s and "IF NOT EXISTS" in s
            for s in conn.statements
        )
