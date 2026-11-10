"""Synthetic provenance fixtures, not historical dataset D labels."""
import copy
import pytest
from reposcope.evaluation.impact import EvaluationError, validate_dataset, changed_files_baseline, evaluate


def dataset(version=2,mode="merge"):
    base,head,merge="a"*40,"b"*40,"c"*40
    run=dict(kind="historical",commit_sha=head if mode=="head" else merge,
             reference="fixture://test-summary",command="python -m pytest",outcome="passed")
    if version==2:
        run.update(checkout=dict(mode=mode,pr_head_sha=head,
            parents=[] if mode=="head" else [base,head],
            checkout_reference="fixture://checkout-log",
            parent_reference=None if mode=="head" else "fixture://commit-parent-record"),
            results=dict(passed=5,failed=0,skipped=1,errors=0))
    return dict(schema_version=version,dataset_id="synthetic-provenance",cases=[dict(
        case_id="synthetic-1",repository="example/project",pr_number=1,base_sha=base,head_sha=head,
        changed_files=["app.py"],files=dict(status="complete",paths=["app.py"],evidence=[dict(
            reference="fixture://independent-file-review",commit_sha=head,note="Synthetic fixture")]),
        tests=dict(status="unknown",paths=[],evidence=[]),test_runs=[run],reviewed_by="fixture-reviewer",
        notes="Synthetic unit test; not a real PR")])


def run(d):return d["cases"][0]["test_runs"][0]


def test_v1_head_compatible():
    d=dataset(1,"head")
    assert validate_dataset(d)["ready_cases"]==1


def test_v1_merge_still_rejected():
    with pytest.raises(EvaluationError):validate_dataset(dataset(1,"merge"))


@pytest.mark.parametrize("mode",["head","merge"])
def test_v2_aligned_ready(mode):
    d=dataset(mode=mode)
    assert validate_dataset(d)["ready_cases"]==1
    assert evaluate(d,changed_files_baseline(d))["aggregates"]["files"]["macro_f1"]==1


def test_other_base_preserved_but_not_ready():
    d=dataset();run(d)["checkout"]["parents"][0]="d"*40
    assert validate_dataset(d)["ready_cases"]==0
    with pytest.raises(EvaluationError):validate_dataset(d,require_ready=True)


@pytest.mark.parametrize("mutation",["head","same_commit","missing_parent_ref","missing_checkout_ref",
    "one_parent","reversed_parents","duplicate_parents","extra","unknown_mode","bool_count",
    "negative_count","string_count","fake_pass","failure_without_failed","error_with_failed"])
def test_invalid_provenance(mutation):
    d=dataset();r=run(d);c=r["checkout"]
    if mutation=="head":c["pr_head_sha"]="d"*40
    elif mutation=="same_commit":r["commit_sha"]="b"*40
    elif mutation=="missing_parent_ref":c["parent_reference"]=None
    elif mutation=="missing_checkout_ref":c["checkout_reference"]=" "
    elif mutation=="one_parent":c["parents"]=["b"*40]
    elif mutation=="reversed_parents":c["parents"].reverse()
    elif mutation=="duplicate_parents":c["parents"]=["b"*40,"b"*40]
    elif mutation=="extra":c["invented"]=True
    elif mutation=="unknown_mode":c["mode"]="maybe"
    elif mutation=="bool_count":r["results"]["passed"]=True
    elif mutation=="negative_count":r["results"]["skipped"]=-1
    elif mutation=="string_count":r["results"]["passed"]="5"
    elif mutation=="fake_pass":r["results"]["passed"]=0
    elif mutation=="failure_without_failed":r["outcome"]="failed"
    else:r["outcome"]="error";r["results"]["failed"]=2
    with pytest.raises(EvaluationError):validate_dataset(d)


def test_assertion_failures_can_be_known_runs():
    d=dataset();r=run(d);r["outcome"]="failed";r["results"]["failed"]=2
    assert validate_dataset(d)["ready_cases"]==1


def test_setup_error_not_eligible():
    d=dataset();r=run(d);r["outcome"]="error";r["results"].update(passed=0,errors=1)
    assert validate_dataset(d)["ready_cases"]==0


def test_skipped_only_is_not_passed_execution():
    d=dataset();run(d)["results"].update(passed=0,skipped=10)
    with pytest.raises(EvaluationError):validate_dataset(d)


def test_head_cannot_claim_merge_parents():
    d=dataset(mode="head");run(d)["checkout"]["parents"]=["a"*40,"b"*40]
    with pytest.raises(EvaluationError):validate_dataset(d)


def test_all_records_validated_even_after_good_run():
    d=dataset();bad=copy.deepcopy(run(d));bad["results"]["failed"]=-1
    d["cases"][0]["test_runs"].append(bad)
    with pytest.raises(EvaluationError):validate_dataset(d)


def test_unknown_file_labels_do_not_become_ready():
    d=dataset();d["cases"][0]["files"].update(status="unknown",paths=[],evidence=[])
    assert validate_dataset(d)["ready_cases"]==0


def test_empty_candidate_v1_still_valid():
    d=dataset(1,"head");d["cases"][0]["test_runs"]=[]
    assert validate_dataset(d)["ready_cases"]==0
