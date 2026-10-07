import hashlib
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

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


def scan_repository(repo_dir: Path | str) -> list[ScannedFile]:
    """
    Scans repository files, skips symlinks, detects extensions, and computes SHA-256 hashes.
    """
    base_path = Path(repo_dir).resolve()
    if not base_path.exists() or not base_path.is_dir():
        raise ValueError(f"Invalid repository directory: {repo_dir}")

    results: list[ScannedFile] = []

    for root, dirs, files in os.walk(base_path, followlinks=False):
        # Skip hidden directories like .git
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        for filename in files:
            file_path = Path(root) / filename

            # Symlink guard
            if file_path.is_symlink():
                continue

            ext = file_path.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                content = file_path.read_bytes()
            except (OSError, PermissionError):
                continue

            content_hash = hash_content(content)
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
