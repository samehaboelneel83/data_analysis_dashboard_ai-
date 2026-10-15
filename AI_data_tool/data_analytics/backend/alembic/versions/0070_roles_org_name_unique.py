"""Role names are unique per organization, whatever their letter case (E-15).

"QA E Role" could be created twice in one org, which made role pickers, rule
lists and the bulk import's role-by-name ambiguous. The API now refuses a
duplicate (409); this revision makes the database enforce it too.

1. Existing duplicates within an org (compared trimmed and lower-case) keep
   their users and rules: the oldest role keeps its name, each later one is
   renamed "<name> (2)", "<name> (3)", ... -- skipping any name already taken
   in that org. Nothing is merged or deleted.
2. A unique index on (org_id, lower(name)) -- functional on Postgres and
   SQLite alike.

Idempotent: with no duplicates left, step 1 changes nothing, and the index is
created IF NOT EXISTS. `app.main._ensure_roles_name_unique` does the same for
databases stamped at head without running revisions.

Revision ID: 0070_roles_org_name_unique
Revises: 0069_users_email_ci_unique
"""
from alembic import op
import sqlalchemy as sa

revision = "0070_roles_org_name_unique"
down_revision = "0069_users_email_ci_unique"
branch_labels = None
depends_on = None

INDEX_NAME = "ux_roles_org_name_lower"


def rename_duplicate_roles(bind) -> list[tuple[int, str, str]]:
    """Rename every later duplicate; returns (role id, old name, new name)."""
    rows = bind.execute(sa.text("SELECT id, org_id, name FROM roles ORDER BY org_id, id")).fetchall()
    taken: dict[int, set[str]] = {}
    for _id, org_id, name in rows:
        taken.setdefault(org_id, set()).add((name or "").strip().lower())
    seen: dict[tuple[int, str], int] = {}
    renamed = []
    for role_id, org_id, name in rows:
        key = (org_id, (name or "").strip().lower())
        if key not in seen:
            seen[key] = role_id
            continue
        base, n = (name or "").strip(), 2
        while f"{base} ({n})".lower() in taken[org_id]:
            n += 1
        new = f"{base} ({n})"
        taken[org_id].add(new.lower())
        bind.execute(sa.text("UPDATE roles SET name = :n WHERE id = :i"), {"n": new, "i": role_id})
        renamed.append((role_id, name, new))
    return renamed


def upgrade() -> None:
    bind = op.get_bind()
    rename_duplicate_roles(bind)
    op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} ON roles (org_id, lower(name))")


def downgrade() -> None:
    # Renamed roles keep their new names: which ones were renamed is not recorded.
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
