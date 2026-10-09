# Day 3 symbol-chunking policy

Date: 9 October 2026

Status: Implemented and locally tested.
Teammate policy acknowledgment, PR review, and merge remain pending.

## Interface

```python
build_symbol_chunks(parsed_file: ParsedFile) -> list[ChunkDraft]
```

The chunker consumes Track 1's shared ParsedFile and ParsedSymbol models.
The existing parser contracts and persisted Chunk contract are unchanged.

## Chunk eligibility

Option A v1 produces one chunk per class, function, or method definition.

Modules remain file context.
Parameters remain metadata attached to their callable.
No standalone module or parameter chunks are generated.

## Header and body

The header is JSON containing:

- file_path
- qualname
- kind
- signature
- docstring

Missing metadata remains JSON null.
An actual empty docstring remains an empty string.

The body is the exact UTF-8 slice described by the parser's content range.
It includes decorators and first-line indentation.
It does not automatically append a trailing newline.

Final text is:

header_text + "\n\n--- SOURCE ---\n" + body_text

Synthetic header lines are not source-file line numbers.

## Completeness and overlap

Functions are not split or truncated to satisfy a token target.
Oversized definitions remain complete drafts.

Class chunks include their methods; methods also receive individual chunks.
Outer-function chunks include nested definitions; nested definitions also
receive individual chunks.

This overlap is intentional.

Completeness depends on correct parser-supplied source ranges.
The chunker revalidates parser metadata and does not reopen source files.

## Identity and persistence

Drafts carry parser-local symbol keys and source hashes, not database IDs.

Hashes do not independently establish snapshot identity.
Persisted Chunk creation requires verified snapshot/file/symbol mappings
through a separate adapter.

No database writes, embeddings, retrieval, or LLM calls occur here.

## Recorded local validation

Platform: Windows
Python: 3.11.9

Command, run from backend:

```powershell
python -m pytest tests/unit tests/integration -q --tb=short --maxfail=1
```

User-reported result:

446 passed in 67.72 seconds.

This is a local backend regression result, not CI or application
end-to-end verification.

## Review

Track 1 should review parser-to-chunker compatibility.
The shared ChunkDraft and header/overlap policy require acknowledgment.
Record the implementation commit and review reference when available.