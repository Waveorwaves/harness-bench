"""Counting."""

from collections import Counter

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
