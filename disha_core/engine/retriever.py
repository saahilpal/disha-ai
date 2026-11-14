from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from typing import Any, Protocol, Sequence

from .normalizer import normalize

STOP_WORDS = frozenset(
    {
        "hai",
        "hain",
        "me",
        "mein",
        "aur",
        "ka",
        "ki",
        "ke",
        "ko",
        "se",
        "par",
        "kya",
        "kyun",
        "the",
        "a",
        "an",
        "is",
        "in",
        "to",
        "for",
        "with",
        "and",
        "or",
        "mera",
        "meri",
        "mere",
        "mujhe",
        "bhi",
        "ho",
        "raha",
        "rahi",
        "rahe",
        "kuch",
        "bahut",
        "bohot",
        "thoda",
        "thodi",
        "please",
        "batao",
        "bataiye",
        "how",
        "what",
        "can",
        "which",
        "best",
        "should",
        "would",
        "tell",
        "kaise",
        "karna",
        "karo",
        "fix",
        "write",
        "give",
        "who",
        "when",
        "where",
        "why",
        "from",
        "that",
        "this",
        "they",
        "them",
        "some",
        "any",
        "about",
        "your",
        "have",
        "has",
        "had",
        "will",
        "does",
        "make",
        "need",
        "want",
        "good",
    }
)


def _build_or_tsquery(text: str) -> str:
    """Extract significant keywords and build a disjunctive full-text tsquery expression."""
    tokens = [re.sub(r"[^\w]", "", w) for w in text.split()]
    clean_tokens = [w for w in tokens if len(w) > 2 and w not in STOP_WORDS]
    return " | ".join(clean_tokens) if clean_tokens else ""


class PgConnection(Protocol):
    async def fetch(self, query: str, *args: Any) -> Sequence[Any]: ...
    async def fetchval(self, query: str, *args: Any) -> Any: ...
    def transaction(self) -> Any: ...


RETRIEVE_SQL = """
SELECT chunk_id, condition_tag, context_header, guideline_content, source_citation,
       required_remedy_tokens,
       GREATEST(similarity(trigger_terms, $1), similarity(guideline_content, $1)) AS trigram_score,
       GREATEST(
           ts_rank(tsv_content, plainto_tsquery('simple', $1)),
           CASE WHEN $4 <> '' THEN ts_rank(tsv_content, to_tsquery('simple', $4)) ELSE 0.0 END
       ) AS text_score
FROM clinical_guideline_chunks
WHERE approval_status = 'approved'
  AND (
       -- Exact condition-tag metadata hit; lexical branches below preserve recall.
       condition_tag = ANY($3)
       OR trigger_terms % $1
       OR tsv_content @@ plainto_tsquery('simple', $1)
       OR ($4 <> '' AND tsv_content @@ to_tsquery('simple', $4))
  )
ORDER BY 
    CASE WHEN condition_tag = ANY($3) THEN 1.0 ELSE 0.0 END DESC,
    GREATEST(similarity(trigger_terms, $1),
             ts_rank(tsv_content, plainto_tsquery('simple', $1)),
             CASE WHEN $4 <> '' THEN ts_rank(tsv_content, to_tsquery('simple', $4)) ELSE 0.0 END) DESC
LIMIT $2::bigint
"""

# Multi-tenant cache partitioned by compound key (patient_id, query_hash) for C11 isolation
_RETRIEVAL_CACHE: OrderedDict[tuple[str, str], Sequence[Any]] = OrderedDict()
_CACHE_MAX_SIZE = 1024


def compute_query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def clear_retrieval_cache() -> None:
    _RETRIEVAL_CACHE.clear()


async def retrieve_chunks(
    connection: PgConnection,
    query: str,
    *,
    patient_id: str = "shared",
    threshold: float = 0.18,
    limit: int = 5,
    use_cache: bool = False,
    tags: Sequence[str] | None = None,
) -> Sequence[Any]:
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    norm = normalize(query)
    query_norm = norm.normalized
    if not query_norm:
        return ()
    if not 0.0 <= threshold <= 1.0 or not 1 <= limit <= 50:
        raise ValueError("threshold must be in [0, 1] and limit in [1, 50]")

    tag_list = list(tags) if tags is not None else list(norm.tags)
    tsquery_or = _build_or_tsquery(query_norm)

    query_hash = compute_query_hash(f"{query_norm}:{tsquery_or}:{','.join(sorted(tag_list))}")
    cache_key = (patient_id, query_hash)
    if use_cache and cache_key in _RETRIEVAL_CACHE:
        _RETRIEVAL_CACHE.move_to_end(cache_key)
        return _RETRIEVAL_CACHE[cache_key]

    # The trigram GIN operator reads this threshold; keep it local to this query.
    async with connection.transaction():
        await connection.fetchval("SELECT set_config('pg_trgm.similarity_threshold', $1, true)", str(threshold))
        raw_results = await connection.fetch(RETRIEVE_SQL, query_norm, limit * 2, tag_list, tsquery_or)

    # Post-retrieval deduplication and strict quality thresholding
    deduped: list[Any] = []
    seen_ids: set[Any] = set()
    seen_contents: set[tuple[str, str]] = set()

    for item in raw_results:
        getter = item.get if hasattr(item, "get") else lambda k, default=None: getattr(item, k, default)
        cid = getter("chunk_id", None)
        tag = getter("condition_tag", "")
        content = str(getter("guideline_content", "")).strip()
        trigram_sc = float(getter("trigram_score", 0.0) or 0.0)
        text_sc = float(getter("text_score", 0.0) or 0.0)

        # Deduplication
        dedup_tuple = (tag, content)
        if cid is not None and cid in seen_ids:
            continue
        if dedup_tuple in seen_contents:
            continue

        # Quality thresholding: direct tag match, or sufficient trigram / full-text score
        is_tag_match = bool(tag_list and tag in tag_list)
        is_relevant = is_tag_match or (trigram_sc >= threshold) or (text_sc >= 0.06)

        if is_relevant:
            if cid is not None:
                seen_ids.add(cid)
            seen_contents.add(dedup_tuple)
            deduped.append(item)
            if len(deduped) >= limit:
                break

    results = tuple(deduped)

    if use_cache:
        if len(_RETRIEVAL_CACHE) >= _CACHE_MAX_SIZE:
            _RETRIEVAL_CACHE.popitem(last=False)
        _RETRIEVAL_CACHE[cache_key] = results

    return results


CONVERSATION_HISTORY_RETRIEVE_SQL = """
SELECT speaker, raw_utterance, timestamp_utc, turn_index
FROM patient_turn_journal
WHERE patient_id = $1
  AND LENGTH(raw_utterance) > 6
  AND raw_utterance ILIKE ANY($2)
ORDER BY timestamp_utc DESC
LIMIT $3
"""


async def retrieve_conversation_history(
    connection: Any,
    patient_id: str,
    query: str,
    exclude_texts: set[str] | None = None,
    limit: int = 4,
) -> list[dict[str, str]]:
    """Retrieve older relevant conversation turns from patient_turn_journal via keyword matching.

    Supplements recent message history without duplicating active turns or returning trivial noise.
    """
    if connection is None or not query:
        return []

    tokens = [re.sub(r"[^\w]", "", w).casefold() for w in query.split()]
    clean_tokens = [w for w in tokens if len(w) > 3 and w not in STOP_WORDS]
    if not clean_tokens:
        return []

    patterns = [f"%{tok}%" for tok in clean_tokens[:6]]
    try:
        rows = await connection.fetch(CONVERSATION_HISTORY_RETRIEVE_SQL, patient_id, patterns, limit * 3)
    except Exception:
        return []

    results: list[dict[str, str]] = []
    seen = {t.strip().casefold() for t in (exclude_texts or ())}
    for r in rows:
        utterance = str(r["raw_utterance"]).strip()
        casefolded = utterance.casefold()
        if casefolded in seen or any(casefolded in s for s in seen):
            continue
        seen.add(casefolded)
        speaker = str(r["speaker"]).lower()
        role = "assistant" if speaker in ("assistant", "coach") else "user"
        results.append({"role": role, "content": utterance})
        if len(results) >= limit:
            break

    # Return in chronological order
    results.reverse()
    return results
