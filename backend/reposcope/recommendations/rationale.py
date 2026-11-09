"""Constrained LLM rationale planning, exact citations, deterministic rendering.

The model never supplies user-visible prose. It chooses a supported template
and copies its required feature citations. Validate fresh AND cached responses.
"""
import asyncio
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from reposcope.integrations.llm import LLMRequest, LLMError
from reposcope.recommendations.scorer import compute_priority_score

CORE = ("impact", "likelihood", "effort", "confidence", "category_multiplier", "score")
METRICS = {"fan_in": "measured_fan_in", "complexity": "measured_complexity",
           "documentation": "measured_documentation_gap"}


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Citation(Record):
    feature: str
    value: float = Field(strict=True)


class RationaleFacts(Record):
    repo_id: int = Field(gt=0, strict=True)
    snapshot_id: int = Field(gt=0, strict=True)
    finding_id: int = Field(gt=0, strict=True)
    category: str
    values: dict[str, float]
    round_digits: int = Field(default=4, ge=0, le=10, strict=True)


class RationalePlan(Record):
    template: Literal["priority", "fan_in", "complexity", "documentation"]
    citations: tuple[Citation, ...]


class RationaleResult(Record):
    text: str
    source: Literal["llm_constrained", "deterministic"]
    citations: tuple[Citation, ...]
    degraded_reason: str | None = None


def validate_facts(facts):
    facts = RationaleFacts.model_validate(facts.model_dump())
    if not set(CORE) <= set(facts.values) or set(facts.values) - (set(CORE) | set(METRICS.values())):
        raise ValueError("Missing or unsupported computed features")
    if any(not math.isfinite(v) for v in facts.values.values()):
        raise ValueError("Non-finite feature")
    v = facts.values
    score = compute_priority_score(v['impact'],v['likelihood'],v['effort'],v['confidence'],
        category_multiplier=v['category_multiplier'],round_digits=facts.round_digits)
    if score != v['score']:
        raise ValueError("Stored score disagrees with computed features")
    return facts


def default_template(facts):
    expected = {'UNTESTED_HOTSPOT':'fan_in','COMPLEXITY_HOTSPOT':'complexity','API_DOC_GAP':'documentation'}
    template = expected.get(facts.category,'priority')
    return template if template == 'priority' or METRICS[template] in facts.values else 'priority'


def required_features(template):
    return CORE + (() if template == 'priority' else (METRICS[template],))


def validate_plan(data,facts):
    plan = RationalePlan.model_validate(data)
    if plan.template not in ('priority',default_template(facts)):
        raise ValueError("Template is unsupported by this finding")
    names = [c.feature for c in plan.citations]
    if len(names) != len(set(names)) or set(names) != set(required_features(plan.template)):
        raise ValueError("Missing, duplicate or unsupported citations")
    for citation in plan.citations:
        if citation.value != facts.values.get(citation.feature):
            raise ValueError("Citation does not exactly match computed feature")
    return plan


def render(plan,facts,source,reason=None):
    v=facts.values
    def show(key):return f"{v[key]} [{key}={v[key]}]"
    text=(f"Computed heuristic priority {show('score')} uses impact {show('impact')}, "
          f"likelihood estimate {show('likelihood')}, applied effort {show('effort')}, "
          f"confidence estimate {show('confidence')} and category multiplier {show('category_multiplier')}.")
    if plan.template=='fan_in':
        text+=f" The detector recorded {show('measured_fan_in')} non-test callers; static links are not runtime coverage."
    elif plan.template=='complexity':
        text+=f" The detector recorded cyclomatic complexity {show('measured_complexity')}."
    elif plan.template=='documentation':
        text+=f" The inspected-handler docstring-gap indicator is {show('measured_documentation_gap')}; external documentation was not assessed."
    citations=tuple(Citation(feature=k,value=v[k]) for k in required_features(plan.template))
    return RationaleResult(text=text,source=source,citations=citations,degraded_reason=reason)


def deterministic_rationale(facts,reason=None):
    facts=validate_facts(facts)
    template=default_template(facts)
    plan=RationalePlan(template=template,citations=tuple(Citation(feature=k,value=facts.values[k])
        for k in required_features(template)))
    return render(plan,facts,'deterministic',reason)


class RationaleGenerator:
    def __init__(self,client=None,*,timeout=8):
        self.client,self.timeout=client,timeout

    async def generate(self,facts):
        facts=validate_facts(facts)
        if self.client is None:
            return deterministic_rationale(facts,'LLM_NOT_CONFIGURED')
        template=default_template(facts)
        request=LLMRequest(messages=(
            {'role':'system','content':
             'Choose priority or the allowed supported template. Copy every required feature and exact value. '
             'Return only the specified JSON; no prose, new claims, percentages, rounding, or extra fields.'},
            {'role':'user','content':f'Allowed templates: priority, {template}. Required core citations: '+', '.join(CORE)+
             (f'. Template {template} also requires {METRICS[template]}.' if template!='priority' else '.')},),
            evidence=facts.model_dump(mode='json'),
            cache_scope=f'recommendation-rationale-v1:repo={facts.repo_id}:snapshot={facts.snapshot_id}:finding={facts.finding_id}',
            response_schema=RationalePlan.model_json_schema(),temperature=0,max_output_tokens=1024)
        try:
            response=await asyncio.wait_for(self.client.generate(request),timeout=self.timeout)
            plan=validate_plan(response.data,facts)
        except (LLMError,TimeoutError,ValueError,TypeError,AttributeError):
            return deterministic_rationale(facts,'LLM_UNAVAILABLE_OR_INVALID_CITATIONS')
        return render(plan,facts,'llm_constrained')
