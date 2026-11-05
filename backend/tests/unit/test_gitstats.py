"""Real disposable Git repositories; no network or application database."""
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import shutil
import subprocess

import pytest
from reposcope.ingestion.gitstats import (
    collect_git_stats, GitStatsError, is_bugfix_subject, _validate_report,
)

UTC = timezone.utc
AS_OF = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="Git executable required")


def git(root, *args, env=None):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, env=env).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Alice")
    git(tmp_path, "config", "user.email", "alice@example.com")
    git(tmp_path, "config", "core.autocrlf", "false")
    return tmp_path


def commit(repo, files, days=1, subject="feat: change", email="alice@example.com", name="Alice", when=None):
    for path, text in files.items():
        target = repo / path
        if text is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    git(repo, "add", "--all")
    timestamp = (when or AS_OF - timedelta(days=days)).isoformat()
    env = os.environ.copy()
    env.update(GIT_AUTHOR_DATE=timestamp, GIT_COMMITTER_DATE=timestamp,
               GIT_AUTHOR_NAME=name, GIT_COMMITTER_NAME=name,
               GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_EMAIL=email)
    git(repo, "commit", "--allow-empty", "-qm", subject, env=env)


def by_path(report):
    return {item.path: item for item in report.files}


def test_counts_authors_frequency_and_old_last_modified(repo):
    commit(repo, {"a.py": "old", "old.py": "old"}, days=120)
    commit(repo, {"a.py": "one"}, days=30, subject="fix: crash")
    commit(repo, {"a.py": "two"}, days=2, email="bob@example.com", name="Bob")
    report = collect_git_stats(repo, as_of=AS_OF)
    rows = by_path(report)
    assert rows["a.py"].commit_count_90d == 2
    assert rows["a.py"].distinct_authors_90d == 2
    assert rows["a.py"].bugfix_commit_count_90d == 1
    assert rows["a.py"].bugfix_frequency_90d == 0.5
    assert rows["a.py"].last_modified_at == AS_OF - timedelta(days=2)
    assert rows["old.py"].commit_count_90d == 0
    assert rows["old.py"].bugfix_frequency_90d == 0.0
    assert rows["old.py"].last_modified_at == AS_OF - timedelta(days=120)
    _validate_report(report)


def test_inclusive_window_boundaries_and_future_exclusion(repo):
    commit(repo, {"a.py": "one"}, when=AS_OF - timedelta(days=90, seconds=1))
    commit(repo, {"a.py": "two"}, when=AS_OF - timedelta(days=90))
    commit(repo, {"a.py": "three"}, when=AS_OF)
    commit(repo, {"a.py": "future"}, when=AS_OF + timedelta(seconds=1))
    row = by_path(collect_git_stats(repo, as_of=AS_OF))["a.py"]
    assert row.commit_count_90d == 2
    assert row.last_modified_at == AS_OF


def test_non_monotonic_dates_do_not_prune_recent_ancestor(repo):
    commit(repo, {"a.py": "recent"}, days=1)
    commit(repo, {"a.py": "older descendant"}, days=200)
    row = by_path(collect_git_stats(repo, as_of=AS_OF))["a.py"]
    assert row.commit_count_90d == 1
    assert row.last_modified_at == AS_OF - timedelta(days=1)


def test_deleted_paths_omitted_and_rename_is_path_local(repo):
    commit(repo, {"old.py": "one", "deleted.py": "x"}, days=5)
    commit(repo, {"old.py": None, "new.py": "one", "deleted.py": None}, days=1)
    rows = by_path(collect_git_stats(repo, as_of=AS_OF))
    assert set(rows) == {"new.py"}
    assert rows["new.py"].commit_count_90d == 1


def test_spaces_unicode_and_dirty_worktree_ignored(repo):
    commit(repo, {"folder/café name.py": "first"})
    (repo / "folder/café name.py").write_text("dirty", encoding="utf-8")
    (repo / "untracked.py").write_text("ignored", encoding="utf-8")
    rows = by_path(collect_git_stats(repo, as_of=AS_OF))
    assert set(rows) == {"folder/café name.py"}
    assert rows["folder/café name.py"].commit_count_90d == 1


@pytest.mark.skipif(os.name == "nt", reason="Windows forbids newline/tab filenames")
def test_nul_framing_preserves_newlines_and_tabs_in_names(repo):
    commit(repo, {"line\nname\t.py": "first"})
    assert set(by_path(collect_git_stats(repo, as_of=AS_OF))) == {"line\nname\t.py"}


def test_author_email_case_normalized_not_display_name(repo):
    commit(repo, {"a.py": "first"}, email="ALICE@example.com", name="Old name")
    commit(repo, {"a.py": "second"}, email="alice@example.com", name="New name")
    assert by_path(collect_git_stats(repo, as_of=AS_OF))["a.py"].distinct_authors_90d == 1


def test_one_commit_touching_multiple_files_counted_once_each(repo):
    commit(repo, {"a.py": "a", "b.py": "b"}, subject="fix: both")
    rows = by_path(collect_git_stats(repo, as_of=AS_OF))
    assert all(r.commit_count_90d == 1 and r.bugfix_commit_count_90d == 1 for r in rows.values())


def test_empty_commit_does_not_inflate_file_counts(repo):
    commit(repo, {"a.py": "a"})
    commit(repo, {}, subject="fix: empty")
    row = by_path(collect_git_stats(repo, as_of=AS_OF))["a.py"]
    assert row.commit_count_90d == 1
    assert row.bugfix_commit_count_90d == 0


def test_shallow_repository_rejected_without_fetch(repo, tmp_path_factory):
    commit(repo, {"a.py": "a"})
    commit(repo, {"a.py": "b"})
    dest = tmp_path_factory.mktemp("shallow-parent") / "clone"
    subprocess.run(["git", "clone", "--depth=1", repo.as_uri(), str(dest)], check=True, capture_output=True)
    with pytest.raises(GitStatsError, match="Shallow"):
        collect_git_stats(dest, as_of=AS_OF)


def test_limits_fail_instead_of_partial_results(repo):
    commit(repo, {"a.py": "a", "b.py": "b"})
    commit(repo, {"a.py": "c"})
    with pytest.raises(GitStatsError, match="max_commits"):
        collect_git_stats(repo, as_of=AS_OF, max_commits=1)
    with pytest.raises(GitStatsError, match="max_files"):
        collect_git_stats(repo, as_of=AS_OF, max_files=1)


def test_non_git_directory_rejected(tmp_path):
    with pytest.raises(GitStatsError):
        collect_git_stats(tmp_path, as_of=AS_OF)


def test_unborn_repository_rejected(repo):
    with pytest.raises(GitStatsError):
        collect_git_stats(repo, as_of=AS_OF)


@pytest.mark.parametrize("value", [datetime(2026, 1, 1), "yesterday", 123])
def test_naive_or_invalid_as_of_rejected(repo, value):
    with pytest.raises(ValueError, match="timezone-aware"):
        collect_git_stats(repo, as_of=value)


@pytest.mark.parametrize("value", [0, -1, True, float("inf"), float("nan")])
def test_invalid_timeout_rejected(repo, value):
    with pytest.raises(ValueError, match="timeout"):
        collect_git_stats(repo, as_of=AS_OF, timeout_seconds=value)


@pytest.mark.parametrize("subject,expected", [
    ("fix: crash", True), ("Fixes #123", True), ("hotfix payment", True),
    ("bugfix: overflow", True), ("avoid regression", True),
    ("feat: feature", False), ("prefix helper", False), ("fixtures updated", False),
])
def test_bugfix_heuristic_is_explicit(subject, expected):
    assert is_bugfix_subject(subject) is expected


def test_report_is_deterministic_for_fixed_window(repo):
    commit(repo, {"a.py": "a"})
    assert collect_git_stats(repo, as_of=AS_OF) == collect_git_stats(repo, as_of=AS_OF)


def test_timezone_normalized(repo):
    commit(repo, {"a.py": "a"})
    local = AS_OF.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert collect_git_stats(repo, as_of=local) == collect_git_stats(repo, as_of=AS_OF)


def test_binary_file_is_counted(repo):
    (repo / "blob.bin").write_bytes(bytes(range(256)))
    commit(repo, {}, subject="fix: binary payload")
    row = by_path(collect_git_stats(repo, as_of=AS_OF))["blob.bin"]
    assert row.commit_count_90d == 1
    assert row.bugfix_frequency_90d == 1.0


def test_merge_commit_not_double_counted(repo):
    commit(repo, {"a.py": "base"}, days=5)
    original = git(repo, "branch", "--show-current").decode().strip()
    git(repo, "checkout", "-qb", "side")
    commit(repo, {"b.py": "side"}, days=4, subject="fix: side")
    git(repo, "checkout", "-q", original)
    commit(repo, {"a.py": "main"}, days=3)
    env = os.environ.copy()
    env.update(GIT_AUTHOR_DATE=(AS_OF - timedelta(days=2)).isoformat(),
               GIT_COMMITTER_DATE=(AS_OF - timedelta(days=2)).isoformat())
    git(repo, "merge", "--no-ff", "side", "-m", "fix: merge side", env=env)
    rows = by_path(collect_git_stats(repo, as_of=AS_OF))
    assert rows["a.py"].commit_count_90d == 2
    assert rows["b.py"].commit_count_90d == 1
    assert rows["a.py"].bugfix_commit_count_90d == 0
