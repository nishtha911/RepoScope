# Day 13 Track 1: deterministic risk score and static test-gap engine

## Scope and entry points

- `risk_score.score_risk(RiskFeatures(...))`: six normalized factors -> weighted
  contributions, score, level and explicit missing-evidence interval.
- `test_gap.analyze_test_gaps(graph, repository_id, snapshot_id, ids, ...)`:
  identify modified production callables with no known static test associations.
- `risk_engine.assess_pr_risk(diff_report, repository_id, snapshots, ...)`:
  connects Day 11 contracts and Day 12 graphs/results, verifies side-specific
  bindings and revisions, computes factors, and returns a JSON-serializable report.

No LLM, schema migration, DB write, API replacement or runtime code execution.
Day 12's loader can provide graphs; verified role/sensitivity/parser metadata
must be supplied separately. This patch does not invent missing ORM fields.

## Frozen policy risk_v1

| Factor | Weight | Normalization |
| --- | --- | --- |
| Blast radius | 30% | min(maximum per-side sum of affected weights / 50, 1) |
| Sensitivity | 20% | max signal: endpoint .6, verified DB model .8, explicitly sensitive symbol 1 |
| Test gap | 20% | no-known-link / applicable modified production callables |
| Contract changes | 15% | mean classification cost: body 0; added .5; removed/signature 1 |
| Complexity delta | 10% | min(maximum positive callable complexity increase / 10, 1) |
| Size | 5% | min((added + deleted patch rows) / 500, 1) |

Score = .30*blast + .20*sensitivity + .20*test_gap + .15*contract +
.10*complexity + .05*size. These are initial documented heuristics, not learned
calibration, semantic breaking-change proof or a probability of failure.
Normalization caps are configurable via RiskPolicy. Feature weights and threshold
bands are fixed for this version. Scores remain on [0,1], not [0,100].

LOW: [0,.25), MEDIUM: [.25,.50), HIGH: [.50,.75), CRITICAL: [.75,1].
Unknown factors remain None; no renormalization or invented zero values. If any
factor is unknown, score and risk_level are None and status is INCOMPLETE.
The lower bound sums known contributions; upper bound adds unknown weights.
The UI/API must handle incomplete reports rather than force a LOW badge.

## Version boundaries and prerequisites

`snapshots` maps base/head to RiskSnapshot(graph, blast_radius, bindings, ...).
Only sides with changed versions are required. Each context must use the same
repository, snapshot and SHA as its side, and its blast seeds must exactly match
the checked local-key-to-ID bindings. Day 12 resolve_diff_seeds verifies path,
qualname, kind and line ranges. IDs from separate snapshots are never unioned.
Blast mass uses the maximum side mass to avoid naive double-counting across sides;
this is a policy proxy, not a deduplicated union of base/head blast graphs.
Truncated traversal, missing bindings and unknown edge confidence keep the blast
factor incomplete. Upstream diff gaps remain visible and prevent a complete score.
Binary/symlink/submodule/copied entries are explicitly unmeasured, not zero risk.

## Static test associations

Roles must come from verified same-snapshot classification: production, test or
unknown. Omitted roles remain unknown. TESTED_BY runs implementation -> test.
Any valid positive-confidence link to a verified callable test establishes LINKED;
confidence is association evidence, not runtime test coverage. Invalid/unknown
association metadata blocks an absence claim. An absent link yields
NO_KNOWN_TEST_LINK only when test_links_complete=True (fully loaded static index).
No statically detected relationship is not proof that no test covers the code.
Tests and noncallables are NOT_APPLICABLE. Unknown roles/associations keep the
aggregate test-gap factor unknown. Head versions are used for surviving/added
changes; removals use base. The output includes side, snapshot ID, symbol ID,
qualified name, local key and file path for every untested modified symbol.

## Sensitivity and complexity metadata

RiskSnapshot defaults sensitivity_complete=False, test_links_complete=False and
unknown roles. Supply explicitly verified sensitive_symbol_ids per snapshot and
set sensitivity_complete only after classification. No name/path guesses are made.
A known saturated sensitivity signal of 1 remains 1 even if other labels are unknown.
The graph must flag verified database models via is_database_model, as in Day 12.

base_complexities/head_complexities map Day 11 local keys to measured positive
integers. Callers must obtain them from the corresponding revision's validated
parser output using the SAME complexity policy on both sides; arbitrary scores or
mismatched policies are invalid inputs. Added callables compare to 0; removals have
0 positive increase; reductions clamp at 0. Unknown measurements remain unknown.
Class records are not treated as callable complexity. The integration does not
claim to extract metadata directly from the current symbols ORM table.

## Example integration shape

```python
from reposcope.impact.risk_engine import RiskSnapshot, assess_pr_risk

contexts = {
    'base': RiskSnapshot(base_graph, base_blast, base_bindings,
        symbol_roles=base_roles, test_links_complete=True,
        sensitive_symbol_ids=base_sensitive_ids, sensitivity_complete=True),
    'head': RiskSnapshot(head_graph, head_blast, head_bindings,
        symbol_roles=head_roles, test_links_complete=True,
        sensitive_symbol_ids=head_sensitive_ids, sensitivity_complete=True),
}
assessment = assess_pr_risk(diff_report, repo_id, contexts,
    base_complexities=base_complexities, head_complexities=head_complexities)
serialized = assessment.model_dump(mode='json')
```

The completeness flags above are appropriate only when the caller has actually
verified those prerequisites. Existing storage must supply real base/head graphs;
this patch does not add historical snapshot persistence or fetch PRs.

## Tests and rollout

Run from backend:

python -m pytest tests/unit/test_risk_score.py tests/unit/test_test_gap.py tests/unit/test_risk_engine.py -q -rs

54 score/test-gap tests passed in the build environment. The 18 real Day 11/12
integration tests must run against the local Day 12 module; no execution of those
18, PostgreSQL test, or full backend regression is claimed by this package.
After focused tests, run python -m pytest tests -q -rs and git diff --check.

Not included: recommendation ranking/rationale API, UI, final PR report/API wiring,
LLM explanation, parser re-execution, or new historical graph persistence.
