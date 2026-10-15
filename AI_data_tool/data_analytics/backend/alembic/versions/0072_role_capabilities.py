"""What each role may do: roles.permissions (QA E-08).

A JSON map {capability: bool} (app/core/role_permissions.py). Existing roles
get NULL, which means every capability is allowed -- exactly today's
behaviour, so nobody loses a right on upgrade. An org-admin role always has
every capability whatever is stored.

`app.main._migrate` adds the same column (ADD COLUMN IF NOT EXISTS) for
databases stamped at head without running revisions.

Revision ID: 0072_role_capabilities
Revises: 0070_roles_org_name_unique
"""
from alembic import op
import sqlalchemy as sa

revision = "0072_role_capabilities"
down_revision = "0070_roles_org_name_unique"
branch_labels = None
depends_on = None


def _has_column() -> bool:
    return "permissions" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("roles")}


def upgrade() -> None:
    if not _has_column():
        op.add_column("roles", sa.Column("permissions", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column("roles", "permissions")
