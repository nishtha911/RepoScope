from pathlib import Path

import pytest

from reposcope.ingestion.redaction import redact_secrets
from reposcope.ingestion.scanner import scan_repository


def test_redacts_common_credentials_before_hashing():
    github_token = b"gh" + b"p_" + b"x" * 36
    content = (
        b'API_KEY="abc123"\n'
        + b"token = " + github_token + b"\n"
        + b"AWS_ACCESS_KEY_ID=" + b"AKIA" + b"X" * 16 + b"\n"
    )

    redacted = redact_secrets(content)

    assert b"abc123" not in redacted
    assert b"ghp_" not in redacted
    assert b"AKIA" + b"X" * 16 not in redacted
    assert b"[REDACTED]" in redacted


def test_scanner_skips_files_over_size_budget(tmp_path: Path):
    source = tmp_path / "large.py"
    source.write_bytes(b"x" * 11)

    assert scan_repository(tmp_path, max_file_size_bytes=10) == []


def test_scanner_rejects_invalid_size_budget(tmp_path: Path):
    with pytest.raises(ValueError):
        scan_repository(tmp_path, max_file_size_bytes=0)


def test_scanner_skips_symlink_files(tmp_path: Path):
    target = tmp_path / "outside.py"
    target.write_text("password='not persisted'", encoding="utf-8")
    link = tmp_path / "linked.py"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable on this platform")

    files = scan_repository(tmp_path)

    assert [item.relative_path for item in files] == ["outside.py"]


def test_scanner_does_not_follow_symlink_directories(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("TOKEN='nope'", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    link = repo / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable on this platform")

    assert scan_repository(repo) == []
