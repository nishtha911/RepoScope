import subprocess

import pytest

from reposcope.ingestion import clone as clone_module


REPO_URL = "https://github.com/example/example.git"


@pytest.fixture
def failing_git(monkeypatch):
    """Simulate a Git failure without accessing the network."""

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Simulated Git failure",
        )

    monkeypatch.setattr(
        clone_module.subprocess,
        "run",
        fake_run,
    )


@pytest.fixture
def forbid_git(monkeypatch):
    """Fail the test if Git is launched."""

    def unexpected_git_call(*args, **kwargs):
        pytest.fail(
            "Git must not run for an unsafe destination."
        )

    monkeypatch.setattr(
        clone_module.subprocess,
        "run",
        unexpected_git_call,
    )


def test_failure_preserves_existing_empty_directory(
    tmp_path,
    failing_git,
):
    target = tmp_path / "existing-folder"
    target.mkdir()

    with pytest.raises(clone_module.CloneError):
        clone_module.clone_repository(
            REPO_URL,
            target,
            workspace_root=tmp_path,
        )

    assert target.is_dir(), (
        "Clone failure deleted a caller-owned directory."
    )


def test_failure_removes_operation_created_directory(
    tmp_path,
    failing_git,
):
    target = tmp_path / "new-clone"

    assert not target.exists()

    with pytest.raises(clone_module.CloneError):
        clone_module.clone_repository(
            REPO_URL,
            target,
            workspace_root=tmp_path,
        )

    assert not target.exists()


def test_nonempty_directory_is_preserved_without_running_git(
    tmp_path,
    forbid_git,
):
    target = tmp_path / "existing-project"
    target.mkdir()

    existing_file = target / "important.txt"
    existing_file.write_text(
        "Keep this file.",
        encoding="utf-8",
    )

    with pytest.raises(clone_module.CloneError):
        clone_module.clone_repository(
            REPO_URL,
            target,
            workspace_root=tmp_path,
        )

    assert existing_file.read_text(
        encoding="utf-8"
    ) == "Keep this file."


def test_destination_outside_workspace_is_rejected(
    tmp_path,
    forbid_git,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    marker = outside / "important.txt"
    marker.write_text("Keep me.", encoding="utf-8")

    with pytest.raises(clone_module.CloneError):
        clone_module.clone_repository(
            REPO_URL,
            outside / "repo",
            workspace_root=workspace,
        )

    assert marker.read_text(encoding="utf-8") == "Keep me."
    assert not (outside / "repo").exists()


def test_workspace_root_cannot_be_destination(
    tmp_path,
    forbid_git,
):
    with pytest.raises(clone_module.CloneError):
        clone_module.clone_repository(
            REPO_URL,
            tmp_path,
            workspace_root=tmp_path,
        )

    assert tmp_path.is_dir()


def test_parent_traversal_is_rejected(
    tmp_path,
    forbid_git,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(clone_module.CloneError):
        clone_module.clone_repository(
            REPO_URL,
            "../escaped-repo",
            workspace_root=workspace,
        )

    assert not (tmp_path / "escaped-repo").exists()


def test_valid_destination_inside_workspace_is_allowed(
    tmp_path,
    monkeypatch,
):
    def successful_git(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        clone_module.subprocess,
        "run",
        successful_git,
    )

    result = clone_module.clone_repository(
        REPO_URL,
        "repo",
        workspace_root=tmp_path,
    )

    assert result == (tmp_path / "repo").resolve()
    assert result.is_dir()

def _run_git(directory, *arguments):
    """Run Git with test-only settings, without changing global config."""
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
    """Create a local repository with three commits."""
    source = tmp_path / "source"
    source.mkdir()

    _run_git(source, "init")

    for version in range(1, 4):
        (source / "main.py").write_bytes(
            f"VALUE = {version}\n".encode("utf-8")
        )

        _run_git(source, "add", "main.py")
        _run_git(
            source,
            "commit",
            "-m",
            f"Fixture version {version}",
        )

    assert _run_git(source, "rev-list", "--count", "HEAD") == "3"

    return source


def test_successful_local_clone(tmp_path, local_source_repo):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = clone_module.clone_repository(
        local_source_repo.resolve().as_uri(),
        "repo",
        workspace_root=workspace,
    )

    assert result == (workspace / "repo").resolve()
    assert (result / ".git").is_dir()
    assert (result / "main.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 3\n"

    source_head = _run_git(local_source_repo, "rev-parse", "HEAD")
    clone_head = _run_git(result, "rev-parse", "HEAD")

    assert clone_head == source_head


def test_clone_has_shallow_depth_one(tmp_path, local_source_repo):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = clone_module.clone_repository(
        local_source_repo.resolve().as_uri(),
        "repo",
        workspace_root=workspace,
    )

    assert _run_git(
        result,
        "rev-parse",
        "--is-shallow-repository",
    ) == "true"

    assert _run_git(
        result,
        "rev-list",
        "--count",
        "HEAD",
    ) == "1"


def test_clone_command_suppresses_hooks(tmp_path, monkeypatch):
    captured = {}

    def successful_git(*args, **kwargs):
        captured["command"] = args[0]
        captured["options"] = kwargs

        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        clone_module.subprocess,
        "run",
        successful_git,
    )

    clone_module.clone_repository(
        REPO_URL,
        "repo",
        workspace_root=tmp_path,
    )

    command = captured["command"]

    assert command[:4] == [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "clone",
    ]
    assert "--depth=1" in command
    assert captured["options"]["timeout"] == 120
    assert not captured["options"].get("shell", False)

def test_timeout_cleans_partial_destination(tmp_path, monkeypatch):
    target = tmp_path / "repo"

    def timed_out_git(*args, **kwargs):
        (target / "partial.py").write_bytes(b"partial download")

        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=120,
        )

    monkeypatch.setattr(
        clone_module.subprocess,
        "run",
        timed_out_git,
    )

    with pytest.raises(clone_module.CloneError):
        clone_module.clone_repository(
            REPO_URL,
            target,
            workspace_root=tmp_path,
        )

    assert not target.exists()


def test_missing_git_executable_cleans_destination(tmp_path, monkeypatch):
    target = tmp_path / "repo"

    def missing_git(*args, **kwargs):
        raise FileNotFoundError("Git executable not found")

    monkeypatch.setattr(
        clone_module.subprocess,
        "run",
        missing_git,
    )

    with pytest.raises(
        clone_module.CloneError,
        match="Git executable not found",
    ):
        clone_module.clone_repository(
            REPO_URL,
            target,
            workspace_root=tmp_path,
        )

    assert not target.exists()


def test_failed_clone_cleans_partial_readonly_file(tmp_path, monkeypatch):
    target = tmp_path / "repo"

    def failed_git(*args, **kwargs):
        partial = target / "partial.py"
        partial.write_bytes(b"partial download")
        partial.chmod(clone_module.stat.S_IREAD)

        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Simulated partial-clone failure",
        )

    monkeypatch.setattr(
        clone_module.subprocess,
        "run",
        failed_git,
    )

    with pytest.raises(clone_module.CloneError):
        clone_module.clone_repository(
            REPO_URL,
            target,
            workspace_root=tmp_path,
        )

    assert not target.exists()


def test_cleanup_failure_is_reported(tmp_path, monkeypatch, failing_git):
    target = tmp_path / "repo"

    def denied_cleanup(*args, **kwargs):
        raise PermissionError("Simulated cleanup denial")

    monkeypatch.setattr(
        clone_module.shutil,
        "rmtree",
        denied_cleanup,
    )

    with pytest.raises(
        clone_module.CloneError,
        match="cleanup failed",
    ) as captured:
        clone_module.clone_repository(
            REPO_URL,
            target,
            workspace_root=tmp_path,
        )

    message = str(captured.value)

    assert "Simulated Git failure" in message
    assert "Simulated cleanup denial" in message
    assert target.is_dir()


def test_replaced_destination_is_not_deleted(tmp_path, monkeypatch):
    target = tmp_path / "repo"
    original = tmp_path / "original-operation-directory"

    def replace_then_fail(*args, **kwargs):
        target.rename(original)

        target.mkdir()
        (target / "important.txt").write_bytes(b"Do not delete")

        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Simulated failure after replacement",
        )

    monkeypatch.setattr(
        clone_module.subprocess,
        "run",
        replace_then_fail,
    )

    with pytest.raises(
        clone_module.CloneError,
        match="destination identity changed",
    ):
        clone_module.clone_repository(
            REPO_URL,
            target,
            workspace_root=tmp_path,
        )

    assert (target / "important.txt").read_bytes() == b"Do not delete"
    assert original.is_dir()