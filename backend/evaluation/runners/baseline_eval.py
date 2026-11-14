"""Run B0: python evaluation/runners/baseline_eval.py --documents ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reposcope.evaluation.baseline import build_baseline_index, recall_at_k, search_baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline vector-only B0 benchmark")
    parser.add_argument("--documents", required=True, help="JSON array of {source, text}")
    parser.add_argument("--queries", required=True, help="JSON array of {query, relevant_chunk_ids}")
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    documents = json.loads(Path(args.documents).read_text(encoding="utf-8"))
    queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    index = build_baseline_index(
        [(item["source"], item["text"]) for item in documents],
        chunk_size=args.chunk_size,
    )
    from reposcope.retrieval.embeddings import embed_query

    report = {
        "baseline": "B0",
        "method": "fixed-size chunks + vector search",
        "chunk_size": args.chunk_size,
        "chunk_count": len(index.chunks),
        "recall_at_k": recall_at_k(
            index,
            [(item["query"], set(item["relevant_chunk_ids"])) for item in queries],
            embed_query=embed_query,
            k=args.k,
        ),
    }
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
