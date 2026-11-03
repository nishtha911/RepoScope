"""Pure reciprocal rank fusion over ranked chunk IDs.

No database access, embedding imports, or configuration side effects.
Input lists must already be ranked best-first and share one chunk-ID
namespace and repository scope.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FusedHit:
    chunk_id: int
    score: float


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]],
    *,
    k: int = 60,
    limit: int = 20,
) -> list[FusedHit]:
    """Combine ranked lists using sum(1 / (k + rank)).

    Ranks start at 1. Missing items contribute zero.

    Duplicate IDs within one input list are ignored, and ranks are
    assigned after deduplication, preserving first occurrence order.

    Equal final scores are ordered by ascending chunk ID.
    """
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
    ):
        raise ValueError("limit must be a positive integer")

    contributions: dict[int, list[float]] = {}

    for ranking in rankings:
        seen: set[int] = set()
        rank = 0

        for chunk_id in ranking:
            if (
                isinstance(chunk_id, bool)
                or not isinstance(chunk_id, int)
                or chunk_id < 1
            ):
                raise ValueError("chunk IDs must be positive integers")

            if chunk_id in seen:
                continue

            seen.add(chunk_id)
            rank += 1

            contributions.setdefault(chunk_id, []).append(
                1.0 / (k + rank)
            )

    # Stable summation avoids depending on input-list iteration order
    # when accumulating equivalent contributions.
    from math import fsum

    hits = [
        FusedHit(chunk_id=chunk_id, score=fsum(values))
        for chunk_id, values in contributions.items()
    ]

    hits.sort(key=lambda hit: (-hit.score, hit.chunk_id))

    return hits[:limit]