from pathlib import Path
import pytest
from reposcope.ingestion.clone import CloneError, clone_repository
from reposcope.ingestion.scanner import (
    detect_extension,
    detect_language,
    hash_content,
    scan_repository,
)


def test_extension_detection():
    assert detect_extension("src/service.PY") == ".py"
    assert detect_extension("src/App.tsx") == ".tsx"
    assert detect_extension("README") == ""


def test_language_detection():
    assert detect_language("service.py") == "python"
    assert detect_language("App.tsx") == "typescript"
    assert detect_language("data.xyz") == "unknown"


def test_sha256_known_value():
    assert hash_content(b"hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e"
        "1b161e5c1fa7425e73043362938b9824"
    )


def test_hash_changes_when_content_changes():
    assert hash_content(b"hello") != hash_content(b"Hello")


def test_clone_invalid_url(tmp_path: Path):
    target = tmp_path / "cloned"
    with pytest.raises(CloneError):
        clone_repository("https://invalid.github.com/nonexistent/repo.git", target)


def test_scan_repository(tmp_path: Path):
    # Create mock repo files
    (tmp_path / "main.py").write_text("def hello(): pass\n", encoding="utf-8")
    (tmp_path / "utils.py").write_text("class Util: pass\n", encoding="utf-8")
    (tmp_path / "ignore.bin").write_bytes(b"\x00\x01\x02")

    files = scan_repository(tmp_path)
    assert len(files) == 2
    paths = [f.relative_path for f in files]
    assert "main.py" in paths
    assert "utils.py" in paths
    assert files[0].content_hash != ""
