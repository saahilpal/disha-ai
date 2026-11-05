import json
import re
from typing import Any, Dict, List, Optional, Tuple
from app.db import get_connection
from app.rag.embeddings import SemanticVectorizer

class RetrievedChunk:
    def __init__(
        self,
        chunk_id: str,
        document_id: str,
        document_title: str,
        version: int,
        heading: str,
        content: str,
        category: str,
        patient_id: Optional[str] = None,
        bm25_rank: Optional[int] = None,
        semantic_score: float = 0.0,
        rrf_score: float = 0.0
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.document_title = document_title
        self.version = version
        self.heading = heading
        self.content = content
        self.category = category
        self.patient_id = patient_id
        self.bm25_rank = bm25_rank
        self.semantic_score = semantic_score
        self.rrf_score = rrf_score

    @property
    def citation(self) -> str:
        return f"[{self.document_title} v{self.version} — Section: {self.heading}]"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "version": self.version,
            "heading": self.heading,
            "content": self.content,
            "category": self.category,
            "patient_id": self.patient_id,
            "citation": self.citation,
            "bm25_rank": self.bm25_rank,
            "semantic_score": round(self.semantic_score, 4),
            "rrf_score": round(self.rrf_score, 5)
        }


COMMON_STOPWORDS = {
    "about", "tell", "what", "where", "when", "which", "with", "from", "that", "this",
    "have", "more", "some", "like", "will", "your", "mine", "them", "then", "there",
    "kya", "hai", "hain", "mein", "batao", "karo", "mera", "meri", "thoda", "kuch"
}

class HybridRetriever:
    """
    Two-Tier Hybrid RAG Retriever combining:
    1. SQLite FTS5 (BM25 keyword search)
    2. Dense Semantic Vector Cosine Similarity
    3. Reciprocal Rank Fusion (RRF) Reranker
    4. Strict Multi-Tenant Isolation & Approval Status Filters
    5. Contradiction / Conflict Detection
    """

    def __init__(self, db_path: Optional[str] = None, rrf_k: int = 60):
        self.db_path = db_path
        self.rrf_k = rrf_k

    def _sanitize_fts_query(self, query: str) -> str:
        """Strips special SQLite FTS5 syntax, removes stopwords, and builds clean search string."""
        clean = re.sub(r"[^\w\s]", " ", query).strip()
        words = [w for w in clean.split() if len(w) > 2 and w.lower() not in COMMON_STOPWORDS]
        if not words:
            # Fall back to content words > 2 chars if all words were stopwords
            words = [w for w in clean.split() if len(w) > 2]
        if not words:
            return ""
        # Join with OR for broad lexical recall
        return " OR ".join(words)

    def retrieve(
        self,
        query: str,
        patient_id: Optional[str] = None,
        category: Optional[str] = None,
        top_k: int = 3,
        min_relevance_threshold: float = 0.15,
    ) -> Tuple[List[RetrievedChunk], Optional[str]]:
        """
        Executes hybrid retrieval over approved documents.
        Returns: (ranked_chunks, conflict_warning_if_any)
        """
        if not query or not query.strip():
            return [], None

        conn = get_connection(self.db_path)
        
        # 1. Fetch all active approved candidate chunks matching tenant boundary
        # Strict isolation: patient_id matches current patient OR is NULL (global clinical knowledge)
        tenant_sql = """
            SELECT 
                c.id as chunk_id,
                c.document_id,
                d.title as document_title,
                d.version,
                c.heading,
                c.content,
                d.category,
                d.patient_id,
                c.embedding_json
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE d.approval_status = 'approved'
              AND (d.patient_id IS NULL OR d.patient_id = ?)
        """
        params: List[Any] = [patient_id or ""]
        if category:
            tenant_sql += " AND d.category = ?"
            params.append(category)

        all_candidates = conn.execute(tenant_sql, params).fetchall()
        if not all_candidates:
            conn.close()
            return [], None

        candidates_by_id = {row["chunk_id"]: dict(row) for row in all_candidates}

        # 2. Keyword Search (BM25 via FTS5)
        fts_query = self._sanitize_fts_query(query)
        bm25_ranks: Dict[str, int] = {}
        
        if fts_query:
            try:
                fts_sql = f"""
                    SELECT chunk_id, bm25(document_chunks_fts) as rank_score
                    FROM document_chunks_fts
                    WHERE document_chunks_fts MATCH ?
                    ORDER BY rank_score ASC
                    LIMIT 20
                """
                fts_rows = conn.execute(fts_sql, (fts_query,)).fetchall()
                rank = 1
                for r in fts_rows:
                    cid = r["chunk_id"]
                    if cid in candidates_by_id:
                        bm25_ranks[cid] = rank
                        rank += 1
            except Exception:
                pass

        conn.close()

        # 3. Dense Semantic Vector Search (Cosine Similarity)
        query_vec = SemanticVectorizer.encode(query)
        semantic_scores: Dict[str, float] = {}
        for cid, row in candidates_by_id.items():
            emb_str = row.get("embedding_json")
            if emb_str:
                chunk_vec = json.loads(emb_str)
                score = SemanticVectorizer.cosine_similarity(query_vec, chunk_vec)
                semantic_scores[cid] = score
            else:
                semantic_scores[cid] = 0.0

        # Sort semantic candidates by score descending
        sorted_semantic = sorted(semantic_scores.items(), key=lambda x: x[1], reverse=True)
        semantic_ranks = {cid: rank + 1 for rank, (cid, score) in enumerate(sorted_semantic)}

        # 4. Reciprocal Rank Fusion (RRF) Reranking
        scored_chunks: List[RetrievedChunk] = []
        for cid, row in candidates_by_id.items():
            r_bm25 = bm25_ranks.get(cid, 999)
            r_sem = semantic_ranks.get(cid, 999)
            
            # Reciprocal Rank Fusion formula
            rrf = (1.0 / (self.rrf_k + r_bm25)) + (1.0 / (self.rrf_k + r_sem))
            sem_score = semantic_scores.get(cid, 0.0)

            # Filter out chunks that have neither lexical match nor sufficient semantic relevance,
            # and discard negative/near-zero semantic relevance matches (< 0.05)
            if r_bm25 > 20 and sem_score < min_relevance_threshold:
                continue
            if sem_score < 0.05 and r_bm25 > 3:
                continue

            scored_chunks.append(RetrievedChunk(
                chunk_id=cid,
                document_id=row["document_id"],
                document_title=row["document_title"],
                version=row["version"],
                heading=row["heading"],
                content=row["content"],
                category=row["category"],
                patient_id=row["patient_id"],
                bm25_rank=bm25_ranks.get(cid),
                semantic_score=sem_score,
                rrf_score=rrf
            ))

        # Sort by RRF score descending
        scored_chunks.sort(key=lambda c: c.rrf_score, reverse=True)
        top_chunks = scored_chunks[:top_k]

        # 5. Clinical Stance Contradiction / Conflict Detection
        conflict_warning = self._check_conflicts(top_chunks)

        return top_chunks, conflict_warning

    def _check_conflicts(self, chunks: List[RetrievedChunk]) -> Optional[str]:
        """Detects if two retrieved approved documents contain opposing clinical recommendations on the same topic."""
        if len(chunks) < 2:
            return None

        # Check for conflicts anchored to specific clinical topics
        topic_entities = ["mango", "aam", "fruit", "fasting", "salt", "sugar", "diet", "meal", "exercise", "walk"]
        for topic in topic_entities:
            topic_chunks = [c.content.lower() for c in chunks if topic in c.content.lower() or topic in c.heading.lower()]
            if len(topic_chunks) >= 2:
                has_strictly_avoid = any("strictly avoid" in t or "bilkul na lein" in t or "prohibited" in t for t in topic_chunks)
                has_permitted = any("permitted" in t or "moderation mein" in t or "allowed" in t or "safe" in t for t in topic_chunks)
                if has_strictly_avoid and has_permitted:
                    return (
                        f"CLINICAL_CONFLICT_DETECTED: Two approved documents provide differing guidance on {topic} "
                        "(one suggests strict avoidance while another permits moderation). "
                        "Consulting the supervising doctor is advised."
                    )

        # Global check only if general guidance directly conflicts
        combined_texts = [c.content.lower() for c in chunks]
        has_strictly_avoid = any("strictly avoid" in t for t in combined_texts)
        has_permitted = any("permitted in seasonal moderation" in t for t in combined_texts)
        if has_strictly_avoid and has_permitted:
            return (
                "CLINICAL_CONFLICT_DETECTED: Differing clinical guidance detected. "
                "Consulting the supervising doctor is advised."
            )
        return None

hybrid_retriever = HybridRetriever()

