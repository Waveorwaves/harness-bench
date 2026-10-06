"""Counting."""

from collections import Counter
from fractions import Fraction
import math

CLASSES = ("2xx", "3xx", "4xx", "5xx")


def status_classes(entries):
    counts = dict.fromkeys(CLASSES, 0)
    for entry in entries:
        name = f"{entry.status // 100}xx"
        if name in counts:
            counts[name] += 1
    return counts


def top_paths(entries, limit):
    counts = Counter(entry.path for entry in entries)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


def percentile(values, p):
    """Nearest rank: the value at position ceil(p / 100 * n) of the sorted values, counting from 1."""
    if not values:
        return None
    ordered = sorted(values)
    # Fractions, not floats: 28 / 100 * 25 is 7.000000000000001 in floating point, which would round up to 8.
    return ordered[max(1, math.ceil(Fraction(p) / 100 * len(ordered))) - 1]


def in_window(entries, since=None, until=None):
    return [entry for entry in entries
            if (since is None or entry.time >= since) and (until is None or entry.time < until)]


def path_report(entries, limit):
    rows = []
    for path, count in top_paths(entries, limit):
        mine = [entry for entry in entries if entry.path == path]
        durations = [entry.duration_ms for entry in mine]
        rows.append({"path": path, "count": count, "errors": sum(500 <= entry.status <= 599 for entry in mine),
                     "p50_ms": percentile(durations, 50), "p95_ms": percentile(durations, 95),
                     "p99_ms": percentile(durations, 99)})
    return rows
