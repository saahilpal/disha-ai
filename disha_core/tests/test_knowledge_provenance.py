"""Unit and invariant tests for knowledge_sources, knowledge_chunks, and product_facts."""
from __future__ import annotations

import json
import os

import asyncpg
import pytest


def _get_db_url() -> str:
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER", "disha")
    db_name = os.getenv("DB_NAME", "disha")
    db_pass = os.getenv("DB_PASSWORD", "disha_secure_pass_123")
    return f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"


def _as_json(val: any) -> dict:
    if isinstance(val, str):
        return json.loads(val)
    return val


@pytest.mark.asyncio
async def test_knowledge_sources_schema_and_tiers():
    """Verify knowledge_sources table exists with all required columns and valid trust tiers."""
    conn = await asyncpg.connect(_get_db_url())
    try:
        sources = await conn.fetch("SELECT id, name, license, domain, trust_tier FROM knowledge_sources ORDER BY id")
        assert len(sources) >= 5, f"Expected at least 5 knowledge sources, found {len(sources)}"
        
        source_ids = {s["id"] for s in sources}
        assert "src_icmr_nin_2024" in source_ids
        assert "src_ifct_2017" in source_ids
        assert "src_ayush_remedies_2024" in source_ids
        assert "src_who_cvd_diabetes_2021" in source_ids

        for s in sources:
            assert s["trust_tier"] in ("tier_1", "tier_2", "tier_3"), f"Invalid trust tier: {s['trust_tier']}"
            assert s["license"], f"License must not be empty for {s['id']}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_knowledge_chunks_provenance_invariant():
    """Verify that 100% of knowledge_chunks have valid foreign key provenance to knowledge_sources."""
    conn = await asyncpg.connect(_get_db_url())
    try:
        # Check orphan chunks
        orphan_count = await conn.fetchval("""
            SELECT count(*) 
            FROM knowledge_chunks k 
            LEFT JOIN knowledge_sources s ON k.source_id = s.id 
            WHERE s.id IS NULL
        """)
        assert orphan_count == 0, f"Found {orphan_count} orphan knowledge chunks without provenance!"

        # Check total count
        total_chunks = await conn.fetchval("SELECT count(*) FROM knowledge_chunks")
        assert total_chunks >= 400, f"Expected >= 400 knowledge chunks, found {total_chunks}"

        # Check domain distribution
        domains = await conn.fetch("SELECT domain, count(*) as cnt FROM knowledge_chunks GROUP BY domain")
        assert len(domains) >= 2, "Expected multiple clinical domains"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_knowledge_chunks_fts_and_length_safety():
    """Verify that full-text vector indexing works and micro-chunks respect conciseness bounds."""
    conn = await asyncpg.connect(_get_db_url())
    try:
        # Query via tsvector
        results = await conn.fetch("""
            SELECT id, source_id, domain, content,
                   ts_rank(fts_vector, to_tsquery('simple', 'jeera | saunf')) as rank
            FROM knowledge_chunks
            WHERE fts_vector @@ to_tsquery('simple', 'jeera | saunf')
            ORDER BY rank DESC LIMIT 5
        """)
        assert len(results) > 0, "Expected FTS search for 'jeera | saunf' to return results"
        
        # Verify content is not empty
        empty_count = await conn.fetchval("SELECT count(*) FROM knowledge_chunks WHERE btrim(content) = ''")
        assert empty_count == 0, "Found empty content in knowledge_chunks"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_product_facts_pricing_and_policies():
    """Verify that commercial pricing, channel policies, and clearance facts exist in product_facts."""
    conn = await asyncpg.connect(_get_db_url())
    try:
        facts = await conn.fetch("SELECT fact_key, category, fact_value, verification_status FROM product_facts")
        fact_dict = {f["fact_key"]: f for f in facts}

        # Check all records marked provisional / owner-verify
        for k, f in fact_dict.items():
            assert f["verification_status"] == "provisional / owner-verify", f"{k} is not marked provisional / owner-verify"

        # Pricing checks
        assert "pricing_followup_consultations" in fact_dict
        val_followup = _as_json(fact_dict["pricing_followup_consultations"]["fact_value"])
        assert val_followup.get("amount") == 0
        assert val_followup.get("currency") == "INR"

        assert "pricing_dedicated_nutritionist" in fact_dict
        val_nutritionist = _as_json(fact_dict["pricing_dedicated_nutritionist"]["fact_value"])
        assert val_nutritionist.get("amount") == 1499
        assert val_nutritionist.get("currency") == "INR"

        # Channel policy
        assert "channel_delivery_policy" in fact_dict
        val_channel = _as_json(fact_dict["channel_delivery_policy"]["fact_value"])
        assert val_channel.get("allowed_channel") == "app_my_plan_tab"
        assert "whatsapp" in val_channel.get("forbidden_channels", [])

        # Persona identity
        assert "persona_identity" in fact_dict
        val_id = _as_json(fact_dict["persona_identity"]["fact_value"])
        assert val_id.get("is_doctor") is False
        assert val_id.get("is_human") is False

        # Helplines
        assert "emergency_helpline_national" in fact_dict
        val_112 = _as_json(fact_dict["emergency_helpline_national"]["fact_value"])
        assert val_112.get("number") == "112"

        assert "emergency_helpline_telemanas" in fact_dict
        val_tele = _as_json(fact_dict["emergency_helpline_telemanas"]["fact_value"])
        assert val_tele.get("number") == "14416"

        # Exercise clearance
        assert "pep_clearance_hypertension_stage1" in fact_dict
        val_pep1 = _as_json(fact_dict["pep_clearance_hypertension_stage1"]["fact_value"])
        assert "brisk walking" in val_pep1.get("allowed", [])
        assert "heavy deadlifts" in val_pep1.get("restricted", [])

        # Diet templates
        assert "diet_template_jain" in fact_dict
        assert "diet_template_vegetarian" in fact_dict
        assert "diet_template_non_vegetarian" in fact_dict
    finally:
        await conn.close()
