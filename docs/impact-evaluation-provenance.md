# Dataset D: test-run provenance schema 2

Schema 1 remains supported unchanged. Existing candidate manifests remain schema 1
and are NOT upgraded automatically. Predictions and scoring outputs retain schema 1.
Only explicitly reviewed dataset inputs may use schema_version=2.

In schema 2, each test_runs record keeps kind, commit_sha, reference, command,
and outcome, and requires checkout and results. commit_sha is the ACTUAL tested
commit, not necessarily the PR head. reference identifies the test-result artifact.

checkout fields:
- mode: head or merge.
- pr_head_sha: must equal the case head_sha.
- parents: [] for head mode; exactly two distinct ordered commit SHAs for merge.
- checkout_reference: recorded evidence for the actual working-tree revision.
- parent_reference: null for head; recorded commit-parent evidence for merge.

Head mode requires commit_sha=head_sha. Merge mode requires a separate tested SHA
and second parent=head_sha. A merge is eligible for readiness only if its ordered
parents are exactly [case.base_sha, case.head_sha]. Merges into a different base
are preserved as contextual evidence but do not satisfy readiness. Parent claims
must be checked against commit metadata; a checkout message alone is insufficient
for that independent check. A merge result is never described as a head-only run.

results fields: passed, failed, skipped, errors; nonnegative integers (no booleans).
These are recorded observed counts, not test relevance or coverage labels. Failed
means failed assertions (failed>0); error means a setup/collection/command error.
A passed run requires passed>0 and no failures/errors; skipped-only is not enough.
An error does not satisfy readiness. A completed assertion-failing run may satisfy
the known-run requirement; it is not a claim the PR was successful.

All recorded run records are validated, not just the first eligible one. Readiness
still requires complete independent file labels and reviewer identity, plus 30
eligible cases for --require-ready. The validator checks recorded structure and
internal consistency, not whether an artifact exists or is trustworthy. Do not
invent references or fill reviewer names automatically.

No dataset labels, candidate manifests, collectors, API contracts, database, or
existing tests are modified by this patch. No Docker or external project execution.
Future provenance import must explicitly map actual logs/commit metadata to these
fields; unavailable evidence stays absent. Never copy example fixtures into D.
