import asyncio
from types import SimpleNamespace
import pytest
from reposcope.recommendations.rationale import (RationaleFacts,RationaleGenerator,
    CORE,default_template,required_features,deterministic_rationale,validate_plan)
from reposcope.integrations.llm import LLMUnavailable


def facts(category='UNTESTED_HOTSPOT',metric=True):
    values=dict(impact=5,likelihood=.8,effort=2,confidence=.95,category_multiplier=1,score=1.9)
    key={'UNTESTED_HOTSPOT':'measured_fan_in','COMPLEXITY_HOTSPOT':'measured_complexity','API_DOC_GAP':'measured_documentation_gap'}.get(category)
    if metric and key:values[key]=1 if category=='API_DOC_GAP' else 12
    return RationaleFacts(repo_id=1,snapshot_id=2,finding_id=3,category=category,values=values)


def plan(f):
    t=default_template(f)
    return {'template':t,'citations':[{'feature':k,'value':f.values[k]} for k in required_features(t)]}


class Client:
    def __init__(self,data=None,error=None):self.data,self.error,self.request=data,error,None
    async def generate(self,request):
        self.request=request
        if self.error:raise self.error
        return SimpleNamespace(data=self.data,cached=True)


def generate(client,f=None):
    return asyncio.run(RationaleGenerator(client).generate(f or facts()))


def test_valid_plan_even_cache_hit_revalidated():
    f=facts();client=Client(plan(f));r=generate(client,f)
    assert r.source=='llm_constrained' and '[measured_fan_in=12.0]' in r.text
    assert 'snapshot=2' in client.request.cache_scope
    assert client.request.evidence['finding_id']==3


@pytest.mark.parametrize('category',['UNTESTED_HOTSPOT','COMPLEXITY_HOTSPOT','API_DOC_GAP','CUSTOM'])
def test_deterministic_templates(category):
    r=deterministic_rationale(facts(category))
    assert r.source=='deterministic'
    for c in r.citations:assert f'[{c.feature}={c.value}]' in r.text


def test_unavailable_uses_safe_fallback():
    r=generate(Client(error=LLMUnavailable('secret provider error')))
    assert r.source=='deterministic' and 'secret' not in r.text


def test_not_configured_is_explicit():
    assert generate(None).degraded_reason=='LLM_NOT_CONFIGURED'


@pytest.mark.parametrize('mutation',['wrong_number','unknown_feature','extra_prose','missing_citation','duplicate','unsupported_template'])
def test_invalid_output_falls_back(mutation):
    f=facts();p=plan(f)
    if mutation=='wrong_number':p['citations'][0]['value']=999
    if mutation=='unknown_feature':p['citations'][0]['feature']='invented'
    if mutation=='extra_prose':p['text']='This will definitely prevent all bugs'
    if mutation=='missing_citation':p['citations'].pop()
    if mutation=='duplicate':p['citations'].append(dict(p['citations'][0]))
    if mutation=='unsupported_template':p['template']='complexity'
    assert generate(Client(p),f).source=='deterministic'


def test_priority_only_is_valid():
    f=facts();p={'template':'priority','citations':[{'feature':k,'value':f.values[k]} for k in CORE]}
    assert generate(Client(p),f).source=='llm_constrained'


def test_corrupt_computed_score_is_not_explained():
    f=facts();f.values['score']=99
    with pytest.raises(ValueError):deterministic_rationale(f)


def test_no_measured_value_no_measured_claim():
    r=deterministic_rationale(facts(metric=False))
    assert 'non-test callers' not in r.text


def test_exact_values_not_six_digit_display_rounding():
    f=facts();f.values['measured_fan_in']=1234567
    assert '1234567.0' in deterministic_rationale(f).text


def test_cross_scope_cache_keys_differ():
    f=facts();a=Client(plan(f));generate(a,f)
    other=f.model_copy(update={'snapshot_id':4});b=Client(plan(other));generate(b,other)
    assert a.request.cache_scope!=b.request.cache_scope
