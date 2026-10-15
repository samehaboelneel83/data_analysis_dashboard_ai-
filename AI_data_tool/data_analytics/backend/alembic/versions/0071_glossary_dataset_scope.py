"""A glossary term may belong to ONE dataset (B-21).

The glossary only worked per connection: an uploaded dataset (Demo -- Sales)
had no place for its terms, and a column could not be linked to one. A term
with `dataset_id` set is that dataset's: shown and used only where that
dataset is readable. Existing terms keep `dataset_id` NULL, so org-wide terms
stay org-wide and a connection's terms stay its own.

Revision ID: 0071_glossary_dataset_scope
Revises: 0070_roles_org_name_unique
"""
from alembic import op
import sqlalchemy as sa

revision = "0071_glossary_dataset_scope"
down_revision = "0070_roles_org_name_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a table to add a foreign key in place.
    with op.batch_alter_table("glossary_terms") as batch:
        batch.add_column(sa.Column("dataset_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_glossary_terms_dataset_id", "datasets", ["dataset_id"], ["id"],
                                 ondelete="CASCADE")
    op.create_index("ix_glossary_terms_dataset_id", "glossary_terms", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_glossary_terms_dataset_id", table_name="glossary_terms")
    with op.batch_alter_table("glossary_terms") as batch:
        batch.drop_constraint("fk_glossary_terms_dataset_id", type_="foreignkey")
        batch.drop_column("dataset_id")
