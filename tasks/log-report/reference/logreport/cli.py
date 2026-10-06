"""Command line."""

import argparse
from datetime import timezone
import json
import sys

from .parse import BadLine, parse_time, read
from .stats import in_window, path_report, status_classes


def moment(text):
    try:
        return parse_time(text).astimezone(timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a time: {text!r}") from None


def main(argv=None):
    parser = argparse.ArgumentParser(prog="logreport", description="Summarise an access log.")
    parser.add_argument("log", help="path of the access log")
    parser.add_argument("--top", type=int, default=5, help="how many paths to list (default 5)")
    parser.add_argument("--since", type=moment, help="keep entries at or after this time")
    parser.add_argument("--until", type=moment, help="keep entries before this time")
    parser.add_argument("--strict", action="store_true", help="stop at the first bad line")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        with open(args.log, encoding="utf-8") as handle:
            entries, skipped = read(handle, strict=args.strict)
    except BadLine as error:
        print(error, file=sys.stderr)
        return 2
    except OSError as error:
        print(f"logreport: {error}", file=sys.stderr)
        return 1

    entries = in_window(entries, args.since, args.until)
    paths = path_report(entries, args.top)
    if args.format == "json":
        print(json.dumps({
            "total": len(entries), "skipped": skipped,
            "since": args.since.isoformat() if args.since else None,
            "until": args.until.isoformat() if args.until else None,
            "status": status_classes(entries), "paths": paths,
        }, indent=2))
        return 0
    print(f"total: {len(entries)}")
    print(f"skipped: {skipped}")
    for name, count in status_classes(entries).items():
        print(f"{name}: {count}")
    print("top paths:")
    for row in paths:
        print(f"  {row['path']} {row['count']} p50={row['p50_ms']}ms p95={row['p95_ms']}ms errors={row['errors']}")
    return 0
