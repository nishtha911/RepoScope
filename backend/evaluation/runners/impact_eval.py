"""Run from backend: python evaluation/runners/impact_eval.py --help."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from reposcope.evaluation.impact import (
    EvaluationError, changed_files_baseline, evaluate, read_json,
    validate_dataset, write_results,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline PR-impact benchmark; never runs repository code")
    parser.add_argument("command", choices=["validate", "score", "baseline"])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--predictions")
    parser.add_argument("--out")
    parser.add_argument("--require-ready", action="store_true", help="Require 30 reviewed PRs with complete file labels and head test runs")
    args = parser.parse_args(argv)
    try:
        dataset = read_json(args.dataset)
        inventory = validate_dataset(dataset, require_ready=args.require_ready)
        if args.command == "validate":
            print(json.dumps(inventory, sort_keys=True))
            return 0
        if not args.out:
            raise EvaluationError("--out is required for scoring")
        if args.command == "score" and not args.predictions:
            raise EvaluationError("score requires --predictions")
        predictions = (read_json(args.predictions) if args.command == "score"
                       else changed_files_baseline(dataset))
        report = evaluate(dataset, predictions, require_ready=args.require_ready)
        write_results(report, args.out)
        print(json.dumps({"inventory": inventory, "prediction_counts": report["prediction_counts"], "aggregates": report["aggregates"]}, sort_keys=True))
        return 0 if all(r["status"] == "ok" for r in predictions["predictions"]) and report["prediction_counts"]["missing"] == 0 else 2
    except (EvaluationError, OSError, ValueError) as exc:
        print(f"impact-eval: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
