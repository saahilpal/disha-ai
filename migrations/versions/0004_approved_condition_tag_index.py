"""Index approved guideline condition tags for metadata-assisted RAG lookup.

Revision ID: 0004_approved_condition_tag_index
Revises: 0003_knowledge_and_product_facts
Create Date: 2026-11-09 00:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_approved_condition_tag_index"
down_revision: Union[str, None] = "0003_knowledge_and_product_facts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_clinical_condition_approved "
        "ON clinical_knowledge_base(condition_tag) WHERE approval_status = 'approved'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_clinical_condition_approved")
