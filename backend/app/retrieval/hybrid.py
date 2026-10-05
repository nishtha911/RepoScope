from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[T]],
    constant: int = 60,
) -> list[tuple[T, float]]:
    scores: dict[T, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1 / (constant + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)