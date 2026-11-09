import math
import pytest
from pydantic import ValidationError
from reposcope.impact.risk_score import FEATURE_WEIGHTS, RiskFeatures, RiskPolicy, score_risk


def features(value=0, **changes):
    return RiskFeatures(**{**dict.fromkeys(FEATURE_WEIGHTS,value),**changes})


def test_weights_sum_to_one():
    assert sum(FEATURE_WEIGHTS.values()) == 1


@pytest.mark.parametrize('value,level',[(0,'LOW'),(.249,'LOW'),(.25,'MEDIUM'),(.499,'MEDIUM'),(.5,'HIGH'),(.749,'HIGH'),(.75,'CRITICAL'),(1,'CRITICAL')])
def test_boundaries(value,level):
    r = score_risk(features(value))
    assert r.score == pytest.approx(value)
    assert r.risk_level == level and r.status == 'COMPLETE'
    assert r.lower_bound == r.upper_bound


@pytest.mark.parametrize('name',list(FEATURE_WEIGHTS))
def test_one_component_weight(name):
    r = score_risk(features(**{name:1}))
    assert r.score == float(FEATURE_WEIGHTS[name])
    assert sum(c.contribution for c in r.components) == r.score


@pytest.mark.parametrize('name',list(FEATURE_WEIGHTS))
def test_unknown_not_zero_or_renormalized(name):
    r = score_risk(features(.5,**{name:None}))
    assert r.score is None and r.risk_level is None and r.status == 'INCOMPLETE'
    assert r.upper_bound-r.lower_bound == pytest.approx(float(FEATURE_WEIGHTS[name]))
    assert r.missing_features == (name,)


def test_all_unknown_interval():
    r = score_risk(RiskFeatures())
    assert (r.lower_bound,r.upper_bound) == (0,1)


@pytest.mark.parametrize('value',[-.01,1.01,math.nan,math.inf,-math.inf])
def test_invalid_values(value):
    with pytest.raises(ValidationError):
        features(blast_radius=value)


def test_deterministic_serialization():
    assert score_risk(features(.37)).model_dump_json() == score_risk(features(.37)).model_dump_json()


@pytest.mark.parametrize('name,value',[('blast_mass_cap',0),('blast_mass_cap',math.inf),('complexity_increase_cap',True),('changed_lines_cap',0)])
def test_bad_caps(name,value):
    with pytest.raises(ValidationError):
        RiskPolicy(**{name:value})
