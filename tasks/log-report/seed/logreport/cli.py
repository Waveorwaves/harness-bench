"""Command line."""

import argparse
import sys

from .parse import read
from .stats import status_classes, top_paths


def main(argv=None):
    parser = argparse.ArgumentParser(prog="logreport", description="Summarise an access log.")
    parser.add_argument("log", help="path of the access log")
    parser.add_argument("--top", type=int, default=5, help="how many paths to list (default 5)")
    args = parser.parse_args(argv)

    try:
        with open(args.log, encoding="utf-8") as handle:
            entries = read(handle)
    except OSError as error:
        print(f"logreport: {error}", file=sys.stderr)
        return 1

    print(f"total: {len(entries)}")
    for name, count in status_classes(entries).items():
        print(f"{name}: {count}")
    print("top paths:")
    for path, count in top_paths(entries, args.top):
        print(f"  {path} {count}")
    return 0
