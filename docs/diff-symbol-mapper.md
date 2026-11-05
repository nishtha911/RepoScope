# Day 11 Track 1: Unified Diff Parser and Symbol Mapper

## Structure

```
raw unified patch
    -> impact.diff_parser.parse_unified_diff
    -> contracts.diff.DiffPatch (separate base/head coordinates)
    -> impact.symbol_mapper.map_diff_to_symbols
    -> SymbolDiffReport (changes, line mappings, gaps)
```

`analyze_python_diff` is the convenience adapter accepting a raw patch plus
complete base/head raw source-byte mappings. It invokes the existing Python
parser only for relevant Python paths. It does not fetch GitHub revisions,
apply a patch to disk, query/write the database, run code, compute blast radius,
score risk, or change the PR-report/API/frontend contracts.

## API

```python
from reposcope.impact.symbol_mapper import analyze_python_diff

report = analyze_python_diff(
    patch_text,
    base_sources={"src/app.py": base_bytes},
    head_sources={"src/app.py": head_bytes},
    base_revision=base_commit_sha,
    head_revision=head_commit_sha,
)
print(report.model_dump(mode="json"))
```

Supply full contents from the correct versions, not hunk snippets or current
working-tree content reused as both versions. Paths must match the diff's
repository-relative POSIX paths. ADDED files have no base version; REMOVED
files have no head version. A missing required version is a MISSING_SOURCE gap,
not evidence of addition/removal. Caller-supplied revision labels are preserved,
not independently fetched or verified. No database/snapshot IDs are invented.

For existing parser inventories:

```python
from reposcope.impact.diff_parser import parse_unified_diff
from reposcope.impact.symbol_mapper import map_diff_to_symbols

report = map_diff_to_symbols(parse_unified_diff(patch_text), base_parsed_files,
                             head_parsed_files)
```

## Classification policy

| Classification | Meaning |
| --- | --- |
| ADDED | A newly present unique definition owns changed head lines |
| REMOVED | A formerly present unique definition owns changed base lines |
| SIGNATURE_CHANGED | A paired definition's structural header differs |
| BODY_CHANGED | Paired definition/decorator text differs, but structural header is stable |

Headers are compared with Python AST structures, not raw strings or database
IDs. Callable arguments/defaults/annotations/async status/decorators and class
bases/keywords/decorators are part of the header. Line/column movement alone
is not a signature change. SIGNATURE_CHANGED takes precedence when both
header and body change. Class headers are handled even though the extraction
contract stores class.signature=None.

BODY_CHANGED is textual, not a runtime/semantic claim; comments, docstrings,
indentation and header-only formatting can qualify. CRLF is normalized to LF.
Function renames or moves across files are conservatively REMOVED+ADDED, not
heuristic identity guesses. Within a file pair, identities are (kind, qualname),
not local keys containing offsets. Explicit file renames pair old/new paths.
A pure file rename retains file metadata without inventing a symbol change.
Duplicate qualified identities generate AMBIGUOUS_SYMBOL_IDENTITY gaps.

Changed lines (only '-' and '+', not context) map to innermost containing
symbols, including decorator content ranges. Ancestor classes/functions are
not redundantly classified merely because a nested method/body changed.
Module-level changes generate MODULE_LEVEL_CHANGE gaps; no fake module symbol
is manufactured. Output includes side-specific local keys and line ranges,
not persistence IDs. Query the appropriate snapshot separately in later stages.

## Validation and incomplete results

Before mapping, the patch is replayed against supplied base text in memory and
must reproduce the supplied head text. Context, deletions, shifted target
coordinates and EOF-newline markers are checked. A mismatch/truncated patch
produces PATCH_SOURCE_MISMATCH and no symbol classifications for that file.
The mapper verifies extraction identity against source AST definitions, so
missing/stale inventories do not become invented changes. Source parse errors
and unsupported host-Python syntax produce explicit gaps.

Unified and git-unified formats, zero-length hunk sides, multiple files/hunks,
UTF-8 paths, quoted Git filenames, EOF-newline markers and file renames are
handled. Binary files, copies, symlinks/submodules and non-Python entries are
retained/identified but not falsely classified as Python source changes.
Combined merge diffs are rejected; provide a normal two-revision unified diff.
Git-style a/ and b/ prefixes are stripped only when supported by headers/pairs;
ordinary paths under an a/ directory are not blindly truncated.

Default patch budgets: 5 MB UTF-8 input, 200000 physical lines, 1000 files.
Convenience adapter source budgets: 2 MB/file version and 20 MB total. Exceeded
source budgets create explicit gaps; complete source is never silently clipped.
The lower-level ParsedFile API expects already bounded inventories from its
caller. This is static inspection, not a security sandbox or proof of behavior.

## Tests and dependencies

Uses unidiff>=1.0.1,<2 for the actual unified-diff parser, with the existing
Pydantic and Tree-sitter extraction contracts. It does not reimplement unidiff.

From backend:

```powershell
python -m pip install "unidiff>=1.0.1,<2"
python -m pytest tests/unit/test_diff_parser.py tests/unit/test_symbol_mapper.py tests/unit/test_diff_symbol_integration.py -q -rs
python -m pytest tests -q -rs
```

83 authored cases: 26 diff-parser, 41 mapper/contract, 16 real parser integration.
In the build environment, 47 dependency-independent mapper/parser-helper cases
passed. The 20 actual unidiff parser cases and 16 unidiff/Tree-sitter integration
cases could not run there because those packages were unavailable. Run all
three files locally before marking Day 11 Track 1 verified. No database or API
keys are needed for these new tests. This feature does not complete the other
Day 11 tracks, PR fetching, API persistence or downstream impact traversal.
