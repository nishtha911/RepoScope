"""Day 9: disposable SQLite only; no application database URL is used."""
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from reposcope.models.base import Base
from reposcope.models.repository import Repository
from reposcope.models.file import File
from reposcope.models.symbol import Symbol
from reposcope.models.edge import Edge
from reposcope.models.chunk import Chunk
from reposcope.graph.builder import canonical_graph, build_graph_plan, persist_graph_plan, resolution_report
from reposcope.graph import incremental as inc
from reposcope.parsing.python_parser import parse_python, PythonParserError
from reposcope.parsing.reference_resolver import ReferenceResolver


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


def repository(db, name):
    repo = Repository(full_name=name, remote_url="https://example.invalid/" + name)
    db.add(repo)
    db.flush()
    return repo.id


def start(db, sources, roots=(".",)):
    return inc.initialize_incremental_graph(db, repository(db, "initial"), sources, source_roots=roots)


def assert_fresh(db, state, sources):
    reference = repository(db, "fresh")
    parsed = [parse_python(content, file_path=path) for path, content in sorted(sources.items())]
    plan = build_graph_plan(parsed, source_roots=state.source_roots)
    persist_graph_plan(db, reference, plan)
    assert canonical_graph(db, state.graph.repository_id) == canonical_graph(db, reference)
    actual_report = resolution_report(state.graph.plan)
    expected_report = resolution_report(plan)
    for report in (actual_report, expected_report):
        report["results"].sort(key=lambda r: r["reference"]["reference_key"])
    assert actual_report == expected_report


BASE = {
    "service.py": b"def work():\n    return 1\n",
    "client.py": b"from service import work\ndef run():\n    return work()\n",
    "isolated.py": b"def isolated():\n    return 7\n",
    "test_service.py": b"from service import work\ndef test_work():\n    assert work() == 1\n",
}


CASES = [
    ({"service.py": b"def work():\n    return 22\n"}, ()),
    ({"service.py": b"def replacement():\n    return 1\n"}, ()),
    ({}, ("service.py",)),
    ({"extra.py": b"def extra():\n    return 3\n"}, ()),
    ({"renamed.py": BASE["service.py"]}, ("service.py",)),
    ({"service.py": b"class Worker:\n    def work(self):\n        return 1\n"}, ()),
    ({"client.py": b"from service import work\ndef run():\n    return 0\n"}, ()),
    ({"test_service.py": b"def test_work():\n    assert True\n"}, ()),
    ({"test_service.py": b"def test_other():\n    assert True\n"}, ()),
    ({}, tuple(BASE)),
]


@pytest.mark.parametrize("changes,deletions", CASES)
def test_updates_equal_fresh_build(db, changes, deletions):
    state = start(db, BASE)
    sources = {p: b for p, b in BASE.items() if p not in deletions}
    sources.update(changes)
    update = inc.update_incremental_graph(db, state, sources)
    assert_fresh(db, update.state, sources)
    if "isolated.py" in sources:
        assert update.state.graph.file_ids["isolated.py"] == state.graph.file_ids["isolated.py"]
        isolated_keys = {n.key for n in state.graph.plan.nodes if n.path == "isolated.py"}
        assert all(update.state.graph.node_ids[k] == state.graph.node_ids[k] for k in isolated_keys)


def test_only_dirty_files_parsed_and_dependents_resolved(db, monkeypatch):
    state = start(db, BASE)
    parsed_paths, resolved_paths = [], []
    real_parse, real_resolve = inc.parse_python, ReferenceResolver.resolve
    def parse(content, *, file_path):
        parsed_paths.append(file_path)
        return real_parse(content, file_path=file_path)
    def resolve(self, reference):
        resolved_paths.append(reference.site.file_path)
        return real_resolve(self, reference)
    monkeypatch.setattr(inc, "parse_python", parse)
    monkeypatch.setattr(ReferenceResolver, "resolve", resolve)
    sources = dict(BASE, **{"service.py": b"def work():\n    return 100\n"})
    update = inc.update_incremental_graph(db, state, sources)
    assert parsed_paths == ["service.py"]
    assert "isolated.py" not in update.resolved_paths
    assert set(resolved_paths) <= set(update.resolved_paths)
    assert "client.py" in resolved_paths
    assert "test_service.py" in resolved_paths


def test_noop_does_not_parse_resolve_or_write(db, monkeypatch):
    state = start(db, BASE)
    def forbidden(*args, **kwargs):
        pytest.fail("No-op invoked parser/resolver")
    monkeypatch.setattr(inc, "parse_python", forbidden)
    monkeypatch.setattr(inc, "analyze_python_files", forbidden)
    statements = []
    @event.listens_for(db.bind, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())
    update = inc.update_incremental_graph(db, state, BASE)
    assert update.state is state
    assert not update.changed_paths
    assert not {"INSERT", "UPDATE", "DELETE"} & set(statements)


def test_new_file_resolves_previously_unresolved_import(db):
    sources = {"caller.py": b"from missing import task\ndef run():\n    return task()\n"}
    state = start(db, sources)
    sources["missing.py"] = b"def task():\n    return 1\n"
    update = inc.update_incremental_graph(db, state, sources)
    assert "caller.py" in update.resolved_paths
    assert any(e.kind == "CALLS" for e in update.state.graph.plan.edges)
    assert_fresh(db, update.state, sources)


def test_transitive_reexport_dependency(db):
    sources = {
        "leaf.py": b"def task():\n    return 1\n",
        "bridge.py": b"from leaf import task\n",
        "caller.py": b"from bridge import task\ndef run():\n    return task()\n",
    }
    state = start(db, sources)
    sources["leaf.py"] = b"def other():\n    return 1\n"
    update = inc.update_incremental_graph(db, state, sources)
    assert set(sources) <= set(update.resolved_paths)
    assert_fresh(db, update.state, sources)


def test_relative_import_and_package_init(db):
    sources = {
        "pkg/__init__.py": b"from .leaf import task\n",
        "pkg/leaf.py": b"def task():\n    return 1\n",
        "pkg/caller.py": b"from . import task\ndef run():\n    return task()\n",
    }
    state = start(db, sources)
    sources["pkg/leaf.py"] = b"def renamed():\n    return 1\n"
    update = inc.update_incremental_graph(db, state, sources)
    assert "pkg/caller.py" in update.resolved_paths
    assert_fresh(db, update.state, sources)


def test_source_roots(db):
    sources = {"src/a.py": b"def task():\n    return 1\n", "src/b.py": b"from a import task\ntask()\n"}
    state = start(db, sources, ("src",))
    sources["src/a.py"] = b"def task():\n    return 2\n"
    update = inc.update_incremental_graph(db, state, sources)
    assert_fresh(db, update.state, sources)


def test_naming_fallback_recomputed_globally(db):
    sources = {"service.py": b"def work():\n    pass\n", "test_service.py": b"def test_work():\n    pass\n"}
    state = start(db, sources)
    sources["duplicate.py"] = b"def work():\n    pass\n"
    update = inc.update_incremental_graph(db, state, sources)
    assert_fresh(db, update.state, sources)


def test_routes_changed(db):
    sources = {"app.py": b'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/old")\ndef view():\n    return 1\n'}
    state = start(db, sources)
    sources["app.py"] = sources["app.py"].replace(b"/old", b"/new")
    update = inc.update_incremental_graph(db, state, sources)
    assert_fresh(db, update.state, sources)


def test_model_base_changed(db):
    sources = {
        "base.py": b"from sqlalchemy.orm import DeclarativeBase\nclass Base(DeclarativeBase):\n    pass\n",
        "models.py": b'from base import Base\nclass Item(Base):\n    __tablename__ = "items"\n',
        "caller.py": b"from models import Item\ndef make():\n    return Item()\n",
    }
    state = start(db, sources)
    sources["base.py"] = b"class Base:\n    pass\n"
    update = inc.update_incremental_graph(db, state, sources)
    assert_fresh(db, update.state, sources)


def test_chunks_invalidated_only_for_dirty_symbols(db):
    state = start(db, BASE)
    ids = {n.path: state.graph.node_ids[n.key] for n in state.graph.plan.nodes if n.kind == "function"}
    dirty = Chunk(symbol_id=ids["service.py"], repo_id=state.graph.repository_id, text="old")
    kept = Chunk(symbol_id=ids["isolated.py"], repo_id=state.graph.repository_id, text="keep")
    db.add_all([dirty, kept]); db.flush()
    dirty_id, kept_id = dirty.id, kept.id
    update = inc.update_incremental_graph(db, state, dict(BASE, **{"service.py": b"def work():\n    return 4\n"}))
    assert update.invalidated_chunk_ids == (dirty_id,)
    assert list(db.scalars(select(Chunk.id))) == [kept_id]


def test_repository_isolation(db):
    state = start(db, BASE)
    other = inc.initialize_incremental_graph(db, repository(db, "other"), BASE)
    expected = canonical_graph(db, other.graph.repository_id)
    inc.update_incremental_graph(db, state, {})
    assert canonical_graph(db, other.graph.repository_id) == expected


def test_parser_failure_preserves_baseline(db):
    state = start(db, BASE)
    expected = canonical_graph(db, state.graph.repository_id)
    with pytest.raises(PythonParserError):
        inc.update_incremental_graph(db, state, dict(BASE, **{"service.py": b"def broken(:\n"}))
    assert canonical_graph(db, state.graph.repository_id) == expected
    assert_fresh(db, inc.update_incremental_graph(db, state, BASE).state, BASE)


def test_savepoint_rolls_back_mid_write_failure(db, monkeypatch):
    state = start(db, BASE)
    expected = canonical_graph(db, state.graph.repository_id)
    original = inc._state
    def fail(*args, **kwargs):
        raise RuntimeError("injected failure")
    monkeypatch.setattr(inc, "_state", fail)
    with pytest.raises(RuntimeError, match="injected"):
        inc.update_incremental_graph(db, state, {})
    assert canonical_graph(db, state.graph.repository_id) == expected
    monkeypatch.setattr(inc, "_state", original)
    assert inc.update_incremental_graph(db, state, BASE).state is state


def test_caller_rollback_undoes_update(db):
    state = start(db, BASE)
    db.commit()
    expected = canonical_graph(db, state.graph.repository_id)
    inc.update_incremental_graph(db, state, {})
    db.rollback()
    assert canonical_graph(db, state.graph.repository_id) == expected
    assert inc.update_incremental_graph(db, state, BASE).state is state


def test_successive_updates(db):
    state = start(db, BASE)
    sources = dict(BASE)
    sources["service.py"] = b"def work():\n    return 3\n"
    state = inc.update_incremental_graph(db, state, sources).state
    sources.pop("client.py")
    state = inc.update_incremental_graph(db, state, sources).state
    assert_fresh(db, state, sources)


def test_stale_graph_rejected(db):
    state = start(db, BASE)
    symbol = db.get(Symbol, next(iter(state.graph.node_ids.values())))
    symbol.name = "externally_changed"
    db.flush()
    with pytest.raises(ValueError, match="Stale baseline"):
        inc.update_incremental_graph(db, state, {})


@pytest.mark.parametrize("path", ["../x.py", "/x.py", "a\\b.py", "a//x.py", "x.txt", "C:/x.py"])
def test_invalid_paths_rejected(db, path):
    with pytest.raises(ValueError, match="POSIX"):
        start(db, {path: b"pass\n"})


def test_text_source_rejected(db):
    with pytest.raises(TypeError, match="bytes"):
        start(db, {"x.py": "pass\n"})


def test_attach_existing_fresh_graph(db):
    parsed = [parse_python(b, file_path=p) for p, b in sorted(BASE.items())]
    graph = persist_graph_plan(db, repository(db, "existing"), build_graph_plan(parsed))
    state = inc.attach_incremental_state(parsed, graph)
    assert inc.update_incremental_graph(db, state, BASE).state is state


def test_snapshot_owned_graph_rejected(db):
    from reposcope.models.repository_snapshot import RepositorySnapshot
    state = start(db, BASE)
    snapshot = RepositorySnapshot(repository_id=state.graph.repository_id, commit_sha="a" * 40)
    db.add(snapshot); db.flush()
    file = db.get(File, state.graph.file_ids["service.py"])
    file.snapshot_id = snapshot.id
    db.flush()
    with pytest.raises(ValueError, match="Snapshot-owned"):
        inc.update_incremental_graph(db, state, {})


def test_cross_repository_edge_rejected(db):
    state = start(db, BASE)
    other = inc.initialize_incremental_graph(db, repository(db, "other"), BASE)
    db.add(Edge(source_symbol_id=next(iter(state.graph.node_ids.values())),
                target_symbol_id=next(iter(other.graph.node_ids.values())), kind="CALLS", confidence=1.0))
    db.flush()
    with pytest.raises(ValueError, match="Cross-repository"):
        inc.update_incremental_graph(db, state, {})


def test_deleted_file_chunks_removed(db):
    state = start(db, BASE)
    node = next(n for n in state.graph.plan.nodes if n.path == "service.py" and n.kind == "function")
    chunk = Chunk(symbol_id=state.graph.node_ids[node.key], repo_id=state.graph.repository_id, text="old")
    db.add(chunk); db.flush()
    chunk_id = chunk.id
    sources = {p: b for p, b in BASE.items() if p != "service.py"}
    update = inc.update_incremental_graph(db, state, sources)
    assert chunk_id in update.invalidated_chunk_ids
    assert db.scalar(select(Chunk.id).where(Chunk.id == chunk_id)) is None


def test_utf8_bom_and_unicode(db):
    sources = {"unicode.py": b"\xef\xbb\xbf" + "def café():\n    return 'é'\n".encode()}
    state = start(db, sources)
    sources["unicode.py"] = "def café():\n    return 'à'\n".encode()
    update = inc.update_incremental_graph(db, state, sources)
    assert update.modified == ("unicode.py",)
    assert_fresh(db, update.state, sources)
