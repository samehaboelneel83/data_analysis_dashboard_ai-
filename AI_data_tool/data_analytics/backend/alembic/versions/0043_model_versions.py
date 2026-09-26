"""Model versions: `prediction_models.version/status/card/promoted_*` (E13).

A saved model's name was unique per dataset, so retraining meant deleting the
model a dashboard was scoring with, and nothing recorded how a model had been
chosen. Training under an existing name now makes its next version; one
version per name is the champion; the card records the comparison it won.

Existing rows become version 1, champion (each name had one row), with no
card. The unique key moves from (org, dataset, name) to (org, dataset, name,
version). The columns also ship as `main.py` inline ALTERs, and the key swap
too, for installs that were provisioned by create_all.

Revision ID: 0043_model_versions
Revises: 0042_ai_budget
"""
from alembic import op
import sqlalchemy as sa

revision = "0043_model_versions"
down_revision = "0042_ai_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prediction_models") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="champion"))
        batch_op.add_column(sa.Column("card", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("promoted_by", sa.Integer(),
                                      sa.ForeignKey("users.id", ondelete="SET NULL",
                                                    name="fk_prediction_models_promoted_by"),
                                      nullable=True))
        batch_op.drop_constraint("uq_prediction_models_org_dataset_name", type_="unique")
        batch_op.create_unique_constraint("uq_prediction_models_org_dataset_name_version",
                                          ["org_id", "dataset_id", "name", "version"])


def downgrade() -> None:
    # Only the champions can survive the old key (one row per name).
    op.execute("DELETE FROM prediction_models WHERE status <> 'champion'")
    with op.batch_alter_table("prediction_models") as batch_op:
        batch_op.drop_constraint("uq_prediction_models_org_dataset_name_version", type_="unique")
        batch_op.create_unique_constraint("uq_prediction_models_org_dataset_name",
                                          ["org_id", "dataset_id", "name"])
        batch_op.drop_constraint("fk_prediction_models_promoted_by", type_="foreignkey")
        batch_op.drop_column("promoted_by")
        batch_op.drop_column("promoted_at")
        batch_op.drop_column("card")
        batch_op.drop_column("status")
        batch_op.drop_column("version")
