"""Remove unverified commercial and meal-template claims from product facts.

Revision ID: 0006_product_fact_truth
Revises: 0005_runtime_schema_alignment
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_product_fact_truth"
down_revision: Union[str, None] = "0005_runtime_schema_alignment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE product_facts
        ADD COLUMN IF NOT EXISTS owner VARCHAR(64) NOT NULL DEFAULT 'product_team',
        ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS verification_status VARCHAR(64) NOT NULL DEFAULT 'unknown';

    UPDATE product_facts
    SET fact_value = '{"status":"unknown"}'::jsonb,
        description = 'Awaiting verified product information from the responsible team.',
        is_verified = FALSE,
        verification_status = 'unknown',
        updated_at = NOW()
    WHERE fact_key IN (
        'pricing_followup_consultations',
        'pricing_dedicated_nutritionist',
        'channel_delivery_policy'
    );

    DELETE FROM product_facts
    WHERE fact_key IN (
        'diet_template_jain',
        'diet_template_vegetarian',
        'diet_template_non_vegetarian',
        'pep_clearance_hypertension_stage1',
        'pep_clearance_cardiac_severe',
        'pep_clearance_healthy_adult'
    );
    """)


def downgrade() -> None:
    raise RuntimeError(
        "0006 removes unverified product claims and meal templates. "
        "Restore from a pre-migration backup instead of recreating those claims."
    )
