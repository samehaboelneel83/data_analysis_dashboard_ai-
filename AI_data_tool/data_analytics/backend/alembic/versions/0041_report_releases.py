"""Report releases: the `report_releases` table (E09).

Viewers of a released report see its latest release, a frozen copy of the
content, while editors change the draft. See `ReportRelease` in models.py.

No backfill: a published report is given its first release the first time it
is edited after this ships, from exactly what its viewers were seeing (see
`reports._bump_revision`). Until then nothing about it changes.

A brand-new table, so `create_all` also provisions it on a running install; no
inline ALTER is needed in `main.py`.

Revision ID: 0041_report_releases
Revises: 0040_jobs
"""
from alembic import op
import sqlalchemy as sa

revision = "0041_report_releases"
down_revision = "0040_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_releases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("reason", sa.String(20), nullable=False, server_default="release"),
        sa.Column("released_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_report_releases_report_id", "report_releases", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_report_releases_report_id", table_name="report_releases")
    op.drop_table("report_releases")
