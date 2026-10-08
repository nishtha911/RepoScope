from dataclasses import dataclass
from pathlib import Path

from .clone import clone_repository
from .scanner import ScannedFile, scan_repository


class PipelineError(Exception):
    """Raised when scanning fails after a successful clone."""

    def __init__(
        self,
        message: str,
        *,
        repository_path: Path,
    ) -> None:
        super().__init__(message)
        self.repository_path = repository_path


@dataclass(frozen=True)
class CloneScanResult:
    """Result of a completed clone-and-scan operation."""

    repository_path: Path
    files: tuple[ScannedFile, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)


def clone_and_scan_repository(
    repo_url: str,
    target_dir: Path | str,
    *,
    workspace_root: Path | str,
    timeout_seconds: float = 120,
) -> CloneScanResult:
    """
    Clone a repository at depth 1, then scan the cloned files.

    Lifecycle:
    - Clone failures propagate as CloneError.
    - Clone failure cleanup belongs to clone_repository().
    - Successful clones are retained.
    - If scanning raises an exception, retain the clone and raise
      PipelineError with its location.

    This function does not enqueue jobs, parse symbols, persist data,
    or connect repository registration to real ingestion.
    """
    repository_path = clone_repository(
        repo_url,
        target_dir,
        depth=1,
        workspace_root=workspace_root,
        timeout_seconds=timeout_seconds,
    )

    try:
        files = tuple(scan_repository(repository_path))
    except Exception as exc:
        raise PipelineError(
            "Repository cloned, but scanning failed. "
            f"The clone was retained at: {repository_path}",
            repository_path=repository_path,
        ) from exc

    return CloneScanResult(
        repository_path=repository_path,
        files=files,
    )