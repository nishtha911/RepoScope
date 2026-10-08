from typing import Protocol

from reposcope.contracts.api import RepositoryResponse
from reposcope.contracts.vocabulary import RepositoryStatus


class RepositoryRow(Protocol):
    id: int
    full_name: str
    remote_url: str


def repository_to_response(
    row: RepositoryRow,
    *,
    default_branch: str,
    status: RepositoryStatus,
    snapshot_id: int | None,
    head_sha: str | None,
    file_count: int | None,
    symbol_count: int | None,
) -> RepositoryResponse:
    """Map ORM names explicitly; the caller supplies real selected-snapshot metadata."""
    return RepositoryResponse(
        id=row.id,
        name=row.full_name,
        url=row.remote_url,
        default_branch=default_branch,
        status=status,
        snapshot_id=snapshot_id,
        head_sha=head_sha,
        file_count=file_count,
        symbol_count=symbol_count,
    )
