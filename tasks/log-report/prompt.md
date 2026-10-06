Extend the `logreport` tool. `README.md` describes what it does today.

## 1. Bad lines no longer stop the report

A line that does not match the format, including one whose time is not a real date and time, is skipped and counted. Blank lines are ignored and are not counted.

With the new option `--strict`, the first bad line ends the run instead: exit code 2, and `line N: ` followed by that line printed to standard error, where N is its line number in the file counting from 1 (blank lines included).

## 2. Time window

New options `--since TIME` and `--until TIME` keep only entries with `since <= time < until`. Either can be given alone. TIME is ISO 8601 and, like times in the log, is UTC when it has no offset. Times are compared as instants, so `2026-03-01T13:00:00+02:00` is the same moment as `2026-03-01T11:00:00+00:00`. A TIME that cannot be read ends the run with exit code 2 and a message on standard error.

The window applies to everything reported about entries. The count of skipped lines always covers the whole file.

## 3. Percentiles

Add `percentile(values, p)` to `logreport/stats.py`, using the nearest-rank method: sort the values in ascending order and return the one at position `ceil(p / 100 * n)`, counting from 1, where `n` is how many values there are. `p` is a whole number between 1 and 100. With no values the result is `None`.

The position must be exact. For 25 values the 28th percentile is the 7th value, because 28 / 100 × 25 is exactly 7, even though floating-point arithmetic makes it slightly more.

## 4. The text report

After `total:` comes a new line `skipped: N`. Each path line becomes

```
  <path> <count> p50=<ms>ms p95=<ms>ms errors=<n>
```

where the percentiles are of that path's durations and `errors` is how many of its responses had a 5xx status. For example:

```
total: 5
skipped: 0
2xx: 3
3xx: 0
4xx: 1
5xx: 1
top paths:
  /api/items 3 p50=340ms p95=900ms errors=1
  /health 2 p50=1ms p95=2ms errors=0
```

The order of paths and `--top` work as before.

## 5. JSON output

New option `--format json` (the default is `--format text`) prints one JSON object instead:

```json
{
  "total": 5,
  "skipped": 0,
  "since": null,
  "until": null,
  "status": {"2xx": 3, "3xx": 0, "4xx": 1, "5xx": 1},
  "paths": [
    {"path": "/api/items", "count": 3, "errors": 1, "p50_ms": 340, "p95_ms": 900, "p99_ms": 900},
    {"path": "/health", "count": 2, "errors": 0, "p50_ms": 1, "p95_ms": 2, "p99_ms": 2}
  ]
}
```

`since` and `until` repeat the options converted to UTC in the form `2026-03-01T11:00:00+00:00`, or are `null` when not given. `paths` follows the same order and `--top` limit as the text report.

Standard library only. Update the existing tests for the new text format; `python3 -m unittest discover -s tests` must pass.
