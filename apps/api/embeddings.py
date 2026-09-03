"""
Embeddings-based conflict detection for incident facts.
Uses OpenAI text-embedding-3-small for semantic similarity.
Falls back gracefully when OPENAI_API_KEY is not set.
"""
from __future__ import annotations

import os
import logging
import math
from typing import Any

import httpx

logger = logging.getLogger("agora.embeddings")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_ENABLED = bool(OPENAI_API_KEY)

# In-memory cache: text -> embedding vector
_cache: dict[str, list[float]] = {}


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector for text via OpenAI API."""
    if not EMBEDDING_ENABLED:
        return []

    cache_key = text[:500]  # truncate for cache key
    if cache_key in _cache:
        return _cache[cache_key]

    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": EMBEDDING_MODEL, "input": text[:8000]}  # max tokens

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            embedding = data["data"][0]["embedding"]
            _cache[cache_key] = embedding
            return embedding
    except Exception as e:
        logger.warning(f"Embedding request failed: {e}")
        return []


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def find_similar_facts(
    facts: list[dict[str, Any]],
    threshold: float = 0.85,
) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    """
    Find pairs of facts with high semantic similarity.
    Returns list of (fact_a, fact_b, similarity) tuples.
    """
    if not EMBEDDING_ENABLED or len(facts) < 2:
        return []

    # Get embeddings for all facts
    embeddings: dict[str, list[float]] = {}
    for f in facts:
        emb = await get_embedding(f.get("statement", ""))
        if emb:
            embeddings[f["id"]] = emb

    # Compare all pairs
    pairs: list[tuple[dict, dict, float]] = []
    fact_map = {f["id"]: f for f in facts}
    seen: set[tuple[str, str]] = set()

    for f1 in facts:
        for f2 in facts:
            if f1["id"] >= f2["id"]:
                continue
            pair_key = (f1["id"], f2["id"])
            if pair_key in seen:
                continue
            seen.add(pair_key)

            e1 = embeddings.get(f1["id"], [])
            e2 = embeddings.get(f2["id"], [])
            if e1 and e2:
                sim = cosine_similarity(e1, e2)
                if sim >= threshold:
                    pairs.append((f1, f2, sim))

    return pairs


async def detect_embedding_conflicts(
    facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Detect conflicts using embeddings. Two facts are conflicting if:
    1. They are semantically similar (high cosine similarity)
    2. They have different values or status
    """
    similar_pairs = await find_similar_facts(facts, threshold=0.80)
    gaps: list[dict[str, Any]] = []

    for f1, f2, sim in similar_pairs:
        # Check if they actually conflict (different status or different values)
        status_conflict = f1.get("status") != f2.get("status")
        # Check if statements contain different numbers
        import re
        nums1 = set(re.findall(r"(\d+(?:\.\d+)?)", f1.get("statement", "")))
        nums2 = set(re.findall(r"(\d+(?:\.\d+)?)", f2.get("statement", "")))
        value_conflict = nums1 != nums2 and nums1 and nums2

        if status_conflict or value_conflict:
            gaps.append({
                "id": f"gap-embed-{f1['id']}-{f2['id']}",
                "kind": "ConflictingInfo",
                "severity": "high",
                "message": f"Semantically similar facts with conflicts: '{f1.get('statement', '')[:60]}' vs '{f2.get('statement', '')[:60]}' (sim={sim:.2f})",
                "relatedIds": [f1["id"], f2["id"]],
            })

    return gaps
