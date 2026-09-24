"""A store for fitted models, so a champion can score new rows.

Every analysis here refits and discards, which answers "what could predict
this" and never "score these rows". This table is what closes that.

`artifact` is a joblib pickle written only by
`services/analysis/model_store.py` -- nothing accepts an uploaded model, since
loading a pickle executes code.

Revision ID: 0027_prediction_models
Revises: 0026_page_background
"""
import sqlalchemy as sa
from alembic import op

revision = "0027_prediction_models"
down_revision = "0026_page_background"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("dataset_id", sa.Integer(),
                  sa.ForeignKey("datasets.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        # The columns a caller must supply, and the ENCODED columns the
        # estimator expects in order. They differ whenever a categorical
        # predictor is one-hot encoded.
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("feature_columns", sa.JSON(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("model_family", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_name", sa.String(length=32), nullable=True),
        sa.Column("artifact", sa.LargeBinary(), nullable=False),
        # The row filter the model was fitted under: it may only be used by
        # somebody who sees the same rows.
        sa.Column("trained_rls", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", "dataset_id", "name",
                            name="uq_prediction_models_org_dataset_name"),
    )


def downgrade() -> None:
    op.drop_table("prediction_models")
