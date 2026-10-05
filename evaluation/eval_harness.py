from collections.abc import Sequence


def precision_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    return sum(item in relevant for item in retrieved[:k]) / k


def mean_reciprocal_rank(rankings: Sequence[Sequence[str]], relevant: set[str]) -> float:
    if not rankings:
        return 0.0
    reciprocal_ranks = []
    for ranking in rankings:
        reciprocal_ranks.append(
            next((1 / rank for rank, item in enumerate(ranking, 1) if item in relevant), 0.0)
        )
    return sum(reciprocal_ranks) / len(reciprocal_ranks)