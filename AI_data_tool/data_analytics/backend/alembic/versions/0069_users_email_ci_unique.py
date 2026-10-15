"""User emails are unique regardless of letter case (E-02 follow-up).

Before E-02 an address was compared exactly as typed, so `ADMIN@x` and
`admin@x` could both exist, and a case-variant of a platform-admin address
counted as a platform admin. The application now normalises every new email
(trim + lower) and checks duplicates case-insensitively; this revision makes
the database enforce it too.

1. Look for addresses that differ only by letter case. If there are any, the
   upgrade STOPS with a message naming every such account: which one is the
   real person is a decision for an administrator, never for a migration (no
   account is merged, renamed or deleted here).
2. Otherwise store every address lower-case (no collision is possible now).
3. Add a unique index on lower(email) -- a functional index on Postgres and on
   SQLite (both support index expressions).

Every step is idempotent, so a re-run (or `_ensure_users_email_ci_unique` in
app.main, which does the same for databases adopted without running
revisions) is a no-op.

Revision ID: 0069_users_email_ci_unique
Revises: 0068_publishing_sharing
"""
from alembic import op
import sqlalchemy as sa

revision = "0069_users_email_ci_unique"
down_revision = "0068_publishing_sharing"
branch_labels = None
depends_on = None

INDEX_NAME = "ux_users_email_lower"

#: app.main._ensure_users_email_ci_unique runs the same query, so both paths
#: find and report the same accounts.
CASE_DUPLICATES_SQL = (
    "SELECT id, org_id, email FROM users WHERE lower(trim(email)) IN ("
    " SELECT lower(trim(email)) FROM users GROUP BY lower(trim(email)) HAVING COUNT(*) > 1)"
    " ORDER BY lower(trim(email)), id"
)


def describe_case_duplicates(rows) -> str:
    """The refusal message: every account involved, grouped by address."""
    lines = [f"  user id={r[0]} org_id={r[1]} email={r[2]!r}" for r in rows]
    return (
        "users.email: these accounts differ only by letter case (or surrounding spaces), so a unique "
        "lower(email) index cannot be added. An administrator must rename or "
        "remove the extra account(s) (nothing was changed), then re-run the "
        "upgrade:\n" + "\n".join(lines)
    )


def upgrade() -> None:
    bind = op.get_bind()
    dupes = bind.execute(sa.text(CASE_DUPLICATES_SQL)).fetchall()
    if dupes:
        raise RuntimeError(describe_case_duplicates(dupes))
    bind.execute(sa.text("UPDATE users SET email = lower(trim(email)) WHERE email <> lower(trim(email))"))
    op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} ON users (lower(email))")


def downgrade() -> None:
    # Addresses stay lower-case: the original capitals are not recorded, and
    # login matches any case anyway.
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
