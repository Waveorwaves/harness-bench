"""Counting."""

from collections import Counter, defaultdict
import math

CLASSES = ("2xx", "3xx", "4xx", "5xx")


def percentile(values, p):
    """Compute percentile using nearest-rank method.

    Returns the value at position ceil(p / 100 * n), counting from 1.
    Returns None if there are no values.
    """
    if not values:
        return None
    sorted_values = sorted(values)
    n = len(sorted_values)
    position = math.ceil(p / 100 * n) - 1  # Convert to 0-indexed
    return sorted_values[position]


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


def get_path_stats(entries):
    """Get stats for each path: count, durations, errors.

    Returns a dict: {path: {"count": int, "durations": [int], "errors": int}}
    """
    stats = defaultdict(lambda: {"count": 0, "durations": [], "errors": 0})
    for entry in entries:
        path_stat = stats[entry.path]
        path_stat["count"] += 1
        path_stat["durations"].append(entry.duration_ms)
        if entry.status >= 500:
            path_stat["errors"] += 1
    return stats
