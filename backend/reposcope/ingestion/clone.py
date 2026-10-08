import math
import os
import shutil
import stat
import subprocess
from pathlib import Path


class CloneError(Exception):
    """Raised when cloning or its safety checks fail."""


def _reject_linked_components(path: Path) -> None:
    """Reject symlinks and Windows reparse points in existing components."""
    for component in (path, *path.parents):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CloneError(
                f"Could not inspect path component: {component}"
            ) from exc

        is_symlink = stat.S_ISLNK(metadata.st_mode)

        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_flag = getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
        is_reparse_point = bool(attributes & reparse_flag)

        if is_symlink or is_reparse_point:
            raise CloneError(
                f"Linked path components are not allowed: {component}"
            )


def _directory_identity(path: Path) -> tuple[int, int]:
    """Return device/file identifiers for an ordinary directory."""
    metadata = path.lstat()

    if not stat.S_ISDIR(metadata.st_mode):
        raise CloneError(f"Expected a directory: {path}")

    return metadata.st_dev, metadata.st_ino


def _validate_destination(
    target_dir: Path | str,
    workspace_root: Path | str,
) -> tuple[Path, Path, tuple[int, int]]:
    """Validate an existing workspace and a new contained destination."""
    workspace = Path(workspace_root)

    if ".." in workspace.parts:
        raise CloneError("Workspace path must not contain '..'.")

    if workspace.drive and not workspace.is_absolute():
        raise CloneError(
            "Drive-relative workspace paths are not allowed."
        )

    if not workspace.is_absolute():
        workspace = Path.cwd() / workspace

    _reject_linked_components(workspace)

    try:
        workspace = workspace.resolve(strict=True)
        workspace_identity = _directory_identity(workspace)
    except (OSError, RuntimeError) as exc:
        raise CloneError(
            "Workspace must be an existing directory."
        ) from exc

    requested = Path(target_dir)

    if ".." in requested.parts:
        raise CloneError("Destination path must not contain '..'.")

    if requested.drive and not requested.is_absolute():
        raise CloneError(
            "Drive-relative destinations are not allowed."
        )

    if not requested.is_absolute():
        requested = workspace / requested

    _reject_linked_components(requested)

    try:
        target = requested.resolve()
    except (OSError, RuntimeError) as exc:
        raise CloneError(
            "Could not resolve destination."
        ) from exc

    if target == workspace or not target.is_relative_to(workspace):
        raise CloneError(
            "Destination must be strictly inside the approved workspace."
        )

    if os.path.lexists(target):
        raise CloneError(
            f"Target destination already exists: {target}"
        )

    if not target.parent.is_dir():
        raise CloneError(
            "Destination parent must already exist inside the workspace."
        )

    return target, workspace, workspace_identity


def _check_owned_destination(
    target_path: Path,
    workspace_path: Path,
    workspace_identity: tuple[int, int],
    target_identity: tuple[int, int],
) -> bool:
    """
    Verify workspace and destination identities.

    Return False if the destination no longer exists.
    Raise CloneError for unsafe or replaced paths.
    """
    _reject_linked_components(workspace_path)

    if _directory_identity(workspace_path) != workspace_identity:
        raise CloneError(
            "Safety check refused: workspace identity changed."
        )

    if workspace_path.resolve(strict=True) != workspace_path:
        raise CloneError(
            "Safety check refused: workspace location changed."
        )

    _reject_linked_components(target_path)

    try:
        current_identity = _directory_identity(target_path)
    except FileNotFoundError:
        return False

    if current_identity != target_identity:
        raise CloneError(
            "Safety check refused: destination identity changed."
        )

    resolved_target = target_path.resolve(strict=True)

    if (
        resolved_target != target_path
        or resolved_target == workspace_path
        or not resolved_target.is_relative_to(workspace_path)
    ):
        raise CloneError(
            "Safety check refused: destination escaped the workspace."
        )

    return True


def _cleanup_owned_destination(
    target_path: Path,
    workspace_path: Path,
    workspace_identity: tuple[int, int],
    target_identity: tuple[int, int],
) -> None:
    """Clean up only the original, contained operation directory."""

    def check_ownership() -> bool:
        return _check_owned_destination(
            target_path,
            workspace_path,
            workspace_identity,
            target_identity,
        )

    if not check_ownership():
        # Git may have already removed the failed clone.
        return

    def remove_readonly(function, path, exc_info):
        error = exc_info[1]

        if not isinstance(error, PermissionError):
            raise error

        if function not in (os.unlink, os.remove, os.rmdir):
            raise error

        if not check_ownership():
            raise CloneError(
                "Cleanup refused: operation directory disappeared."
            )

        candidate = Path(path)
        _reject_linked_components(candidate)

        resolved_candidate = candidate.resolve(strict=True)

        if (
            resolved_candidate != target_path
            and not resolved_candidate.is_relative_to(target_path)
        ):
            raise CloneError(
                "Cleanup refused: entry escaped the operation directory."
            )

        metadata = candidate.lstat()
        os.chmod(candidate, metadata.st_mode | stat.S_IWRITE)
        function(path)

    # Do not suppress cleanup errors.
    shutil.rmtree(
        target_path,
        onerror=remove_readonly,
    )

    if os.path.lexists(target_path):
        raise CloneError(
            "Cleanup failed: destination still exists."
        )


def clone_repository(
    repo_url: str,
    target_dir: Path | str,
    depth: int = 1,
    *,
    workspace_root: Path | str,
    timeout_seconds: float = 120,
) -> Path:
    """
    Clone a repository at depth 1 inside a trusted workspace.

    Rules:
    - Workspace must already exist.
    - Destination must be a strict descendant of the workspace.
    - Destination must not already exist.
    - Linked path components and Windows reparse points are rejected.
    - Missing parent directories are not created.
    - Git hooks are suppressed for the clone command.
    - Only the operation-created directory is eligible for cleanup.
    - Cleanup failures are reported.

    Relative destinations are interpreted inside workspace_root.

    This function does not enforce remote-host/SSRF policy, sandbox Git,
    scan files, persist results, or enqueue jobs. The workspace and Git
    configuration/environment must be controlled by the service.
    """
    if not isinstance(repo_url, str) or not repo_url.strip():
        raise CloneError("Repository URL must be a nonempty string.")

    if repo_url.startswith("-") or "\x00" in repo_url:
        raise CloneError("Invalid repository URL.")

    if type(depth) is not int or depth != 1:
        raise CloneError("This clone service requires depth=1.")

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise CloneError("Timeout must be a positive finite number.")

    target_path, workspace_path, workspace_identity = (
        _validate_destination(target_dir, workspace_root)
    )

    try:
        target_path.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        # Creation failed: this operation does not own the destination.
        raise CloneError(
            f"Could not create clone destination: {target_path}"
        ) from exc

    try:
        _reject_linked_components(target_path)
        target_identity = _directory_identity(target_path)
    except (CloneError, OSError) as exc:
        # Ownership could not be established; do not delete blindly.
        raise CloneError(
            "Could not establish destination ownership; "
            "automatic cleanup was not attempted."
        ) from exc

    cmd = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "clone",
        "--depth=1",
        "--",
        repo_url,
        str(target_path),
    ]

    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            env=environment,
        )

        if result.returncode != 0:
            raise CloneError(
                f"Git clone failed: {result.stderr.strip()}"
            )

        if not _check_owned_destination(
            target_path,
            workspace_path,
            workspace_identity,
            target_identity,
        ):
            raise CloneError(
                "Git reported success, but the destination is missing."
            )

    except (
        CloneError,
        subprocess.SubprocessError,
        OSError,
        RuntimeError,
    ) as exc:
        try:
            _cleanup_owned_destination(
                target_path,
                workspace_path,
                workspace_identity,
                target_identity,
            )
        except (CloneError, OSError, RuntimeError) as cleanup_exc:
            raise CloneError(
                f"Clone failed: {exc}; cleanup failed: {cleanup_exc}"
            ) from exc

        if isinstance(exc, CloneError):
            raise

        raise CloneError(
            f"Clone operation error: {exc}"
        ) from exc

    return target_path