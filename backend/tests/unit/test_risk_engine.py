"""Integration with real Day 11 contracts and Day 12 traversal (no DB required)."""
import networkx as nx
import pytest
from reposcope.contracts.diff import (SymbolVersion,SymbolChange,SymbolDiffReport,
    DiffPatch,FileDiff,DiffHunk,DiffLine,MappingGap)
from reposcope.impact.blast_radius import blast_radius
from reposcope.impact.risk_engine import RiskSnapshot,assess_pr_risk


def version(key):
    return SymbolVersion(path='app.py',local_key=key,name='f',qualname='f',kind='function',
        start_line=1,end_line=2,content_start_line=1,content_end_line=2)


def report(classification='BODY_CHANGED',gap=False):
    before=None if classification=='ADDED' else version('old')
    after=None if classification=='REMOVED' else version('new')
    file=FileDiff(base_path='app.py',head_path='app.py',status='MODIFIED',hunks=(
        DiffHunk(base_start=2,base_count=1,head_start=2,head_count=1,lines=(
            DiffLine(kind='-',text=' return 1\n',base_line=2),
            DiffLine(kind='+',text=' return 2\n',head_line=2))),))
    return SymbolDiffReport(patch=DiffPatch(files=(file,)),
        changes=(SymbolChange(classification=classification,base_symbol=before,head_symbol=after),),
        base_revision='a'*40,head_revision='b'*40,
        gaps=(MappingGap(code='MISSING_SOURCE',path='x.py',detail='fixture gap'),) if gap else ())


def context(side,linked=False,sensitive=False):
    snap=10 if side=='base' else 20
    # Deliberately reuse ID 1 across snapshots: never union persisted IDs.
    g=nx.MultiDiGraph(repository_id=1,snapshot_id=snap,commit_sha=('a' if side=='base' else 'b')*40)
    g.add_node(1,repository_id=1,snapshot_id=snap,file_id=1,file_path='app.py',
        name='f',qualname='f',kind='function',start_line=1,end_line=2)
    g.add_node(2,repository_id=1,snapshot_id=snap,file_id=2,file_path='test_app.py',
        name='test_f',qualname='test_f',kind='function',start_line=1,end_line=2)
    if linked:g.add_edge(1,2,key=1,edge_id=1,kind='TESTED_BY',confidence=1)
    return RiskSnapshot(g,blast_radius(g,1,snap,[1]),
        {'old' if side=='base' else 'new':1},symbol_roles={1:'production',2:'test'},
        test_links_complete=True,sensitive_symbol_ids=(1,) if sensitive else (),sensitivity_complete=True)


def assess(r=None,contexts=None,**kw):
    return assess_pr_risk(r or report(),1,
        {'base':context('base'),'head':context('head')} if contexts is None else contexts,
        base_complexities={'old':2},head_complexities={'new':4},**kw)


def test_real_diff_blast_scoring_integration():
    r=assess()
    assert r.risk.status=='COMPLETE'
    assert r.features.blast_radius==.02 and r.features.test_gap==1
    assert r.features.complexity_delta==.2 and r.features.size==.004
    assert r.features.contract_changes==0
    assert r.risk.score==pytest.approx(.2262)
    assert r.untested_modified_symbols[0].side=='head'


def test_head_test_association_wins_over_base_absence():
    r=assess(contexts={'base':context('base'),'head':context('head',linked=True)})
    assert r.features.test_gap==0 and not r.untested_modified_symbols


def test_removed_uses_base_test_gap():
    r=assess(report('REMOVED'),contexts={'base':context('base')})
    assert r.risk.status=='COMPLETE' and r.features.contract_changes==1
    assert r.maximum_complexity_increase==0
    assert r.untested_modified_symbols[0].side=='base'


def test_added_uses_head_only():
    r=assess(report('ADDED'),contexts={'head':context('head')})
    assert r.risk.status=='COMPLETE' and r.features.contract_changes==.5
    assert r.maximum_complexity_increase==4


def test_signature_classification_is_contract_proxy():
    assert assess(report('SIGNATURE_CHANGED')).features.contract_changes==1


def test_missing_snapshot_not_low_risk():
    r=assess(contexts={'head':context('head')})
    assert r.risk.score is None and 'MISSING_BASE_SNAPSHOT' in r.gaps


def test_wrong_revision_fails():
    ctx=context('head');ctx.graph.graph['commit_sha']='c'*40
    with pytest.raises(ValueError):assess(contexts={'base':context('base'),'head':ctx})


def test_mapper_gaps_keep_score_incomplete():
    r=assess(report(gap=True))
    assert r.risk.score is None and r.features.contract_changes is None


def test_missing_complexity_keeps_score_incomplete():
    r=assess_pr_risk(report(),1,{'base':context('base'),'head':context('head')})
    assert r.risk.score is None and 'complexity_delta' in r.risk.missing_features


def test_sensitive_symbol_signal():
    assert assess(contexts={'base':context('base'),'head':context('head',sensitive=True)}).features.sensitivity==1


def test_json_serializable_and_stable():
    assert assess().model_dump_json()==assess().model_dump_json()


def test_empty_patch_is_complete_zero():
    r=assess_pr_risk(SymbolDiffReport(patch=DiffPatch()),1,{})
    assert r.risk.score==0 and r.risk.risk_level=='LOW'


def test_wrong_blast_seeds_rejected():
    from dataclasses import replace
    ctx=context('head')
    bad=replace(ctx,blast_radius=replace(ctx.blast_radius,seed_symbol_ids=(2,)))
    with pytest.raises(ValueError):assess(contexts={'base':context('base'),'head':bad})


def test_unknown_test_roles_keep_score_incomplete():
    from dataclasses import replace
    ctx=replace(context('head'),symbol_roles={})
    r=assess(contexts={'base':context('base'),'head':ctx})
    assert r.features.test_gap is None and r.risk.score is None


def test_unknown_sensitivity_not_assumed_zero():
    from dataclasses import replace
    ctx=replace(context('head'),sensitivity_complete=False)
    r=assess(contexts={'base':context('base'),'head':ctx})
    assert r.features.sensitivity is None


def test_positive_complexity_delta_never_negative():
    r=assess_pr_risk(report(),1,{'base':context('base'),'head':context('head')},
        base_complexities={'old':10},head_complexities={'new':2})
    assert r.features.complexity_delta==0


def test_saturation_caps():
    from reposcope.impact.risk_score import RiskPolicy
    r=assess(policy=RiskPolicy(blast_mass_cap=.5,complexity_increase_cap=1,changed_lines_cap=1))
    assert r.features.blast_radius==1 and r.features.complexity_delta==1 and r.features.size==1


def test_depth_limited_blast_not_complete_risk():
    from dataclasses import replace
    ctx=context('head');ctx=replace(ctx,blast_radius=replace(ctx.blast_radius,depth_limited=True))
    r=assess(contexts={'base':context('base'),'head':ctx})
    assert r.features.blast_radius is None and r.risk.score is None
