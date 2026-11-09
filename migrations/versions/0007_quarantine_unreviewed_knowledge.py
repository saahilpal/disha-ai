"""Quarantine health content that was auto-approved with placeholder reviewer IDs.

Revision ID: 0007_quarantine_unreviewed_knowledge
Revises: 0006_product_fact_truth
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007_quarantine_unreviewed_knowledge"
down_revision: Union[str, None] = "0006_product_fact_truth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    UPDATE clinical_knowledge_base
    SET approval_status = 'draft', clinician_id = NULL, approved_at = NULL
    WHERE approval_status = 'approved'
      AND clinician_id IN (
          'clin_lead_icmr', 'clin_lead_ayush', 'clin_lead_01', 'clin_lead_02',
          'dr_fit_india_ayush'
      );

    ALTER TABLE patient_pep
        ALTER COLUMN dietary_preference DROP DEFAULT;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Quarantined health content requires a genuine review before approval; "
        "restore from a pre-migration backup only if required."
    )
