from collections.abc import Iterable


def resolve_name(name: str, candidates: Iterable[str]) -> str | None:
    """Resolve an exact symbol name only when it has one unambiguous match."""
    matches = [candidate for candidate in candidates if candidate == name]
    return matches[0] if len(matches) == 1 else None