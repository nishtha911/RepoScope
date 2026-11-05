"""Per-file Git churn over a rolling 90-day UTC window.

Semantics: pinned HEAD/current tracked paths; all reachable non-merge commits;
raw normalized author email (name fallback); committer timestamps; inclusive
window endpoints. last_modified_at spans all available history up to as_of.
Renames are path-local (no --follow); dirty working-tree edits are ignored.
Bugfix frequency is a message-subject heuristic, not verified bug classification.
Shallow history is rejected. This module never fetches or executes repo code.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

BUGFIX_RULE_VERSION = "subject-keywords-v1"
_BUGFIX = re.compile(r"\b(?:fix(?:es|ed|ing)?|bugfix(?:es)?|hotfix(?:es)?|bugs?|regressions?)\b", re.I)
_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
UTC = timezone.utc


class GitStatsError(RuntimeError):
    """No complete trustworthy statistics could be produced."""


@dataclass(frozen=True)
class FileGitStats:
    path: str
    commit_count_90d: int
    distinct_authors_90d: int
    last_modified_at: datetime | None
    bugfix_commit_count_90d: int
    bugfix_frequency_90d: float


@dataclass(frozen=True)
class GitStatsReport:
    head_sha: str
    window_start: datetime
    window_end: datetime
    files: tuple[FileGitStats, ...]
    bugfix_rule_version: str = BUGFIX_RULE_VERSION


def is_bugfix_subject(subject: str) -> bool:
    return bool(_BUGFIX.search(subject))


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _decode(value):
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GitStatsError("Git paths/metadata must be valid UTF-8") from exc


def collect_git_stats(repository_path, *, as_of=None, timeout_seconds=60, max_commits=20000, max_files=100000):
    """Read a local complete Git repository; no writes, network calls or commits.

    Limits fail closed rather than returning partial counts. Large repositories
    may require explicit larger budgets. Paths are pinned to HEAD's tree, not
    to the current working directory contents. Submodules/gitlinks are omitted.
    """
    end = _utc(as_of if as_of is not None else datetime.now(UTC))
    start = end - timedelta(days=90)
    for name, value in (("max_commits", max_commits), ("max_files", max_files)):
        if type(value) is not int or value < 1:
            raise ValueError(name + " must be a positive integer")
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise ValueError("timeout_seconds must be positive and finite")
    root = Path(repository_path).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository_path must be a directory")
    deadline = time.monotonic() + timeout_seconds
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment.update(GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1",
                       GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    def git(*args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GitStatsError("Git statistics exceeded the total timeout")
        try:
            completed = subprocess.run(
                ["git", "--no-pager", "-c", "core.fsmonitor=false", "-c", "i18n.logOutputEncoding=UTF-8", "-C", str(root), *args],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                env=environment, timeout=remaining,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GitStatsError("Git command failed or timed out") from exc
        if completed.returncode:
            raise GitStatsError("Git command failed: " + completed.stderr.decode("utf-8", errors="replace").strip())
        return completed.stdout
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        raise GitStatsError("Shallow history cannot produce complete churn statistics; use an approved full-history clone")
    head = _decode(git("rev-parse", "--verify", "HEAD^{commit}").strip())
    if not _SHA.fullmatch(head):
        raise GitStatsError("Invalid pinned HEAD commit")
    tree = git("ls-tree", "-r", "-z", head)
    paths = []
    for item in tree.split(b"\0"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        if metadata.split()[1] == b"blob":
            paths.append(_decode(path))
    if len(paths) > max_files:
        raise GitStatsError("Repository exceeds max_files")
    # NUL-delimited fixed-width metadata; path names never share its framing.
    raw = git("log", "--no-show-signature", "--no-merges", "-z", "--format=%H%x00%ct%x00%ae%x00%an%x00%s",
              "--max-count=" + str(max_commits + 1), head, "--")
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 5:
        raise GitStatsError("Malformed Git log metadata")
    commits = [fields[i:i + 5] for i in range(0, len(fields), 5)]
    if len(commits) > max_commits:
        raise GitStatsError("History exceeds max_commits; no partial statistics returned")
    counts = {p: 0 for p in paths}
    authors = {p: set() for p in paths}
    fixes = {p: 0 for p in paths}
    modified = {p: None for p in paths}
    for sha_bytes, timestamp, email, name, subject in commits:
        sha = _decode(sha_bytes)
        if not _SHA.fullmatch(sha):
            raise GitStatsError("Malformed commit SHA")
        try:
            when = datetime.fromtimestamp(int(timestamp), UTC)
        except (ValueError, OverflowError, OSError) as exc:
            raise GitStatsError("Invalid commit timestamp") from exc
        if when > end:
            continue
        # Read all history: older commits can have non-monotonic timestamps.
        changed = {_decode(p) for p in git(
            "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z",
            "--no-renames", "--no-ext-diff", "--no-textconv", sha, "--",
        ).split(b"\0") if p}
        identity = "email:" + _decode(email).strip().casefold() if email.strip() else "name:" + _decode(name).strip().casefold()
        bugfix = is_bugfix_subject(_decode(subject))
        for path in changed & counts.keys():
            previous = modified[path]
            if previous is None or when > previous:
                modified[path] = when
            if when >= start:
                counts[path] += 1
                authors[path].add(identity)
                fixes[path] += int(bugfix)
    return GitStatsReport(head, start, end, tuple(
        FileGitStats(p, counts[p], len(authors[p]), modified[p], fixes[p],
                     fixes[p] / counts[p] if counts[p] else 0.0)
        for p in sorted(paths)
    ))


def _validate_report(report):
    if not isinstance(report, GitStatsReport) or not _SHA.fullmatch(report.head_sha):
        raise ValueError("Invalid GitStatsReport")
    start, end = _utc(report.window_start), _utc(report.window_end)
    if end - start != timedelta(days=90) or report.bugfix_rule_version != BUGFIX_RULE_VERSION:
        raise ValueError("Invalid statistics window or classifier version")
    seen = set()
    for item in report.files:
        if (not isinstance(item.path, str) or not item.path or "\0" in item.path
                or item.path.startswith("/") or any(p in {"", ".", ".."} for p in item.path.split("/"))
                or item.path in seen):
            raise ValueError("Invalid or duplicate statistics path")
        seen.add(item.path)
        for value in (item.commit_count_90d, item.distinct_authors_90d, item.bugfix_commit_count_90d):
            if type(value) is not int or value < 0:
                raise ValueError("Statistics counts must be non-negative integers")
        count = item.commit_count_90d
        if item.distinct_authors_90d > count or item.bugfix_commit_count_90d > count:
            raise ValueError("Statistics counts are inconsistent")
        expected = item.bugfix_commit_count_90d / count if count else 0.0
        if (isinstance(item.bugfix_frequency_90d, bool)
                or not isinstance(item.bugfix_frequency_90d, (int, float))
                or not math.isfinite(item.bugfix_frequency_90d)
                or not math.isclose(item.bugfix_frequency_90d, expected, abs_tol=1e-12)):
            raise ValueError("Invalid bugfix frequency")
        if count and (not item.distinct_authors_90d or item.last_modified_at is None):
            raise ValueError("Nonzero commits require author and modification evidence")
        if item.last_modified_at is not None:
            latest = _utc(item.last_modified_at)
            if latest > end:
                raise ValueError("Modification timestamp is after window end")
            if bool(count) != (latest >= start):
                raise ValueError("Modification timestamp contradicts the rolling commit count")


def persist_git_stats(session, repository_id, report):
    """Replace this repository's current metrics atomically; caller owns commit.

    Rows are keyed by repository/path, not file IDs, so incremental graph file
    replacement does not leave foreign-key blockers or stale path attachments.
    All tracked blob paths are included, whether or not symbol parsing supports
    them. Previous measurement windows are replaced, not retained as snapshots.
    """
    from sqlalchemy import delete, select
    from reposcope.models.git_stat import GitStat
    from reposcope.models.repository import Repository
    if type(repository_id) is not int or repository_id < 1:
        raise ValueError("repository_id must be a positive integer")
    _validate_report(report)
    with session.begin_nested():
        repository = session.scalar(select(Repository).where(
            Repository.id == repository_id).with_for_update())
        if repository is None:
            raise ValueError("Repository does not exist")
        session.execute(delete(GitStat).where(GitStat.repository_id == repository_id))
        session.add_all([GitStat(
            repository_id=repository_id, path=item.path,
            commit_count_90d=item.commit_count_90d,
            distinct_authors_90d=item.distinct_authors_90d,
            last_modified_at=item.last_modified_at,
            bugfix_commit_count_90d=item.bugfix_commit_count_90d,
            bugfix_frequency_90d=item.bugfix_frequency_90d,
            window_start=report.window_start, window_end=report.window_end,
            head_sha=report.head_sha, bugfix_rule_version=report.bugfix_rule_version,
        ) for item in report.files])
        session.flush()
    return len(report.files)


def extract_and_persist_git_stats(session, repository_id, repository_path, **options):
    report = collect_git_stats(repository_path, **options)
    persist_git_stats(session, repository_id, report)
    return report
