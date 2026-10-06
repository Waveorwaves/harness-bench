"""Turning log lines into entries."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re

LINE = re.compile(r"^(\S+) (GET|POST|PUT|PATCH|DELETE) (\S+) (\d{3}) (\d+)ms$")


@dataclass(frozen=True)
class Entry:
    time: datetime
    method: str
    path: str
    status: int
    duration_ms: int


def parse_time(text):
    """An aware datetime; a time written without an offset is taken as UTC."""
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def parse_line(line):
    match = LINE.match(line.strip())
    if not match:
        raise ValueError(f"not a log line: {line.strip()!r}")
    time, method, path, status, duration = match.groups()
    return Entry(parse_time(time), method, path, int(status), int(duration))


def read(lines, strict=False):
    """Parse lines into entries.

    Returns (entries, skipped_count, bad_line_info).
    bad_line_info is (line_number, line_text) if strict and a bad line is found, else None.
    """
    entries = []
    skipped = 0
    line_number = 0

    for line in lines:
        line_number += 1
        if not line.strip():
            # Blank lines are counted but not considered bad
            continue
        try:
            entries.append(parse_line(line))
        except ValueError:
            if strict:
                return entries, skipped, (line_number, line.rstrip('\n'))
            skipped += 1

    return entries, skipped, None
