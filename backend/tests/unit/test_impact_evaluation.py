"""Synthetic contract fixtures only: these are not historical dataset D cases."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest
from reposcope.evaluation.impact import (
    EvaluationError, changed_files_baseline, evaluate, read_json,
    set_metrics, validate_dataset, write_results,
)


def dataset():
    evidence = [{"reference": "fixture://manual-review", "commit_sha": "b"*40,
                 "note": "Synthetic independently specified expected paths"}]
    return dict(schema_version=1, dataset_id="synthetic-unit-fixture", cases=[dict(
        case_id="example-1", repository="example/project", pr_number=1,
        base_sha="a"*40, head_sha="b"*40, changed_files=["app.py"],
        files=dict(status="complete", paths=["app.py", "consumer.py"], evidence=evidence),
        tests=dict(status="complete", paths=["tests/test_app.py"], evidence=evidence),
        test_runs=[dict(kind="reproduction", commit_sha="b"*40, reference="fixture://junit",
                        command="python -m pytest", outcome="passed")],
        reviewed_by="synthetic-fixture-author", notes="Not a real PR")])


def predictions(d):
    p = changed_files_baseline(d)
    p["predictions"][0]["files"] = ["app.py", "unrelated.py"]
    p["predictions"][0]["tests"] = ["tests/test_app.py"]
    return p


def test_metrics():
    assert set_metrics(["a", "b"], ["a", "c"])["f1"] == .5


@pytest.mark.parametrize("truth,guess,f1", [([],[],1), (["a"],[],0), ([],["a"],0), (["a"],["a"],1)])
def test_empty_policy(truth,guess,f1):
    assert set_metrics(truth,guess)["f1"] == f1


def test_stable_evaluation():
    d=dataset(); p=predictions(d)
    r=evaluate(d,p)
    assert r == evaluate(d,p)
    assert r["aggregates"]["files"]["macro_f1"] == .5
    assert r["aggregates"]["tests"]["macro_f1"] == 1
    assert r["rows"][0]["missing_known"] == ["consumer.py"]


def test_partial_does_not_claim_false_positives():
    d=dataset(); d["cases"][0]["files"]["status"]="partial"
    r=evaluate(d,predictions(d))
    assert r["rows"][0]["precision"] is None
    assert r["rows"][0]["fp"] is None
    assert r["rows"][0]["recall"] == .5
    assert r["aggregates"]["files"]["macro_f1"] is None


def test_unknown_excluded():
    d=dataset(); d["cases"][0]["tests"].update(status="unknown", paths=[], evidence=[])
    assert evaluate(d,predictions(d))["aggregates"]["tests"]["complete_label_cases"] == 0


@pytest.mark.parametrize("status", ["missing","failed"])
def test_failure_is_not_perfect_empty(status):
    d=dataset(); d["cases"][0]["files"]["paths"]=[]
    p=predictions(d)
    if status=="missing": p["predictions"]=[]
    else: p["predictions"][0].update(status="failed",files=[],tests=[],error="Parser failed")
    r=evaluate(d,p)
    assert r["aggregates"]["files"]["macro_f1"] == 0
    assert r["prediction_counts"][status] == 1


@pytest.mark.parametrize("path", ["../a.py", "/a.py", "a\\b.py", "a//b.py", "C:/a.py", "a/./b.py", "a\x00.py"])
def test_bad_paths(path):
    d=dataset(); d["cases"][0]["changed_files"]=[path]
    with pytest.raises(EvaluationError): validate_dataset(d)


@pytest.mark.parametrize("mutation", ["duplicate", "sha", "evidence", "run", "extra", "bool_pr", "duplicates_path"])
def test_invalid_dataset(mutation):
    d=dataset(); c=d["cases"][0]
    if mutation=="duplicate": d["cases"].append(copy.deepcopy(c))
    elif mutation=="sha": c["base_sha"]="short"
    elif mutation=="evidence": c["files"]["evidence"]=[]
    elif mutation=="run": c["test_runs"][0]["commit_sha"]="c"*40
    elif mutation=="extra": c["magic"]=True
    elif mutation=="bool_pr": c["pr_number"]=True
    else: c["changed_files"]=["app.py","app.py"]
    with pytest.raises(EvaluationError): validate_dataset(d)


@pytest.mark.parametrize("mutation", ["sha", "unknown", "duplicate", "wrong_dataset", "bad_failed"])
def test_invalid_predictions(mutation):
    d=dataset(); p=predictions(d); row=p["predictions"][0]
    if mutation=="sha": row["head_sha"]="c"*40
    elif mutation=="unknown": row["case_id"]="other"
    elif mutation=="duplicate": p["predictions"].append(copy.deepcopy(row))
    elif mutation=="wrong_dataset": p["dataset_id"]="other"
    else: row.update(status="failed", error="failed")
    with pytest.raises(EvaluationError): evaluate(d,p)


def test_release_gate():
    d=dataset()
    assert not validate_dataset(d)["release_ready"]
    with pytest.raises(EvaluationError): validate_dataset(d,require_ready=True)
    cases=[]
    for i in range(30):
        c=copy.deepcopy(d["cases"][0]); c.update(case_id=f"fixture-{i}",pr_number=i+1)
        cases.append(c)
    d["cases"]=cases
    assert validate_dataset(d,require_ready=True)["ready_cases"]==30
    d["cases"][0]["test_runs"]=[]
    with pytest.raises(EvaluationError): validate_dataset(d,require_ready=True)


def test_json_and_csv(tmp_path):
    d=dataset(); report=evaluate(d,predictions(d))
    write_results(report,tmp_path)
    assert read_json(tmp_path/"impact-results.json")==report
    assert "example-1,files" in (tmp_path/"impact-results.csv").read_text()
    with pytest.raises(EvaluationError): write_results(report,tmp_path)


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":NaN}'])
def test_strict_json(tmp_path,text):
    p=tmp_path/"bad.json"; p.write_text(text)
    with pytest.raises(EvaluationError): read_json(p)


def test_cli_offline(tmp_path):
    root=Path(__file__).resolve().parents[2]
    script=root/"evaluation/runners/impact_eval.py"
    d=tmp_path/"dataset.json"; d.write_text(json.dumps(dataset()))
    run=subprocess.run([sys.executable,str(script),"baseline","--dataset",str(d),"--out",str(tmp_path/"out")],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert (tmp_path/"out/impact-results.json").is_file()
