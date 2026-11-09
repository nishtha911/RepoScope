"""Real SQLAlchemy/SQLite publication and read integration; no external DB or LLM."""
import pytest
pytest.importorskip('sqlalchemy')
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from reposcope.models.repository import Repository
from reposcope.models.repository_snapshot import RepositorySnapshot
from reposcope.models.file import File
from reposcope.models.symbol import Symbol as SymbolRow
from reposcope.models.edge import Edge as EdgeRow
from reposcope.models.recommendation import RecommendationRun,RecommendationRecord
from reposcope.contracts.symbol import Symbol
from reposcope.contracts.edge import Edge
from reposcope.recommendations.detectors import CandidateDataset,CandidateSymbol
from reposcope.recommendations.scorer import ScorerConfig
from reposcope.recommendations.pipeline import (publish_recommendations,read_recommendations,
    RecommendationNotFound,RecommendationsNotReady)


@pytest.fixture
def db():
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    with engine.begin() as conn:
        for model in [Repository,RepositorySnapshot,File,SymbolRow,EdgeRow,RecommendationRun,RecommendationRecord]:
            model.__table__.create(conn)
    with Session(engine) as session:
        session.add_all([Repository(id=1,full_name='owner/repo',remote_url='https://github.com/owner/repo'),
            Repository(id=2,full_name='owner/other',remote_url='https://github.com/owner/other')]);session.flush()
        session.add(RepositorySnapshot(id=1,repository_id=1,commit_sha='a'*40,status='ready',error_message=None,indexed_at=None));session.flush()
        session.add(File(id=1,repository_id=1,snapshot_id=1,path='app.py',language='python'));session.flush()
        for i in range(1,8):
            session.add(SymbolRow(id=i,file_id=1,name=f's{i}',qualname=f's{i}',
                kind='endpoint' if i==7 else 'function',start_line=i,end_line=i))
        session.flush()
        for i in range(2,8):session.add(EdgeRow(id=i,source_symbol_id=i,target_symbol_id=1,kind='CALLS',confidence=1))
        session.commit()
        yield session
    engine.dispose()


def dataset():
    rows=[CandidateSymbol(symbol=Symbol(id=i,file_id=1,name=f's{i}',qualname=f's{i}',
        kind='endpoint' if i==7 else 'function',start_line=i,end_line=i),
        filepath='app.py',is_test=False,cyclomatic_complexity=15 if i==1 else 1,
        complexity_policy='fixture_v1',documentation_known=True) for i in range(1,8)]
    edges=[Edge(id=i,source_symbol_id=i,target_symbol_id=1,kind='CALLS',confidence=1) for i in range(2,8)]
    return CandidateDataset(repo_id=1,snapshot_id=1,symbols=tuple(rows),edges=tuple(edges),test_links_complete=True)


def publish(db,**kw):
    rid=publish_recommendations(db,dataset(),**kw);db.commit();return rid


def test_detect_score_persist_read(db):
    rid=publish(db);r=read_recommendations(db,1)
    assert r.run_id==rid and r.snapshot_id==1 and r.commit_sha=='a'*40
    assert len(r.items)==3
    assert {x['finding']['category'] for x in r.items}=={'UNTESTED_HOTSPOT','COMPLEXITY_HOTSPOT','API_DOC_GAP'}
    scores=[x['finding']['score'] for x in r.items]
    assert scores==sorted(scores,reverse=True)
    assert all(x['id']>0 for x in r.items)


def test_idempotent_publication_retains_ids(db):
    a=publish(db);ids=[x['id'] for x in read_recommendations(db,1).items]
    b=publish(db)
    assert a==b and ids==[x['id'] for x in read_recommendations(db,1).items]
    assert db.scalar(select(func.count()).select_from(RecommendationRun))==1


def test_applied_effort_and_multiplier_are_preserved(db):
    publish(db,scorer_config=ScorerConfig(min_effort=100,category_multipliers={'UNTESTED_HOTSPOT':1.5}))
    r=read_recommendations(db,1)
    f=next(x['facts'] for x in r.items if x['finding']['category']=='UNTESTED_HOTSPOT')
    assert f.values['effort']==100 and f.values['category_multiplier']==1.5


def test_repository_not_found(db):
    with pytest.raises(RecommendationNotFound):read_recommendations(db,999)


def test_missing_publication_is_not_fake_empty_success(db):
    with pytest.raises(RecommendationsNotReady):read_recommendations(db,1)


def test_cross_repo_snapshot_rejected(db):
    publish(db)
    with pytest.raises(RecommendationNotFound):read_recommendations(db,2,snapshot_id=1)


def test_read_limit(db):
    publish(db);assert len(read_recommendations(db,1,k=1).items)==1


def test_foreign_dataset_rejected(db):
    with pytest.raises(RecommendationsNotReady):publish_recommendations(db,dataset().model_copy(update={'repo_id':2}))


def test_partial_inventory_rejected(db):
    d=dataset()
    with pytest.raises(ValueError):publish_recommendations(db,d.model_copy(update={'symbols':d.symbols[:-1],'edges':d.edges[:-1]}))


def test_missing_edges_rejected(db):
    with pytest.raises(ValueError):publish_recommendations(db,dataset().model_copy(update={'edges':()}))


def test_unpublished_latest_snapshot_does_not_reuse_old_results(db):
    publish(db)
    db.add(RepositorySnapshot(id=2,repository_id=1,commit_sha='b'*40,status='ready',error_message=None,indexed_at=None));db.commit()
    with pytest.raises(RecommendationsNotReady):read_recommendations(db,1)
    assert read_recommendations(db,1,snapshot_id=1).snapshot_id==1


def test_complete_empty_publication_is_legitimate(db):
    db.add(RepositorySnapshot(id=2,repository_id=1,commit_sha='b'*40,status='ready',error_message=None,indexed_at=None));db.commit()
    publish_recommendations(db,CandidateDataset(repo_id=1,snapshot_id=2));db.commit()
    assert read_recommendations(db,1).items==()


def test_corrupt_priority_not_explained(db):
    publish(db)
    row=db.scalar(select(RecommendationRecord));row.facts={**row.facts,'score':999};db.commit()
    with pytest.raises(ValueError):read_recommendations(db,1)


def test_publisher_leaves_commit_to_caller(db):
    publish_recommendations(db,dataset());db.rollback()
    assert db.scalar(select(func.count()).select_from(RecommendationRun))==0
