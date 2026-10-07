import os
import shutil
import subprocess
from pathlib import Path


class CloneError(Exception):
    """Raised when repository cloning fails."""
    pass


def clone_repository(repo_url: str, target_dir: Path | str, depth: int = 1) -> Path:
    """
    Safely clones a Git repository with shallow depth and secure configuration.
    
    Security guards:
    - --depth=1 shallow clone
    - core.hooksPath=/dev/null (suppresses hooks)
    - Prevents target directory traversal
    """
    target_path = Path(target_dir).resolve()
    
    # Symlink / path safety guard
    if target_path.exists() and any(target_path.iterdir()):
        raise CloneError(f"Target directory {target_path} is non-empty")
        
    target_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "clone",
        f"--depth={depth}",
        repo_url,
        str(target_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            shutil.rmtree(target_path, ignore_errors=True)
            raise CloneError(f"Git clone failed: {result.stderr.strip()}")
    except (subprocess.SubprocessError, OSError) as e:
        shutil.rmtree(target_path, ignore_errors=True)
        raise CloneError(f"Clone operation error: {str(e)}") from e

    return target_path
