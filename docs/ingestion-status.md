# Ingestion implementation status

## Implemented scope

A synchronous clone-and-scan workflow is available through:

`reposcope.ingestion.pipeline.clone_and_scan_repository`

It:

1. Clones into a new destination inside a supplied trusted workspace.
2. Uses Git shallow depth 1 and per-command hook suppression.
3. Runs the existing scanner on the cloned repository.
4. Returns the repository path and scanned-file records.

The scanner records relative paths, absolute paths, extensions,
SHA-256 content hashes, and byte counts for supported files.

## Validation

The integration tests exercise:

- A real local clone followed by real file scanning.
- Shallow history and source/clone HEAD agreement.
- Known hashes, byte counts, sorted paths, and excluded files.
- Clone failure preventing scanning.
- Scan failure preserving the completed clone.

Run from `backend`:

```powershell
python -m pytest tests/integration/test_ingestion_pipeline.py -v
```

Record the actual result and platform after running the tests.
Do not describe unexecuted tests as passed.

## Ownership and lifecycle

- Clone failures use the clone module's cleanup handling.
- Successful clones remain on disk.
- A scan exception raises PipelineError and retains the clone.
- The caller/operator owns retention and later cleanup.
- The workspace must be service-controlled and private.
- Filesystem checks are not an atomic defense against concurrent
  directory replacement.

## Not implemented by this workflow

- Repository-registration integration.
- Background job creation or execution.
- Database persistence.
- Symbol parsing, graph construction, or indexing.
- Retrieval, embeddings, or LLM processing.
- A complete safety audit of the scanner.

Repository registration remains mock-only and must not claim to enqueue
a real ingestion job.

## Milestone wording

Minimal synchronous clone-to-scan workflow implemented.
Its integration test must pass before calling the workflow verified.

This is not end-to-end application ingestion.