import subprocess
from hashlib import sha256

import pytest

from reposcope.ingestion import pipeline as pipeline_module
from reposcope.ingestion.clone import CloneError


def _run_git(directory, *arguments):
    """Run Git using test-only settings."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=RepoScope Test",
            "-c",
            "user.email=reposcope-test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.autocrlf=false",
            *arguments,
        ],
        cwd=directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        check=True,
    )

    return result.stdout.strip()


@pytest.fixture
def local_source_repo(tmp_path):
    """Create a repository with three commits and known file bytes."""
    source = tmp_path / "source"
    source.mkdir()

    _run_git(source, "init")

    # No newline characters: checkout newline conversion cannot
    # change these test inputs.
    (source / "README.md").write_bytes(b"Mini pipeline fixture")
    (source / "ignore.bin").write_bytes(b"\x00\x01\x02")

    for version in range(1, 4):
        (source / "main.py").write_bytes(
            f"VALUE = {version}".encode("utf-8")
        )

        _run_git(source, "add", ".")
        _run_git(
            source,
            "commit",
            "-m",
            f"Pipeline fixture version {version}",
        )

    assert _run_git(source, "rev-list", "--count", "HEAD") == "3"

    return source


def test_real_clone_then_scan(tmp_path, local_source_repo):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = pipeline_module.clone_and_scan_repository(
        local_source_repo.resolve().as_uri(),
        "repo",
        workspace_root=workspace,
    )

    repository_path = (workspace / "repo").resolve()

    assert result.repository_path == repository_path
    assert repository_path.is_dir()
    assert (repository_path / ".git").is_dir()

    assert _run_git(
        repository_path,
        "rev-parse",
        "--is-shallow-repository",
    ) == "true"

    assert _run_git(
        repository_path,
        "rev-list",
        "--count",
        "HEAD",
    ) == "1"

    assert _run_git(
        repository_path,
        "rev-parse",
        "HEAD",
    ) == _run_git(
        local_source_repo,
        "rev-parse",
        "HEAD",
    )

    assert result.file_count == 2

    paths = [file.relative_path for file in result.files]
    assert paths == ["README.md", "main.py"]

    expected_contents = {
        "README.md": b"Mini pipeline fixture",
        "main.py": b"VALUE = 3",
    }

    for scanned_file in result.files:
        content = expected_contents[scanned_file.relative_path]

        assert scanned_file.content_hash == sha256(content).hexdigest()
        assert scanned_file.size_bytes == len(content)
        assert scanned_file.extension in {".md", ".py"}

        assert scanned_file.absolute_path == (
            repository_path / scanned_file.relative_path
        )

    # The unsupported binary file exists but was not scanned.
    assert (repository_path / "ignore.bin").exists()
    assert "ignore.bin" not in paths

    # Git metadata must not appear in scanner results.
    assert not any(
        path.startswith(".git/")
        for path in paths
    )


def test_clone_failure_does_not_start_scanning(tmp_path, monkeypatch):
    def failed_clone(*args, **kwargs):
        raise CloneError("Simulated clone failure")

    def unexpected_scan(*args, **kwargs):
        pytest.fail("Scanning must not start after clone failure.")

    monkeypatch.setattr(
        pipeline_module,
        "clone_repository",
        failed_clone,
    )
    monkeypatch.setattr(
        pipeline_module,
        "scan_repository",
        unexpected_scan,
    )

    with pytest.raises(
        CloneError,
        match="Simulated clone failure",
    ):
        pipeline_module.clone_and_scan_repository(
            "https://github.com/example/example.git",
            "repo",
            workspace_root=tmp_path,
        )


def test_scan_failure_retains_clone(
    tmp_path,
    local_source_repo,
    monkeypatch,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def failed_scan(repository_path):
        assert (repository_path / "main.py").is_file()
        raise OSError("Simulated scanner failure")

    monkeypatch.setattr(
        pipeline_module,
        "scan_repository",
        failed_scan,
    )

    with pytest.raises(
        pipeline_module.PipelineError,
        match="scanning failed",
    ) as captured:
        pipeline_module.clone_and_scan_repository(
            local_source_repo.resolve().as_uri(),
            "repo",
            workspace_root=workspace,
        )

    repository_path = (workspace / "repo").resolve()

    assert captured.value.repository_path == repository_path
    assert isinstance(captured.value.__cause__, OSError)

    assert repository_path.is_dir()
    assert (repository_path / "main.py").read_bytes() == b"VALUE = 3"