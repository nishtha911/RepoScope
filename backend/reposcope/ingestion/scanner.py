import hashlib
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from .redaction import redact_secrets


MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Common programming extensions
LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
}

SUPPORTED_EXTENSIONS = set(LANGUAGE_BY_EXTENSION.keys()) | {
    ".hpp", ".md", ".json", ".yaml", ".yml", ".toml",
}


def detect_extension(file_path: str | Path) -> str:
    return Path(file_path).suffix.lower()


def detect_language(file_path: str | Path) -> str:
    extension = detect_extension(file_path)
    return LANGUAGE_BY_EXTENSION.get(extension, "unknown")


def hash_content(content: bytes) -> str:
    return sha256(content).hexdigest()


@dataclass
class ScannedFile:
    relative_path: str
    absolute_path: Path
    extension: str
    content_hash: str
    size_bytes: int


def scan_repository(
    repo_dir: Path | str,
    *,
    max_file_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> list[ScannedFile]:
    """
    Scans supported files with symlink and size guards.

    Content is redacted before hashing so downstream persistence never receives
    the most common credential formats. Files over the configured limit are
    skipped without being read into memory.
    """
    if type(max_file_size_bytes) is not int or max_file_size_bytes < 1:
        raise ValueError("max_file_size_bytes must be a positive integer")

    base_path = Path(repo_dir).resolve()
    if not base_path.exists() or not base_path.is_dir():
        raise ValueError(f"Invalid repository directory: {repo_dir}")

    results: list[ScannedFile] = []

    for root, dirs, files in os.walk(base_path, followlinks=False):
        # Skip hidden directories like .git
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and not (Path(root) / d).is_symlink()
        ]

        for filename in files:
            file_path = Path(root) / filename

            # Symlink guard
            if file_path.is_symlink():
                continue

            ext = file_path.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                if file_path.stat().st_size > max_file_size_bytes:
                    continue
                content = file_path.read_bytes()
            except (OSError, PermissionError):
                continue

            content_hash = hash_content(redact_secrets(content))
            rel_path = file_path.relative_to(base_path).as_posix()

            results.append(
                ScannedFile(
                    relative_path=rel_path,
                    absolute_path=file_path,
                    extension=ext,
                    content_hash=content_hash,
                    size_bytes=len(content),
                )
            )

    return sorted(results, key=lambda f: f.relative_path)
