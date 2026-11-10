"""Offline impact evaluation v1. No network, database, or source execution."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import re


class EvaluationError(ValueError):
    pass


def _object(value, fields, context):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise EvaluationError(f"{context}: expected exactly {sorted(fields)}")
    return value


def _text(value, context):
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"{context}: expected nonblank string")
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise EvaluationError("Expected full lowercase commit SHA")
    return value


def _path(value):
    _text(value, "path")
    if (value.startswith("/") or "\\" in value or ":" in value
        or any(ord(c) < 32 for c in value)
        or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise EvaluationError("Expected canonical repository-relative POSIX path")
    return value


def _paths(value):
    if not isinstance(value, list):
        raise EvaluationError("Expected path list")
    for item in value:
        _path(item)
    if len(set(value)) != len(value):
        raise EvaluationError("Duplicate paths")
    return value


def _evidence(value, allowed_shas):
    if not isinstance(value, list):
        raise EvaluationError("Expected evidence list")
    for item in value:
        _object(item, {"reference", "commit_sha", "note"}, "evidence")
        _text(item["reference"], "evidence reference")
        _text(item["note"], "evidence note")
        if _sha(item["commit_sha"]) not in allowed_shas:
            raise EvaluationError("Evidence commit is outside the case")


def _validate_test_run(run, base, head, version):
    fields = {"kind", "commit_sha", "reference", "command", "outcome"}
    if version == 2:
        fields |= {"checkout", "results"}
    _object(run, fields, "test run")
    if run["kind"] not in {"historical", "reproduction"}:
        raise EvaluationError("Invalid test-run kind")
    tested = _sha(run["commit_sha"])
    if run["outcome"] not in {"passed", "failed", "error"}:
        raise EvaluationError("Invalid test-run outcome")
    _text(run["reference"], "test artifact reference")
    _text(run["command"], "test command")
    if version == 1:
        if tested != head:
            raise EvaluationError("Test run must identify exact PR head")
        return run["outcome"] in {"passed", "failed"}
    checkout = run["checkout"]
    _object(checkout, {"mode", "pr_head_sha", "parents", "checkout_reference", "parent_reference"}, "checkout")
    if _sha(checkout["pr_head_sha"]) != head:
        raise EvaluationError("Checkout PR head mismatch")
    _text(checkout["checkout_reference"], "checkout evidence reference")
    parents = checkout["parents"]
    if not isinstance(parents, list):
        raise EvaluationError("Checkout parents must be a list")
    for parent in parents:
        _sha(parent)
    if checkout["mode"] == "head":
        if tested != head or parents or checkout["parent_reference"] is not None:
            raise EvaluationError("Head checkout requires tested=head and no merge-parent claim")
        aligned = True
    elif checkout["mode"] == "merge":
        _text(checkout["parent_reference"], "merge parent evidence reference")
        if len(parents) != 2 or len(set(parents)) != 2 or tested in parents:
            raise EvaluationError("Merge checkout requires two distinct ordered parents and a separate tested commit")
        if parents[1] != head:
            raise EvaluationError("Merge second parent must be the PR head")
        aligned = parents == [base, head]
    else:
        raise EvaluationError("Checkout mode must be head or merge")
    counts = run["results"]
    _object(counts, {"passed", "failed", "skipped", "errors"}, "test results")
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise EvaluationError("Test result counts must be nonnegative integers, not booleans")
    if run["outcome"] == "passed" and (counts["passed"] < 1 or counts["failed"] or counts["errors"]):
        raise EvaluationError("Passed run requires executed passing tests and no failures/errors")
    if run["outcome"] == "failed" and counts["failed"] < 1:
        raise EvaluationError("Failed test run requires failed tests; setup errors use outcome=error")
    if run["outcome"] == "error" and counts["failed"]:
        raise EvaluationError("Use outcome=failed when test assertions failed")
    return aligned and run["outcome"] in {"passed", "failed"}


def validate_dataset(data, *, require_ready=False):
    _object(data, {"schema_version", "dataset_id", "cases"}, "dataset")
    if type(data["schema_version"]) is not int or data["schema_version"] not in {1, 2}:
        raise EvaluationError("Unsupported dataset schema")
    _text(data["dataset_id"], "dataset_id")
    if not isinstance(data["cases"], list):
        raise EvaluationError("cases must be a list")
    ids, prs = set(), set()
    ready = 0
    for case in data["cases"]:
        _object(case, {"case_id", "repository", "pr_number", "base_sha", "head_sha",
            "changed_files", "files", "tests", "test_runs", "reviewed_by", "notes"}, "case")
        cid = _text(case["case_id"], "case_id")
        repo = case["repository"]
        if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise EvaluationError("Invalid repository")
        number = case["pr_number"]
        if type(number) is not int or number < 1:
            raise EvaluationError("Invalid PR number")
        identity = (repo.lower(), number)
        if cid in ids or identity in prs:
            raise EvaluationError("Duplicate case or PR identity")
        ids.add(cid)
        prs.add(identity)
        base, head = _sha(case["base_sha"]), _sha(case["head_sha"])
        if base == head:
            raise EvaluationError("Base and head must differ")
        _paths(case["changed_files"])
        _text(case["notes"], "case notes")
        if case["reviewed_by"] is not None:
            _text(case["reviewed_by"], "reviewed_by")
        for category in ("files", "tests"):
            labels = case[category]
            _object(labels, {"status", "paths", "evidence"}, category)
            if labels["status"] not in {"complete", "partial", "unknown"}:
                raise EvaluationError("Invalid label status")
            _paths(labels["paths"])
            _evidence(labels["evidence"], {base, head})
            if labels["status"] == "unknown" and labels["paths"]:
                raise EvaluationError("Unknown labels cannot contain positive labels")
            if labels["status"] != "unknown" and not labels["evidence"]:
                raise EvaluationError("Known labels require independent evidence")
        runs = case["test_runs"]
        if not isinstance(runs, list):
            raise EvaluationError("test_runs must be a list")
        run_eligibility = [
            _validate_test_run(run, base, head, data["schema_version"])
            for run in runs
        ]
        eligible = (case["files"]["status"] == "complete"
                    and case["reviewed_by"] is not None
                    and any(run_eligibility))
        ready += int(eligible)
        if require_ready and not eligible:
            raise EvaluationError(f"{cid}: not release-ready")
    if require_ready and len(data["cases"]) != 30:
        raise EvaluationError("Dataset D release requires exactly 30 ready real PR cases")
    return {"cases": len(ids), "ready_cases": ready,
            "release_ready": len(ids) == ready == 30}


def validate_predictions(data, dataset):
    _object(data, {"schema_version", "dataset_id", "analyzer", "predictions"}, "predictions")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise EvaluationError("Unsupported prediction schema")
    if data["dataset_id"] != dataset["dataset_id"]:
        raise EvaluationError("Prediction dataset mismatch")
    _text(data["analyzer"], "analyzer")
    if not isinstance(data["predictions"], list):
        raise EvaluationError("predictions must be a list")
    cases = {c["case_id"]: c for c in dataset["cases"]}
    seen = set()
    for row in data["predictions"]:
        _object(row, {"case_id", "base_sha", "head_sha", "status", "files", "tests", "error"}, "prediction")
        cid = _text(row["case_id"], "prediction case_id")
        if cid not in cases or cid in seen:
            raise EvaluationError("Unknown or duplicate prediction case")
        seen.add(cid)
        for side in ("base_sha", "head_sha"):
            if row[side] != cases[cid][side]:
                raise EvaluationError("Prediction commit mismatch")
        _paths(row["files"])
        _paths(row["tests"])
        if row["status"] not in {"ok", "failed"}:
            raise EvaluationError("Invalid prediction status")
        if row["status"] == "failed":
            _text(row["error"], "prediction error")
            if row["files"] or row["tests"]:
                raise EvaluationError("Failed predictions cannot claim successful outputs")
        elif row["error"] is not None:
            raise EvaluationError("Successful prediction cannot contain an error")


def set_metrics(expected, predicted):
    truth, guess = set(expected), set(predicted)
    tp, fp, fn = len(truth & guess), len(guess - truth), len(truth - guess)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not truth else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0
    return dict(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def evaluate(dataset, predictions, *, require_ready=False):
    inventory = validate_dataset(dataset, require_ready=require_ready)
    validate_predictions(predictions, dataset)
    by_id = {r["case_id"]: r for r in predictions["predictions"]}
    rows = []
    statuses = {"ok": 0, "failed": 0, "missing": 0}
    for case in sorted(dataset["cases"], key=lambda c: c["case_id"]):
        pred = by_id.get(case["case_id"])
        status = pred["status"] if pred else "missing"
        statuses[status] += 1
        for category in ("files", "tests"):
            label = case[category]
            row = dict(case_id=case["case_id"], category=category,
                       prediction_status=status, label_status=label["status"],
                       tp=None, fp=None, fn=None, precision=None, recall=None, f1=None)
            if label["status"] != "unknown":
                guess = pred[category] if status == "ok" else []
                row.update(set_metrics(label["paths"], guess))
                if label["status"] == "partial":
                    row.update(fp=None, precision=None, f1=None)
                if status != "ok":
                    row.update(precision=None, recall=0.0, f1=0.0 if label["status"] == "complete" else None)
                row["missing_known"] = sorted(set(label["paths"]) - set(guess))
            rows.append(row)
    aggregates = {}
    for category in ("files", "tests"):
        complete = [r for r in rows if r["category"] == category and r["label_status"] == "complete"]
        scored_ok = [r for r in complete if r["prediction_status"] == "ok"]
        totals = {key: sum(r[key] for r in complete) for key in ("tp", "fp", "fn")}
        tp, fp, fn = (totals[k] for k in ("tp", "fp", "fn"))
        aggregates[category] = dict(
            complete_label_cases=len(complete), successful_cases=len(scored_ok),
            macro_f1=sum(r["f1"] for r in complete) / len(complete) if complete else None,
            micro_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else (1.0 if complete and len(scored_ok)==len(complete) else None),
            micro_precision=tp/(tp+fp) if tp+fp else None,
            micro_recall=tp/(tp+fn) if tp+fn else None, **totals)
    digest = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return dict(schema_version=1, dataset_id=dataset["dataset_id"], analyzer=predictions["analyzer"],
                dataset_sha256=digest(dataset), predictions_sha256=digest(predictions),
                inventory=inventory, prediction_counts=statuses, aggregates=aggregates, rows=rows,
                policy="Missing/failed analyses score zero macro F1 for complete labels; partial labels provide known-positive recall only. Micro counts cannot represent failures on empty truth; inspect coverage and macro F1.")


def changed_files_baseline(dataset):
    validate_dataset(dataset)
    return dict(schema_version=1, dataset_id=dataset["dataset_id"], analyzer="changed-files-only-v1",
        predictions=[dict(case_id=c["case_id"], base_sha=c["base_sha"], head_sha=c["head_sha"],
            status="ok", files=c["changed_files"], tests=[], error=None) for c in dataset["cases"]])


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EvaluationError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def bad_constant(value):
        raise EvaluationError(f"Invalid JSON number: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique, parse_constant=bad_constant)


def write_results(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    targets = [directory / "impact-results.json", directory / "impact-results.csv"]
    if any(p.exists() for p in targets):
        raise EvaluationError("Output already exists; choose a fresh output directory")
    fields = ["case_id", "category", "prediction_status", "label_status", "tp", "fp", "fn", "precision", "recall", "f1"]
    with targets[0].open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    with targets[1].open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["rows"])
