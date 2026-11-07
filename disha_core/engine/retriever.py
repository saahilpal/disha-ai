from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any, Protocol, Sequence

from .normalizer import normalize


class PgConnection(Protocol):
    async def fetch(self, query: str, *args: Any) -> Sequence[Any]: ...
    async def fetchval(self, query: str, *args: Any) -> Any: ...
    def transaction(self) -> Any: ...


RETRIEVE_SQL = """
SELECT chunk_id, condition_tag, context_header, guideline_content, source_citation,
       required_remedy_tokens,
       similarity(trigger_terms, $1) AS trigram_score,
       ts_rank(tsv_content, plainto_tsquery('simple', $1)) AS text_score
FROM clinical_knowledge_base
WHERE approval_status = 'approved'
  AND (
       condition_tag = ANY($3)
       OR trigger_terms % $1
       OR tsv_content @@ plainto_tsquery('simple', $1)
  )
ORDER BY 
    CASE WHEN condition_tag = ANY($3) THEN 1.0 ELSE 0.0 END DESC,
    GREATEST(similarity(trigger_terms, $1),
             ts_rank(tsv_content, plainto_tsquery('simple', $1))) DESC
LIMIT $2
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
    use_cache: bool = True,
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

    query_hash = compute_query_hash(f"{query_norm}:{','.join(sorted(tag_list))}")
    cache_key = (patient_id, query_hash)
    if use_cache and cache_key in _RETRIEVAL_CACHE:
        _RETRIEVAL_CACHE.move_to_end(cache_key)
        return _RETRIEVAL_CACHE[cache_key]

    # The trigram GIN operator reads this threshold; keep it local to this query.
    async with connection.transaction():
        await connection.fetchval("SELECT set_config('pg_trgm.similarity_threshold', $1, true)", str(threshold))
        results = await connection.fetch(RETRIEVE_SQL, query_norm, limit, tag_list)

    if use_cache:
        if len(_RETRIEVAL_CACHE) >= _CACHE_MAX_SIZE:
            _RETRIEVAL_CACHE.popitem(last=False)
        _RETRIEVAL_CACHE[cache_key] = results

    return results


