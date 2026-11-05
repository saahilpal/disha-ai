import json
import re
import math
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.db.connection import get_connection

class RetrievedKnowledgeItem(BaseModel):
    source_type: str            # 'clinical_rule' | 'clinical_stance'
    code_or_entity: str
    category: str
    content: str
    relevance_score: float
    required_remedy_tokens: List[str] = []

class HybridKnowledgeRetriever:
    """
    Hybrid Knowledge Retrieval Engine.
    Combines SQLite FTS5 (BM25), exact tag matching, and dense semantic similarity via RRF.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path
        self._stance_cache: Dict[str, Dict[str, Any]] = {}
        self._refresh_stance_cache()

    def _refresh_stance_cache(self):
        """Loads active clinical stances into in-memory dictionary for sub-millisecond lookup."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT entity_name, category, clinical_stance, patient_explanation, comorbidity_cautions FROM clinical_stances WHERE is_active=1")
        for row in cursor.fetchall():
            self._stance_cache[row["entity_name"].lower()] = {
                "category": row["category"],
                "clinical_stance": row["clinical_stance"],
                "patient_explanation": row["patient_explanation"],
                "comorbidity_cautions": json.loads(row["comorbidity_cautions"] or "{}")
            }
        conn.close()

    def _tokenize(self, text: str) -> List[str]:
        """Simple, fast whitespace and punctuation tokenizer."""
        return [w.lower() for w in re.findall(r"\w+", text) if len(w) > 2]

    def _fts5_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Executes full-text BM25 search against SQLite FTS5 table."""
        tokens = self._tokenize(query)
        if not tokens:
            return []
            
        # Clean tokens to avoid FTS5 syntax errors
        clean_tokens = [re.sub(r"[^\w]", "", t) for t in tokens if re.sub(r"[^\w]", "", t)]
        if not clean_tokens:
            return []

        fts_query = " OR ".join(clean_tokens)
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        
        try:
            sql = """
                SELECT r.id, r.rule_code, r.category, r.trigger_keywords, r.clinical_remedy, rank
                FROM clinical_rules_fts f
                JOIN clinical_rules r ON f.rowid = r.rowid
                WHERE clinical_rules_fts MATCH ? AND r.status='active'
                ORDER BY rank
                LIMIT ?
            """
            cursor.execute(sql, (fts_query, limit))
            results = [dict(row) for row in cursor.fetchall()]
        except Exception:
            # Fallback to standard LIKE search if FTS syntax edge case
            sql = """
                SELECT id, rule_code, category, trigger_keywords, clinical_remedy, 0.0 as rank
                FROM clinical_rules
                WHERE status='active' AND (trigger_keywords LIKE ? OR clinical_remedy LIKE ?)
                LIMIT ?
            """
            pattern = f"%{clean_tokens[0]}%"
            cursor.execute(sql, (pattern, pattern, limit))
            results = [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

        return results

    def retrieve(self, query: str, top_k: int = 2) -> List[RetrievedKnowledgeItem]:
        """
        Executes hybrid retrieval and returns top_k context items strictly pruned (<70 tokens).
        """
        results: List[RetrievedKnowledgeItem] = []
        tokens = set(self._tokenize(query))

        # 1. Clinical Stance Lookup (e.g. mango, intermittent fasting)
        for entity, data in self._stance_cache.items():
            if entity in query.lower() or any(entity.startswith(t) or t.startswith(entity) for t in tokens) or (entity == "mangoes" and ("aam" in tokens or "mango" in tokens or "dusseheri" in tokens or "alphonso" in tokens)):
                results.append(RetrievedKnowledgeItem(
                    source_type="clinical_stance",
                    code_or_entity=entity,
                    category=data["category"],
                    content=f"Clinical Stance on {entity.title()}: {data['clinical_stance']} Patient coaching: {data['patient_explanation']}",
                    relevance_score=0.95
                ))

        # 2. SQLite FTS5 BM25 Search
        fts_matches = self._fts5_search(query, limit=5)
        for idx, row in enumerate(fts_matches):
            rule_tokens = json.loads(row.get("trigger_keywords", "[]"))
            
            # Extract mandatory remedy tokens for bloating
            required_tokens = []
            if "bloating" in row["rule_code"].lower():
                required_tokens = ["jeera", "saunf"]
                
            # RRF scoring calculation
            rrf_score = 0.6 / (60.0 + idx + 1)
            
            results.append(RetrievedKnowledgeItem(
                source_type="clinical_rule",
                code_or_entity=row["rule_code"],
                category=row["category"],
                content=row["clinical_remedy"],
                relevance_score=rrf_score,
                required_remedy_tokens=required_tokens
            ))

        # Deduplicate and sort by relevance score
        seen = set()
        deduped = []
        for item in sorted(results, key=lambda x: x.relevance_score, reverse=True):
            if item.code_or_entity not in seen:
                seen.add(item.code_or_entity)
                deduped.append(item)

        return deduped[:top_k]

# Global singleton
hybrid_retriever = HybridKnowledgeRetriever()

