"""Shared bounded-reachability contracts and policy."""
from dataclasses import dataclass
from decimal import Decimal
import math
from numbers import Real

DEFAULT_KINDS = ("CALLS", "INHERITS")
ALLOWED_KINDS = frozenset({"CALLS", "INHERITS", "USES", "IMPORTS"})
DECAY = Decimal("0.8")


class TraversalBudgetExceeded(RuntimeError):
    """No complete result is returned when a traversal budget is exceeded."""


@dataclass(frozen=True)
class ImpactHit:
    symbol_id: int
    name: str
    qualname: str | None
    kind: str
    file_path: str
    depth: int
    min_depth: int
    score: float
    symbol_path: tuple[int, ...]
    edge_path: tuple[int, ...]


@dataclass(frozen=True)
class ReachabilityResult:
    repository_id: int
    root_symbol_id: int
    max_depth: int
    hits: tuple[ImpactHit, ...]
    skipped_confidence_edges: int


def positive_int(value, name, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def validate_options(repository_id, root_symbol_id, max_depth, kinds, max_results):
    positive_int(repository_id, "repository_id")
    positive_int(root_symbol_id, "root_symbol_id")
    positive_int(max_depth, "max_depth", 4)
    positive_int(max_results, "max_results", 100000)
    if isinstance(kinds, str):
        raise ValueError("kinds must be a sequence, not a string")
    kinds = tuple(sorted(set(kinds)))
    if not kinds or any(kind not in ALLOWED_KINDS for kind in kinds):
        raise ValueError("Unsupported or empty relationship kinds")
    return kinds


def edge_confidence(value):
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        return None
    try:
        if not math.isfinite(float(value)):
            return None
        result = Decimal(str(value))
        return result if Decimal(0) <= result <= Decimal(1) else None
    except (ValueError, OverflowError):
        return None
