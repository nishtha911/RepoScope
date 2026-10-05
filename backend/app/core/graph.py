from collections import deque
from collections.abc import Iterable


def reachable_nodes(
    edges: Iterable[tuple[str, str]],
    start: str,
    max_depth: int = 2,
) -> dict[str, int]:
    """Return nodes reachable from start and their shortest hop distance."""
    adjacency: dict[str, list[str]] = {}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)

    distances = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if distances[current] >= max_depth:
            continue
        for neighbor in adjacency.get(current, []):
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances