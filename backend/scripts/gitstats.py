"""Run from backend: python -m scripts.gitstats LOCAL_REPO [--persist --repository-id ID].

Default is read-only JSON output. --persist explicitly writes git_stats and
commits; run the migration first. This command never fetches history.
"""
import argparse
from dataclasses import asdict
from datetime import datetime
import json
from reposcope.ingestion.gitstats import collect_git_stats, persist_git_stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_path")
    parser.add_argument("--as-of", help="Timezone-aware ISO 8601 timestamp")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--max-commits", type=int, default=20000)
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--repository-id", type=int)
    args = parser.parse_args()
    if args.persist and (args.repository_id is None or args.repository_id < 1):
        parser.error("--persist requires a positive --repository-id")
    options = dict(timeout_seconds=args.timeout, max_commits=args.max_commits)
    if args.as_of:
        options["as_of"] = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    report = collect_git_stats(args.repository_path, **options)
    if args.persist:
        from reposcope.db.session import SessionLocal
        with SessionLocal() as session:
            persist_git_stats(session, args.repository_id, report)
            session.commit()
    print(json.dumps(asdict(report), default=lambda value: value.isoformat(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
