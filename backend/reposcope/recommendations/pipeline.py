"""Explicit publish/read lifecycle. GET reads publications; never fabricates rows."""
import hashlib
import json
from dataclasses import dataclass
from sqlalchemy import select
from reposcope.models.repository import Repository
from reposcope.models.repository_snapshot import RepositorySnapshot
from reposcope.models.symbol import Symbol as SymbolRow
from reposcope.models.file import File
from reposcope.models.recommendation import RecommendationRun,RecommendationRecord
from reposcope.recommendations.detectors import CandidateDataset,detect_candidates,DetectorConfig
from reposcope.recommendations.scorer import HeuristicScorer,ScorerConfig
from reposcope.recommendations.rationale import RationaleFacts,validate_facts


class RecommendationNotFound(ValueError):pass
class RecommendationsNotReady(ValueError):pass


def publish_recommendations(session,dataset,*,detector_config=None,scorer_config=None):
    """Validate ownership, detect, score and persist; flush only, caller commits.

    Supply fully loaded same-snapshot edges and verified parser metadata.
    This does not complete the previously deferred source-enrichment pipeline.
    """
    if session.get_bind().dialect.name=='postgresql':
        if session.connection().get_isolation_level() not in ('REPEATABLE READ','SERIALIZABLE'):
            raise ValueError('Publish within a REPEATABLE READ or SERIALIZABLE transaction')
    dataset=CandidateDataset.model_validate(dataset.model_dump())
    dc=DetectorConfig.model_validate((detector_config or DetectorConfig()).model_dump())
    sc=ScorerConfig.model_validate((scorer_config or ScorerConfig()).model_dump())
    snapshot=session.get(RepositorySnapshot,dataset.snapshot_id)
    if snapshot is None or snapshot.repository_id!=dataset.repo_id or snapshot.status!='ready':
        raise RecommendationsNotReady('A ready repository-owned snapshot is required')
    rows=session.execute(select(SymbolRow,File).join(File,File.id==SymbolRow.file_id)
        .where(File.repository_id==dataset.repo_id,File.snapshot_id==dataset.snapshot_id)).all()
    owned={sym.id:(sym,file) for sym,file in rows}
    if set(owned)!={row.symbol.id for row in dataset.symbols}:
        raise ValueError('Dataset must contain the complete selected snapshot symbol inventory')
    for row in dataset.symbols:
        sym,file=owned[row.symbol.id]
        actual=(sym.file_id,sym.name,sym.qualname,sym.kind,sym.start_line,sym.end_line,file.path)
        claimed=(row.symbol.file_id,row.symbol.name,row.symbol.qualname,row.symbol.kind,
                 row.symbol.start_line,row.symbol.end_line,row.filepath)
        if actual!=claimed:raise ValueError('Dataset symbol identity disagrees with stored snapshot')
    from reposcope.models.edge import Edge as EdgeRow
    source_ids=set(owned)
    actual_edges=session.scalars(select(EdgeRow).where(EdgeRow.source_symbol_id.in_(source_ids),
        EdgeRow.target_symbol_id.in_(source_ids))).all() if source_ids else []
    expected={(e.source_symbol_id,e.target_symbol_id,e.kind,e.confidence) for e in actual_edges}
    claimed={(e.source_symbol_id,e.target_symbol_id,e.kind,e.confidence) for e in dataset.edges}
    if claimed!=expected:raise ValueError('Dataset must contain all stored internal snapshot edges')
    report=detect_candidates(dataset,dc)
    ranked=HeuristicScorer(sc).score_report(report,dataset)
    blob=json.dumps({'policy':'recommendations-v1','dataset':dataset.model_dump(mode='json'),
        'detector':dc.model_dump(mode='json'),'scorer':sc.model_dump(mode='json')},sort_keys=True,allow_nan=False)
    digest=hashlib.sha256(blob.encode()).hexdigest()
    existing=session.scalar(select(RecommendationRun).where(RecommendationRun.repo_id==dataset.repo_id,
        RecommendationRun.snapshot_id==dataset.snapshot_id,RecommendationRun.digest==digest))
    if existing:return existing.id
    run=RecommendationRun(repo_id=dataset.repo_id,snapshot_id=dataset.snapshot_id,digest=digest,
        gaps=[g.model_dump(mode='json') for g in ranked.gaps])
    session.add(run);session.flush()
    evidence={(e.category,e.symbol_id):e for e in report.evidence}
    for rank,(finding,features) in enumerate(zip(ranked.findings,ranked.features),1):
        ev=evidence.get((finding.category,finding.symbol_id))
        if ev is None:raise ValueError('Finding has no matched detector evidence')
        values={'impact':features.impact,'likelihood':features.likelihood,
            'effort':max(sc.min_effort,features.effort),'confidence':features.confidence,
            'category_multiplier':sc.category_multipliers.get(finding.category,1.0),'score':finding.score}
        if finding.category=='UNTESTED_HOTSPOT' and ev.measured_value is not None:
            values['measured_fan_in']=ev.measured_value
        elif finding.category=='COMPLEXITY_HOTSPOT' and ev.measured_value is not None:
            values['measured_complexity']=ev.measured_value
        elif finding.category=='API_DOC_GAP':values['measured_documentation_gap']=1
        validate_facts(RationaleFacts(repo_id=dataset.repo_id,snapshot_id=dataset.snapshot_id,
            finding_id=1,category=finding.category,values=values,round_digits=sc.round_digits))
        session.add(RecommendationRecord(run_id=run.id,rank=rank,
            finding=finding.model_dump(mode='json'),features=features.model_dump(mode='json'),
            facts=values,evidence=ev.model_dump(mode='json'),round_digits=sc.round_digits))
    session.flush()
    return run.id


@dataclass(frozen=True)
class PublishedRecommendations:
    repo_id:int
    snapshot_id:int
    commit_sha:str
    run_id:int
    gaps:tuple[dict,...]
    items:tuple[dict,...]


def read_recommendations(session,repo_id,*,snapshot_id=None,k=10):
    if type(repo_id) is not int or repo_id<1 or type(k) is not int or not 1<=k<=100:
        raise ValueError('Invalid repository or limit')
    if session.get(Repository,repo_id) is None:raise RecommendationNotFound('Repository not found')
    if snapshot_id is None:
        snapshot=session.scalar(select(RepositorySnapshot).where(RepositorySnapshot.repository_id==repo_id,
            RepositorySnapshot.status=='ready').order_by(RepositorySnapshot.id.desc()).limit(1))
    else:
        if type(snapshot_id) is not int or snapshot_id<1:raise ValueError('Invalid snapshot')
        snapshot=session.get(RepositorySnapshot,snapshot_id)
        if snapshot is None or snapshot.repository_id!=repo_id:raise RecommendationNotFound('Snapshot not found')
    if snapshot is None or snapshot.status!='ready':raise RecommendationsNotReady('No ready snapshot')
    run=session.scalar(select(RecommendationRun).where(RecommendationRun.repo_id==repo_id,
        RecommendationRun.snapshot_id==snapshot.id).order_by(RecommendationRun.id.desc()).limit(1))
    if run is None:raise RecommendationsNotReady('Recommendations have not been published for this snapshot')
    records=session.scalars(select(RecommendationRecord).where(RecommendationRecord.run_id==run.id)
        .order_by(RecommendationRecord.rank).limit(k)).all()
    items=[]
    for row in records:
        if row.finding.get('snapshot_id')!=snapshot.id:raise ValueError('Corrupt stored finding scope')
        sid=row.finding.get('symbol_id')
        if sid is not None:
            owner=session.execute(select(SymbolRow.file_id).join(File,File.id==SymbolRow.file_id)
                .where(SymbolRow.id==sid,File.repository_id==repo_id,File.snapshot_id==snapshot.id)).scalar_one_or_none()
            if owner is None or owner!=row.finding.get('file_id'):
                raise RecommendationsNotReady('Published finding references a stale symbol; republish this snapshot')
        facts=validate_facts(RationaleFacts(repo_id=repo_id,snapshot_id=snapshot.id,finding_id=row.id,
            category=row.finding['category'],values=row.facts,round_digits=row.round_digits))
        if row.finding.get('score')!=facts.values['score']:raise ValueError('Corrupt stored priority')
        items.append({'id':row.id,'finding':dict(row.finding),'features':dict(row.features),
                      'evidence':dict(row.evidence),'facts':facts})
    return PublishedRecommendations(repo_id,snapshot.id,snapshot.commit_sha,run.id,
        tuple(run.gaps),tuple(items))
