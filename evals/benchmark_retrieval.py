"""
Retrieval Benchmark: Lexical (FTS5 BM25) vs Dense Semantic (Hash/Trigram) vs Hybrid RRF.
Evaluates on 15 realistic clinical and Hinglish queries against ground truth targets.
Measures latency, recall@1, recall@3, MRR (Mean Reciprocal Rank), and false positive suppression.
"""
import time
import json
from typing import Dict, List, Any, Optional
from app.db import get_connection
from app.rag.retriever import HybridRetriever, RetrievedChunk
from app.rag.embeddings import SemanticVectorizer

BENCHMARK_QUERIES = [
    {
        "query": "Periods me bloating ho rahi hai pet phoola hua lagta hai",
        "expected_chunk_id": "chk_bloat_01",
        "category": "clinical_remedy",
        "patient_id": None,
        "type": "hinglish_symptom"
    },
    {
        "query": "Aam kha sakte hain kya diet pe?",
        "expected_chunk_id": "chk_mango_01",
        "category": "nutrition_guidance",
        "patient_id": None,
        "type": "hinglish_diet"
    },
    {
        "query": "Can I eat mangoes if I am trying to lose weight?",
        "expected_chunk_id": "chk_mango_01",
        "category": "nutrition_guidance",
        "patient_id": None,
        "type": "english_diet"
    },
    {
        "query": "Kya gym me weight lifting kar sakte hain bp patient?",
        "expected_chunk_id": "chk_pep_01",
        "category": "pep_reference",
        "patient_id": None,
        "type": "hinglish_exercise"
    },
    {
        "query": "Pet me gas aur aafra feel ho raha hai",
        "expected_chunk_id": "chk_bloat_01",
        "category": "clinical_remedy",
        "patient_id": None,
        "type": "colloquial_hinglish"
    },
    {
        "query": "Kabz ki problem hai digestion thik nahi hai",
        "expected_chunk_id": "chk_bloat_02",
        "category": "clinical_remedy",
        "patient_id": None,
        "type": "colloquial_hinglish"
    },
    {
        "query": "How much water should I drink for constipation?",
        "expected_chunk_id": "chk_bloat_02",
        "category": "clinical_remedy",
        "patient_id": None,
        "type": "english_clinical"
    },
    {
        "query": "Workout clearance under PEP for hypertension",
        "expected_chunk_id": "chk_pep_01",
        "category": "pep_reference",
        "patient_id": None,
        "type": "english_technical"
    },
    {
        "query": "Jeera saunf water dosage for period bloating",
        "expected_chunk_id": "chk_bloat_01",
        "category": "clinical_remedy",
        "patient_id": None,
        "type": "hybrid_remedy"
    },
    {
        "query": "Aam ki taseer garam hoti hai kya aam khao ya na khao",
        "expected_chunk_id": "chk_mango_01",
        "category": "nutrition_guidance",
        "patient_id": None,
        "type": "hinglish_myth"
    },
    # Negative / Out-of-domain queries (expected: None retrieved)
    {
        "query": "What is the weather in Delhi today?",
        "expected_chunk_id": None,
        "category": None,
        "patient_id": None,
        "type": "out_of_domain"
    },
    {
        "query": "Tell me a bedtime story about elephants",
        "expected_chunk_id": None,
        "category": None,
        "patient_id": None,
        "type": "out_of_domain"
    },
    {
        "query": "Raw juice cleanse fasting plan batao",
        "expected_chunk_id": None, # Unapproved draft must NOT be retrieved
        "category": None,
        "patient_id": None,
        "type": "unapproved_attempt"
    },
    # Multi-tenant isolation test: anonymous query should NOT retrieve Ramesh's private record
    {
        "query": "Ramesh doctor advice blood pressure readings",
        "expected_chunk_id": None, # If patient_id is None, private pt_101 doc must NOT leak
        "category": None,
        "patient_id": None,
        "type": "multi_tenant_leak_test"
    },
    # Multi-tenant authorized retrieval: pt_101 SHOULD retrieve Ramesh's doc
    {
        "query": "Doctor consultation advice for my blood pressure",
        "expected_chunk_id": "chk_ramesh_01",
        "category": None,
        "patient_id": "pt_101",
        "type": "authorized_private"
    }
]


def run_pure_lexical(query: str, patient_id: Optional[str] = None, top_k: int = 3) -> List[str]:
    """Pure SQLite FTS5 BM25 search."""
    import re
    clean = re.sub(r"[^\w\s]", " ", query).strip()
    words = [w for w in clean.split() if len(w) > 2]
    if not words:
        return []
    fts_query = " OR ".join(words)
    
    conn = get_connection()
    sql = """
        SELECT c.id as chunk_id, bm25(document_chunks_fts) as rank_score
        FROM document_chunks_fts f
        JOIN document_chunks c ON f.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE d.approval_status = 'approved'
          AND (d.patient_id IS NULL OR d.patient_id = ?)
          AND document_chunks_fts MATCH ?
        ORDER BY rank_score ASC
        LIMIT ?
    """
    rows = conn.execute(sql, (patient_id or "", fts_query, top_k)).fetchall()
    conn.close()
    return [r["chunk_id"] for r in rows]


def run_pure_semantic(query: str, patient_id: Optional[str] = None, top_k: int = 3, threshold: float = 0.15) -> List[str]:
    """Pure Dense Semantic Cosine Similarity search with minimum threshold."""
    conn = get_connection()
    sql = """
        SELECT c.id as chunk_id, c.embedding_json
        FROM document_chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.approval_status = 'approved'
          AND (d.patient_id IS NULL OR d.patient_id = ?)
    """
    rows = conn.execute(sql, (patient_id or "",)).fetchall()
    conn.close()
    
    query_vec = SemanticVectorizer.encode(query)
    scores = []
    for r in rows:
        emb_str = r["embedding_json"]
        if emb_str:
            vec = json.loads(emb_str)
            score = SemanticVectorizer.cosine_similarity(query_vec, vec)
            if score >= threshold:
                scores.append((r["chunk_id"], score))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    return [cid for cid, s in scores[:top_k]]


def run_hybrid_rrf(query: str, patient_id: Optional[str] = None, top_k: int = 3) -> List[str]:
    """Current HybridRetriever using BM25 + Semantic + RRF."""
    retriever = HybridRetriever()
    chunks, _ = retriever.retrieve(query, patient_id=patient_id, top_k=top_k)
    return [c.chunk_id for c in chunks]


def evaluate_mode(mode_name: str, search_fn) -> Dict[str, Any]:
    latencies = []
    mrr_total = 0.0
    recall_at_1 = 0
    recall_at_3 = 0
    false_positives = 0
    total_relevant_queries = 0
    total_negative_queries = 0
    
    details = []

    for item in BENCHMARK_QUERIES:
        q = item["query"]
        expected = item["expected_chunk_id"]
        pid = item["patient_id"]
        
        t0 = time.perf_counter()
        retrieved_ids = search_fn(q, patient_id=pid, top_k=3)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)
        
        is_hit_1 = False
        is_hit_3 = False
        reciprocal_rank = 0.0
        
        if expected is not None:
            total_relevant_queries += 1
            if retrieved_ids and retrieved_ids[0] == expected:
                is_hit_1 = True
                recall_at_1 += 1
            if expected in retrieved_ids:
                is_hit_3 = True
                recall_at_3 += 1
                rank = retrieved_ids.index(expected) + 1
                reciprocal_rank = 1.0 / rank
            mrr_total += reciprocal_rank
        else:
            total_negative_queries += 1
            if retrieved_ids:
                false_positives += 1

        details.append({
            "query": q,
            "type": item["type"],
            "expected": expected,
            "retrieved": retrieved_ids,
            "latency_ms": round(elapsed_ms, 3),
            "hit_at_1": is_hit_1,
            "hit_at_3": is_hit_3
        })

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    r1 = recall_at_1 / total_relevant_queries if total_relevant_queries else 0.0
    r3 = recall_at_3 / total_relevant_queries if total_relevant_queries else 0.0
    mrr = mrr_total / total_relevant_queries if total_relevant_queries else 0.0
    fp_rate = false_positives / total_negative_queries if total_negative_queries else 0.0

    return {
        "mode": mode_name,
        "avg_latency_ms": round(avg_latency, 3),
        "min_latency_ms": round(min(latencies), 3),
        "max_latency_ms": round(max(latencies), 3),
        "recall_at_1": round(r1 * 100, 1),
        "recall_at_3": round(r3 * 100, 1),
        "mrr": round(mrr, 3),
        "false_positive_rate": round(fp_rate * 100, 1),
        "false_positive_count": false_positives,
        "details": details
    }


def main():
    print("=" * 65)
    print("      DISHA AI: RETRIEVAL SYSTEM BENCHMARK SUITE")
    print("=" * 65)
    
    lexical_res = evaluate_mode("Pure Lexical (FTS5 BM25)", run_pure_lexical)
    semantic_res = evaluate_mode("Pure Dense Semantic (Hash/Trigram)", run_pure_semantic)
    hybrid_res = evaluate_mode("Hybrid RRF (FTS5 + Semantic + RRF k=60)", run_hybrid_rrf)
    
    print(f"\n{'Metric':<30} | {'Lexical (BM25)':<15} | {'Semantic (Hash)':<15} | {'Hybrid (RRF)':<15}")
    print("-" * 82)
    print(f"{'Recall @ 1 (%)':<30} | {lexical_res['recall_at_1']:<15} | {semantic_res['recall_at_1']:<15} | {hybrid_res['recall_at_1']:<15}")
    print(f"{'Recall @ 3 (%)':<30} | {lexical_res['recall_at_3']:<15} | {semantic_res['recall_at_3']:<15} | {hybrid_res['recall_at_3']:<15}")
    print(f"{'MRR (Mean Reciprocal Rank)':<30} | {lexical_res['mrr']:<15} | {semantic_res['mrr']:<15} | {hybrid_res['mrr']:<15}")
    print(f"{'False Positives (OOD/Draft)':<30} | {lexical_res['false_positive_count']}/4 ({lexical_res['false_positive_rate']}%) | {semantic_res['false_positive_count']}/4 ({semantic_res['false_positive_rate']}%) | {hybrid_res['false_positive_count']}/4 ({hybrid_res['false_positive_rate']}%)")
    print(f"{'Average Latency (ms)':<30} | {lexical_res['avg_latency_ms']:<15} | {semantic_res['avg_latency_ms']:<15} | {hybrid_res['avg_latency_ms']:<15}")
    print(f"{'Max Latency (ms)':<30} | {lexical_res['max_latency_ms']:<15} | {semantic_res['max_latency_ms']:<15} | {hybrid_res['max_latency_ms']:<15}")
    print("=" * 82)

    # Output detailed query-level breakdown
    print("\nQuery-Level Performance Analysis:")
    for i, item in enumerate(BENCHMARK_QUERIES):
        q = item["query"]
        exp = item["expected_chunk_id"] or "NONE (Negative/OOD)"
        lex_ret = lexical_res["details"][i]["retrieved"]
        sem_ret = semantic_res["details"][i]["retrieved"]
        hyb_ret = hybrid_res["details"][i]["retrieved"]
        print(f"\n[{i+1}] \"{q}\"")
        print(f"    Expected: {exp}")
        print(f"    Lexical:  {lex_ret}")
        print(f"    Semantic: {sem_ret}")
        print(f"    Hybrid:   {hyb_ret}")

    with open("evals/results/retrieval_benchmark.json", "w") as f:
        json.dump({
            "lexical": lexical_res,
            "semantic": semantic_res,
            "hybrid": hybrid_res
        }, f, indent=2)
    print("\nBenchmark results saved to evals/results/retrieval_benchmark.json")

if __name__ == "__main__":
    main()

