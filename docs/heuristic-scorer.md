# Day 12 Heuristic Feature Scorer

`reposcope.recommendations.scorer.HeuristicScorer` computes domain-informed feature dimensions
(`impact`, `likelihood`, `effort`, `confidence`) and calculates deterministic priority scores
for codebase findings detected by the Day 11 detector engine.

## Priority Score Formulation

$$\text{score} = \frac{\text{impact} \times \text{likelihood}}{\text{effort}} \times \text{confidence} \times \text{category\_multiplier}$$

| Dimension | Domain Meaning | Range | Constraints |
| :--- | :--- | :--- | :--- |
| **Impact** | Breadth of affected callers, blast radius, API contract exposure | $\ge 0.0$ | Finite, non-negative float |
| **Likelihood** | Defect probability or failure escape risk | $[0.0, 1.0]$ | Calibrated bounded probability |
| **Effort** | Estimated cost / friction to refactor, test, or document | $> 0.0$ | Strictly positive ($\ge 0.5$ clamped) |
| **Confidence** | Measurement certainty (AST exactness, static index completeness) | $[0.0, 1.0]$ | Bounded probability |
| **Category Multiplier** | User feedback prior weight ($\text{prior} \in [0.5, 1.5]$) | $> 0.0$ | Defaults to 1.0 |

## Category Feature Rules

### 1. `UNTESTED_HOTSPOT`
- **Impact**: Base $5.0$ + fan-in bonus $\min(5.0, (\text{fan\_in} - 5) \times 0.5)$. A widely invoked helper that breaks impacts multiple callers.
- **Likelihood**: Base $0.70$ + caller scaling $\min(0.20, \text{fan\_in} \times 0.02) + 0.05$ if complex. High call frequency with zero tests leads to unverified regression risk.
- **Effort**: Base $1.0$ + branch effort $\min(3.0, \text{complexity} \times 0.15)$ + length scaling.
- **Confidence**: $0.95$ (requires complete static test-link index).

### 2. `COMPLEXITY_HOTSPOT`
- **Impact**: Base $4.0$ + $\min(6.0, (\text{complexity} - 10) \times 0.4)$. Complex routines pose severe maintenance and regression liabilities.
- **Likelihood**: Base $0.55$ + $\min(0.40, (\text{complexity} - 10) \times 0.03)$. Cyclomatic branching directly correlates with defect density.
- **Effort**: Base $2.0$ + $\min(6.0, (\text{complexity} - 10) \times 0.3)$. Refactoring high-complexity control flow requires architectural decomposition.
- **Confidence**: $0.95$ (directly measured from Tree-sitter / AST nodes).

### 3. `API_DOC_GAP`
- **Impact**: $4.5$ (endpoints are public integration contracts).
- **Likelihood**: $0.65$ (unregistered or undocumented parameters cause integration faults).
- **Effort**: $1.0$ (writing docstrings is high-ROI, minimal effort).
- **Confidence**: $0.90$ (deterministic nonblank handler docstring check).

## Usage Example

```python
from reposcope.recommendations.detectors import detect_candidates
from reposcope.recommendations.scorer import HeuristicScorer

# 1. Detect candidate findings
candidate_report = detect_candidates(candidate_dataset)

# 2. Score and rank findings
scorer = HeuristicScorer()
scored_report = scorer.score_report(candidate_report, dataset=candidate_dataset)

for finding in scored_report.findings:
    print(f"[{finding.category}] {finding.title} — Priority: {finding.score:.2f} (Confidence: {finding.confidence:.2f})")
```

## Verification

Run test suite:
```bash
uv run pytest -o pythonpath=. tests/unit/test_heuristic_scorer.py -v
```
All 23 focused unit tests cover formula calculations, division safety, boundary validations, feature derivations, and report sorting determinism.

