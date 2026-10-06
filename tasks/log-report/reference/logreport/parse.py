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


class BadLine(ValueError):
    """A line that is not a log entry. `number` counts lines from 1."""

    def __init__(self, number, text):
        super().__init__(f"line {number}: {text}")
        self.number, self.text = number, text


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
    """Returns (entries, number of bad lines skipped). With strict, the first bad line raises BadLine."""
    entries, skipped = [], 0
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entries.append(parse_line(line))
        except ValueError:
            if strict:
                raise BadLine(number, line.rstrip("\r\n")) from None
            skipped += 1
    return entries, skipped
