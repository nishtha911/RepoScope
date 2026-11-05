"""Git-stat persistence/migration tests use disposable SQLite, never app DB."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

from reposcope.models.base import Base
from reposcope.models.repository import Repository
from reposcope.models.git_stat import GitStat
from reposcope.ingestion.gitstats import FileGitStats, GitStatsReport, persist_git_stats

NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def connect(connection, record):
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")
    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()
    engine.dispose()


def repository(db, name="repo"):
    row = Repository(full_name=name, remote_url="https://example.invalid/" + name)
    db.add(row); db.flush()
    return row.id


def report(path="a.py", count=2):
    row = FileGitStats(path, count, 1, NOW - timedelta(days=1), 1, 1/count)
    return GitStatsReport("a" * 40, NOW - timedelta(days=90), NOW, (row,))


def rows(db, repo_id):
    return list(db.scalars(select(GitStat).where(GitStat.repository_id == repo_id)).all())


def test_persists_all_metrics_and_provenance(db):
    repo_id = repository(db)
    assert persist_git_stats(db, repo_id, report()) == 1
    row = rows(db, repo_id)[0]
    assert row.path == "a.py"
    assert row.commit_count_90d == 2
    assert row.distinct_authors_90d == 1
    assert row.bugfix_commit_count_90d == 1
    assert row.bugfix_frequency_90d == 0.5
    assert row.head_sha == "a" * 40
    assert row.bugfix_rule_version == "subject-keywords-v1"
    assert row.last_modified_at.replace(tzinfo=timezone.utc) == NOW - timedelta(days=1)
    assert row.computed_at is not None


def test_rerun_replaces_instead_of_duplicating(db):
    repo_id = repository(db)
    persist_git_stats(db, repo_id, report())
    persist_git_stats(db, repo_id, report(count=4))
    assert len(rows(db, repo_id)) == 1
    assert rows(db, repo_id)[0].commit_count_90d == 4


def test_removes_stale_paths_and_keeps_other_repository(db):
    first, second = repository(db, "first"), repository(db, "second")
    persist_git_stats(db, first, report())
    persist_git_stats(db, second, report())
    persist_git_stats(db, first, report("new.py"))
    assert [r.path for r in rows(db, first)] == ["new.py"]
    assert [r.path for r in rows(db, second)] == ["a.py"]


def test_empty_tree_clears_current_measurement(db):
    repo_id = repository(db)
    persist_git_stats(db, repo_id, report())
    persist_git_stats(db, repo_id, replace(report(), files=()))
    assert rows(db, repo_id) == []


def test_missing_repository_rejected(db):
    with pytest.raises(ValueError, match="does not exist"):
        persist_git_stats(db, 999, report())


def test_invalid_report_preserves_existing_rows(db):
    repo_id = repository(db)
    persist_git_stats(db, repo_id, report())
    bad = replace(report(), files=(replace(report().files[0], bugfix_frequency_90d=0.9),))
    with pytest.raises(ValueError, match="frequency"):
        persist_git_stats(db, repo_id, bad)
    assert rows(db, repo_id)[0].bugfix_frequency_90d == 0.5


def test_duplicate_paths_rejected(db):
    repo_id = repository(db)
    bad = replace(report(), files=report().files * 2)
    with pytest.raises(ValueError, match="duplicate"):
        persist_git_stats(db, repo_id, bad)
    assert not rows(db, repo_id)


def test_caller_rollback_undoes_replacement(db):
    repo_id = repository(db)
    persist_git_stats(db, repo_id, report())
    db.commit()
    persist_git_stats(db, repo_id, report("new.py"))
    db.rollback()
    assert [r.path for r in rows(db, repo_id)] == ["a.py"]


def test_failure_after_delete_rolls_back_savepoint(db):
    repo_id = repository(db)
    persist_git_stats(db, repo_id, report())
    def fail(*args, **kwargs):
        raise RuntimeError("injected insert failure")
    event.listen(GitStat, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            persist_git_stats(db, repo_id, report("new.py"))
    finally:
        event.remove(GitStat, "before_insert", fail)
    assert [r.path for r in rows(db, repo_id)] == ["a.py"]


@pytest.mark.parametrize("value", [0, -1, True])
def test_invalid_repository_id(db, value):
    with pytest.raises(ValueError, match="positive integer"):
        persist_git_stats(db, value, report())


def test_migration_upgrade_downgrade_and_model_columns():
    path = Path(__file__).resolve().parents[2] / "migrations/versions/e10a90c7d201_add_git_stats.py"
    spec = importlib.util.spec_from_file_location("day10_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE repositories (id INTEGER PRIMARY KEY)")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            actual = {c["name"] for c in inspect(connection).get_columns("git_stats")}
            assert actual == {c.name for c in GitStat.__table__.columns}
            assert module.down_revision == "d5e2a6b7c801"
            module.downgrade()
            assert "git_stats" not in inspect(connection).get_table_names()
    engine.dispose()
