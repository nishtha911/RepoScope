"""Execute real loader queries with SQLAlchemy/SQLite; not a PostgreSQL substitute."""
import pytest
sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from reposcope.impact.blast_radius import load_snapshot_graph, analyze_snapshot_blast_radius
from reposcope.graph.traversal_types import TraversalBudgetExceeded


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for sql in [
            "CREATE TABLE repository_snapshots(id INTEGER PRIMARY KEY, repository_id INTEGER, status TEXT, commit_sha TEXT)",
            "CREATE TABLE files(id INTEGER PRIMARY KEY, repository_id INTEGER, snapshot_id INTEGER, path TEXT)",
            "CREATE TABLE symbols(id INTEGER PRIMARY KEY, file_id INTEGER, name TEXT, qualname TEXT, kind TEXT, start_line INTEGER, end_line INTEGER)",
            "CREATE TABLE edges(id INTEGER PRIMARY KEY, source_symbol_id INTEGER, target_symbol_id INTEGER, kind TEXT, confidence REAL)",
            "INSERT INTO repository_snapshots VALUES(10,1,'ready','abc'),(11,1,'ready','def'),(20,2,'ready','ghi'),(30,1,'indexing','jkl')",
            "INSERT INTO files VALUES(1,1,10,'app.py'),(2,1,11,'old.py'),(3,2,20,'foreign.py'),(4,1,NULL,'legacy.py')",
            "INSERT INTO symbols VALUES(1,1,'core','core','function',1,2),(2,1,'handler','handler','function',3,4),(3,1,'GET /','GET /','endpoint',3,4),(4,2,'old','old','function',1,2),(5,3,'foreign','foreign','function',1,2),(6,4,'legacy','legacy','function',1,2)",
            "INSERT INTO edges VALUES(1,2,1,'CALLS',1),(2,3,2,'CALLS',1),(3,4,1,'CALLS',1),(4,5,1,'CALLS',1),(5,6,1,'CALLS',1)",
        ]:
            conn.execute(text(sql))
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_loader_scopes_nodes_and_both_edge_ends(db):
    g = load_snapshot_graph(db,1,10)
    assert sorted(g) == [1,2,3]
    assert sorted(d['edge_id'] for *_,d in g.edges(data=True)) == [1,2]


def test_live_loader_to_bfs(db):
    r = analyze_snapshot_blast_radius(db,1,10,[1])
    assert [h.symbol_id for h in r.hits] == [1,2,3]
    assert r.affected_endpoint_ids == (3,)
    assert r.affected_file_ids == (1,)
    assert db.scalar(text('SELECT count(*) FROM symbols')) == 6


@pytest.mark.parametrize('repo,snap',[(2,10),(1,999),(1,30)])
def test_wrong_or_unready_snapshot(db,repo,snap):
    with pytest.raises(ValueError):
        load_snapshot_graph(db,repo,snap)


@pytest.mark.parametrize('options',[{'max_nodes':1},{'max_edges':1}])
def test_load_budgets(db,options):
    with pytest.raises(TraversalBudgetExceeded):
        load_snapshot_graph(db,1,10,**options)


def test_model_ids_verified_and_not_guessed(db):
    assert load_snapshot_graph(db,1,10,database_model_ids=[1]).nodes[1]['is_database_model']
    with pytest.raises(ValueError):
        load_snapshot_graph(db,1,10,database_model_ids=[5])


def test_foreign_seed_rejected_after_load(db):
    with pytest.raises(ValueError):
        analyze_snapshot_blast_radius(db,1,10,[4])
