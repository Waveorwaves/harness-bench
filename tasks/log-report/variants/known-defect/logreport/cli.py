"""Command line."""

import argparse
import json
import sys
from datetime import datetime, timezone

from .parse import read, parse_time
from .stats import status_classes, top_paths, get_path_stats, percentile


def main(argv=None):
    parser = argparse.ArgumentParser(prog="logreport", description="Summarise an access log.")
    parser.add_argument("log", help="path of the access log")
    parser.add_argument("--top", type=int, default=5, help="how many paths to list (default 5)")
    parser.add_argument("--strict", action="store_true", help="exit on first bad line")
    parser.add_argument("--since", help="minimum time (ISO 8601, UTC if no offset)")
    parser.add_argument("--until", help="maximum time (ISO 8601, UTC if no offset)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="output format")
    args = parser.parse_args(argv)

    # Parse time bounds
    since_time = None
    until_time = None

    if args.since:
        try:
            since_time = parse_time(args.since)
        except (ValueError, TypeError):
            print(f"logreport: invalid --since time: {args.since}", file=sys.stderr)
            return 2

    if args.until:
        try:
            until_time = parse_time(args.until)
        except (ValueError, TypeError):
            print(f"logreport: invalid --until time: {args.until}", file=sys.stderr)
            return 2

    try:
        with open(args.log, encoding="utf-8") as handle:
            entries, skipped, bad_line_info = read(handle, strict=args.strict)
    except OSError as error:
        print(f"logreport: {error}", file=sys.stderr)
        return 1

    if bad_line_info:
        line_number, line_text = bad_line_info
        print(f"line {line_number}: {line_text}", file=sys.stderr)
        return 2

    # Filter entries by time window
    filtered_entries = []
    for entry in entries:
        if since_time and entry.time < since_time:
            continue
        if until_time and entry.time >= until_time:
            continue
        filtered_entries.append(entry)

    if args.format == "json":
        return output_json(filtered_entries, skipped, since_time, until_time, args.top)
    else:
        return output_text(filtered_entries, skipped, args.top)


def output_text(entries, skipped, top_limit):
    """Output text format report."""
    print(f"total: {len(entries)}")
    print(f"skipped: {skipped}")

    for name, count in status_classes(entries).items():
        print(f"{name}: {count}")

    print("top paths:")
    path_stats = get_path_stats(entries)

    for path, count in top_paths(entries, top_limit):
        stats = path_stats[path]
        p50 = percentile(stats["durations"], 50)
        p95 = percentile(stats["durations"], 95)
        errors = stats["errors"]
        print(f"  {path} {count} p50={p50}ms p95={p95}ms errors={errors}")

    return 0


def output_json(entries, skipped, since_time, until_time, top_limit):
    """Output JSON format report."""
    path_stats = get_path_stats(entries)

    # Build paths list in the same order as top_paths
    paths_list = []
    for path, count in top_paths(entries, top_limit):
        stats = path_stats[path]
        p50 = percentile(stats["durations"], 50)
        p95 = percentile(stats["durations"], 95)
        p99 = percentile(stats["durations"], 99)
        errors = stats["errors"]

        paths_list.append({
            "path": path,
            "count": count,
            "errors": errors,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
        })

    # Format times
    since_str = None
    until_str = None
    if since_time:
        since_str = since_time.isoformat()
    if until_time:
        until_str = until_time.isoformat()

    report = {
        "total": len(entries),
        "skipped": skipped,
        "since": since_str,
        "until": until_str,
        "status": status_classes(entries),
        "paths": paths_list,
    }

    print(json.dumps(report))
    return 0
