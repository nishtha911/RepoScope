# Day 14 Track 2: offline impact evaluation foundation

This patch implements the scorer, not the completed historical dataset D.
No database migration, network request, LLM call, or repository-code execution is performed.

## Dataset format (JSON schema version 1)
Root fields: schema_version (1), dataset_id (nonblank string), cases (list).
Each case has exactly: case_id, repository (owner/name), pr_number, base_sha,
head_sha (full lowercase 40-character SHAs), changed_files, files, tests,
test_runs, reviewed_by (string or null), notes (nonblank).

`files` and `tests` each contain status (complete/partial/unknown), paths
(unique canonical repository-relative POSIX paths), and evidence. Each evidence
entry contains reference, commit_sha (base or head), and note. Known labels need
evidence. Unknown labels have no positive paths. Tests are evaluated at FILE level,
not pytest node-ID level. Reviewed labels must use the same base/head path union
policy as predictions: preserve removed base paths and added head paths; for
renames preserve both names when relevant. No case folding or basename matching.

Each test run contains kind (historical/reproduction), commit_sha (exact head),
reference (artifact provenance), command, and outcome (passed/failed/error).
A reproduction is not an original historical CI run. A CI green check alone is
not evidence that a particular test ran or is relevant. Runs are provenance, not
relevance labels. Expected impacted production files and relevant tests require
independent review; do not use analyzer predictions to manufacture labels.
An error-only run does not satisfy release readiness.

`--require-ready` enforces exactly 30 cases, complete file labels, reviewer names,
and at least one completed passed/failed head test run per case. Validation checks
structure and recorded identity, not truthfulness or remote artifact availability.
Human provenance review is mandatory. Complete means exhaustive within the
explicit scope documented in case notes, not inferred runtime impact.

## Predictions
Root: schema_version (1), dataset_id, analyzer, predictions (list).
Rows: case_id, base_sha, head_sha, status (ok/failed), files, tests, error.
Failed rows require nonblank error and empty outputs; successful rows require
null error. Commit identity must match the case exactly. Extra/duplicate IDs fail.
The scorer takes explicit path inventories; counts in PRAnalysisReport cannot
be expanded back into impacted file names. An analyzer export adapter is separate.

## Commands (from backend)

    python evaluation/runners/impact_eval.py validate --dataset evaluation/datasets/D/dataset.json
    python evaluation/runners/impact_eval.py validate --dataset evaluation/datasets/D/dataset.json --require-ready
    python evaluation/runners/impact_eval.py baseline --dataset evaluation/datasets/D/dataset.json --out evaluation/results/baseline-01
    python evaluation/runners/impact_eval.py score --dataset evaluation/datasets/D/dataset.json --predictions evaluation/predictions/impact.json --out evaluation/results/impact-01 --require-ready

Dataset/prediction input paths above are planned locations, not files supplied by
this foundation patch. No synthetic fixture is included in the real dataset.
Outputs are impact-results.json and impact-results.csv in a fresh directory.
Exit code 2 indicates invalid inputs or missing/failed predictions (failure reports
are still written when the inputs validate). Exit 0 is not a quality threshold.

## Scoring policy
Complete labels: per-case precision, recall, F1; macro F1 and micro pooled
precision/recall/F1. Partial labels: known-positive recall only; unmatched predictions
are not declared false positives. Unknown labels are not scored. Missing/failed
analyses score zero macro F1 and recall for known labels; their known positives
contribute false negatives. Micro counts cannot penalize failed empty-truth cases;
always report coverage/failure counts and macro F1 beside micro metrics.
For successful empty/empty sets F1=1; empty prediction with positive truth F1=0;
false-positive-only predictions F1=0. No true-negative accuracy is reported because
a finite negative universe is not defined. Results hash canonicalized dataset and
predictions. Baseline predicts changed_files for file impact and no relevant tests;
it is not an inferred ground truth or a production analyzer.

## Remaining Day 14 work
Collect, independently label, review, and provenance-check 30 actual PRs using the
existing repos.lock repositories where eligible. Capture diffs, source revisions,
and head-run artifacts. Export production analyzer path predictions, run the
benchmark, compare to baseline, and review failures. Do not mark dataset D or the
full Day 14 milestone complete merely because these unit tests pass.
