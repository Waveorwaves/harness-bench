"""Hidden acceptance checks. Runs the tool as a user would (python3 -m logreport ...) on logs the
agent never saw, and calls percentile directly. Every expectation is in the prompt or the README."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

checks = []
scratch = Path(tempfile.mkdtemp())


def check(name, body):
    try:
        body()
        checks.append({"name": name, "passed": True})
    except Exception as error:  # a broken tool must fail its checks, not the evaluator
        checks.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:400]})


def run(log, *arguments):
    path = scratch / "access.log"
    path.write_text(log, encoding="utf-8")
    done = subprocess.run([sys.executable, "-B", "-m", "logreport", str(path), *arguments],
                          capture_output=True, text=True, timeout=30)
    return done.returncode, done.stdout, done.stderr


def report(log, *arguments):
    code, out, err = run(log, "--format", "json", *arguments)
    assert code == 0, f"exit {code}: {err.strip()[:200]}"
    return json.loads(out)


def same(actual, expected, what=""):
    assert actual == expected, f"{what} expected {expected!r}, got {actual!r}"


DAY = """\
2026-03-01T09:00:00+00:00 GET /api/items 200 100ms
2026-03-01T10:00:00+00:00 GET /api/items 200 300ms
2026-03-01T11:00:00+00:00 POST /api/items 503 900ms
2026-03-01T12:00:00+00:00 GET /health 200 2ms
2026-03-01T13:00:00+00:00 GET /health 404 4ms
2026-03-01T14:00:00+00:00 DELETE /api/items/7 204 50ms
"""


def percentile_checks():
    sys.path.insert(0, os.getcwd())
    from logreport.stats import percentile
    same(percentile([10, 20, 30, 40], 50), 20)
    same(percentile([10, 20, 30, 40], 25), 10)
    same(percentile([10, 20, 30, 40], 26), 20)
    same(percentile([10, 20, 30, 40], 95), 40)
    same(percentile([10, 20, 30, 40], 100), 40)
    same(percentile([10, 20, 30, 40], 1), 10)
    same(percentile([7], 50), 7)
    same(percentile([900, 100, 300], 50), 300, "unsorted input:")
    same(percentile(list(range(1, 101)), 95), 95)
    same(percentile(list(range(1, 101)), 99), 99)
    same(percentile([5, 5, 5, 9], 75), 5)
    same(percentile([], 50), None)


check("percentile uses the nearest-rank method", percentile_checks)


def percentile_exact():
    # 28 / 100 * 25 is exactly 7, but floating point makes it 7.000000000000001, and a careless ceil gives 8.
    sys.path.insert(0, os.getcwd())
    from logreport.stats import percentile
    values = list(range(10, 260, 10))  # 25 values: 10, 20, ... 250
    same(percentile(values, 28), 70, "28th percentile of 25 values:")
    same(percentile(values, 56), 140, "56th percentile of 25 values:")
    same(percentile(values, 60), 150, "60th percentile of 25 values:")
    same(percentile(list(range(1, 51)), 14), 7, "14th percentile of 50 values:")


check("percentile is exact where the rank is a whole number", percentile_exact)


def bad_lines():
    log = ("2026-03-01T09:00:00+00:00 GET /a 200 10ms\n"
           "\n"
           "this is not a log line\n"
           "2026-03-01T09:00:01+00:00 FETCH /a 200 10ms\n"
           "2026-03-01T09:00:02+00:00 GET /a 200 ten\n"
           "   \n"
           "2026-03-01T09:00:03+00:00 GET /a 200 30ms\n")
    data = report(log)
    same((data["total"], data["skipped"]), (2, 3))


check("bad lines are skipped and counted, blank lines are not", bad_lines)


def impossible_times():
    log = ("2026-02-30T09:00:00+00:00 GET /a 200 10ms\n"
           "2026-03-01T25:00:00+00:00 GET /a 200 10ms\n"
           "yesterday GET /a 200 10ms\n"
           "2026-03-01T09:00:03+00:00 GET /a 200 30ms\n")
    data = report(log)
    same((data["total"], data["skipped"]), (1, 3))


check("a line with an impossible time is a bad line", impossible_times)


def strict():
    log = "2026-03-01T09:00:00+00:00 GET /a 200 10ms\n\n\nbroken line here\n2026-03-01T09:00:03+00:00 GET /a 200 30ms\nalso broken\n"
    code, out, err = run(log, "--strict")
    same(code, 2, "exit code:")
    assert "line 4: broken line here" in err, f"standard error was {err!r}"
    assert "also broken" not in err, "only the first bad line should be reported"
    code, _, _ = run(DAY, "--strict")
    same(code, 0, "exit code for a clean log:")


check("--strict stops at the first bad line with its number", strict)


def window_edges():
    data = report(DAY, "--since", "2026-03-01T10:00:00+00:00", "--until", "2026-03-01T13:00:00+00:00")
    same(data["total"], 3, "since is inclusive and until exclusive:")
    same(report(DAY, "--since", "2026-03-01T13:00:00+00:00")["total"], 2, "since alone:")
    same(report(DAY, "--until", "2026-03-01T09:00:00+00:00")["total"], 0, "until alone:")
    same(report(DAY, "--until", "2026-03-01T09:00:01+00:00")["total"], 1)


check("--since is inclusive and --until is exclusive", window_edges)


def instants():
    same(report(DAY, "--since", "2026-03-01T13:00:00+02:00")["total"], 4, "+02:00 option:")
    same(report(DAY, "--since", "2026-03-01T11:00:00")["total"], 4, "option without offset is UTC:")
    same(report(DAY, "--until", "2026-03-01T05:30:00-05:00")["total"], 2, "-05:00 option:")
    mixed = ("2026-03-01T12:30:00+02:00 GET /a 200 10ms\n"      # 10:30 UTC
             "2026-03-01T06:45:00-04:00 GET /b 200 10ms\n"      # 10:45 UTC
             "2026-03-01T11:15:00 GET /c 200 10ms\n")           # 11:15 UTC
    data = report(mixed, "--since", "2026-03-01T10:40:00+00:00", "--until", "2026-03-01T11:00:00+00:00")
    same([row["path"] for row in data["paths"]], ["/b"], "log times with offsets:")


check("times are compared as instants, whatever their offsets", instants)


def bad_option():
    for value in ("yesterday", "2026-13-01T00:00:00", ""):
        code, _, err = run(DAY, "--since", value)
        same(code, 2, f"exit code for --since {value!r}:")
        assert err.strip(), "nothing was printed to standard error"
    code, _, err = run(DAY, "--until", "noon")
    same(code, 2, "exit code for --until noon:")


check("an unreadable --since or --until ends with exit code 2", bad_option)


def window_scope():
    log = DAY + "garbage\n"
    data = report(log, "--since", "2026-03-01T11:00:00+00:00", "--until", "2026-03-01T14:00:00+00:00")
    same(data["status"], {"2xx": 1, "3xx": 0, "4xx": 1, "5xx": 1}, "status counts inside the window:")
    same(data["skipped"], 1, "skipped covers the whole file:")
    same([(row["path"], row["count"], row["errors"]) for row in data["paths"]], [("/health", 2, 0), ("/api/items", 1, 1)])
    empty = report(log, "--since", "2027-01-01T00:00:00")
    same((empty["total"], empty["paths"], empty["status"], empty["skipped"]), (0, [], {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}, 1))


check("the window applies to totals, status counts and paths, but not to skipped", window_scope)


def json_shape():
    data = report(DAY)
    same(sorted(data), sorted(["total", "skipped", "since", "until", "status", "paths"]), "keys:")
    same((data["total"], data["skipped"], data["since"], data["until"]), (6, 0, None, None))
    same(data["status"], {"2xx": 4, "3xx": 0, "4xx": 1, "5xx": 1})
    same(data["paths"], [
        {"path": "/api/items", "count": 3, "errors": 1, "p50_ms": 300, "p95_ms": 900, "p99_ms": 900},
        {"path": "/health", "count": 2, "errors": 0, "p50_ms": 2, "p95_ms": 4, "p99_ms": 4},
        {"path": "/api/items/7", "count": 1, "errors": 0, "p50_ms": 50, "p95_ms": 50, "p99_ms": 50},
    ])


check("--format json has the documented shape and values", json_shape)


def json_window_echo():
    data = report(DAY, "--since", "2026-03-01T13:00:00+02:00", "--until", "2026-03-01T15:00:00")
    same((data["since"], data["until"]), ("2026-03-01T11:00:00+00:00", "2026-03-01T15:00:00+00:00"))


check("JSON repeats since and until in UTC", json_window_echo)


def ordering_and_top():
    log = "".join(f"2026-03-01T09:00:{second:02d}+00:00 GET {path} 200 {second + 1}ms\n"
                  for second, path in enumerate(["/b", "/a", "/c", "/b", "/a", "/d", "/c", "/e", "/c"]))
    same([(row["path"], row["count"]) for row in report(log)["paths"]],
         [("/c", 3), ("/a", 2), ("/b", 2), ("/d", 1), ("/e", 1)])
    same([row["path"] for row in report(log, "--top", "2")["paths"]], ["/c", "/a"])
    seven = "".join(f"2026-03-01T09:00:0{n}+00:00 GET /p{n} 200 1ms\n" for n in range(7))
    same(len(report(seven)["paths"]), 5, "default --top:")


check("paths are ordered by count then name, and --top limits them", ordering_and_top)


def errors_are_5xx():
    log = "".join(f"2026-03-01T09:00:0{n}+00:00 GET /x {status} 5ms\n"
                  for n, status in enumerate([200, 301, 404, 499, 500, 502, 599]))
    row = report(log)["paths"][0]
    same((row["count"], row["errors"]), (7, 3))


check("errors counts only 5xx responses", errors_are_5xx)


def percentiles_per_path():
    durations = [12, 250, 31, 47, 1900, 8, 77, 64, 55, 120, 43, 39, 610, 28, 91, 15, 33, 70, 505, 22]
    log = "".join(f"2026-03-01T09:{n:02d}:00+00:00 GET /slow 200 {ms}ms\n" for n, ms in enumerate(durations))
    log += "2026-03-01T10:00:00+00:00 GET /fast 200 1ms\n"
    rows = {row["path"]: row for row in report(log)["paths"]}
    same((rows["/slow"]["p50_ms"], rows["/slow"]["p95_ms"], rows["/slow"]["p99_ms"]), (47, 610, 1900))
    same((rows["/fast"]["p50_ms"], rows["/fast"]["p95_ms"], rows["/fast"]["p99_ms"]), (1, 1, 1))


check("percentiles are computed per path", percentiles_per_path)


def text_report():
    code, out, _ = run(DAY + "nonsense\n")
    same(code, 0, "exit code:")
    same(out, "total: 6\nskipped: 1\n2xx: 4\n3xx: 0\n4xx: 1\n5xx: 1\ntop paths:\n"
              "  /api/items 3 p50=300ms p95=900ms errors=1\n"
              "  /health 2 p50=2ms p95=4ms errors=0\n"
              "  /api/items/7 1 p50=50ms p95=50ms errors=0\n")
    code, out, _ = run(DAY, "--format", "text", "--top", "1", "--since", "2026-03-01T12:00:00")
    same(out, "total: 3\nskipped: 0\n2xx: 2\n3xx: 0\n4xx: 1\n5xx: 0\ntop paths:\n  /health 2 p50=2ms p95=4ms errors=0\n")
    code, out, _ = run("")
    same(out, "total: 0\nskipped: 0\n2xx: 0\n3xx: 0\n4xx: 0\n5xx: 0\ntop paths:\n", "empty log:")


check("the text report has the new skipped line and path details", text_report)


def old_behaviour():
    code, _, err = run(DAY)
    same(code, 0)
    done = subprocess.run([sys.executable, "-B", "-m", "logreport", str(scratch / "missing.log")], capture_output=True, text=True, timeout=30)
    same(done.returncode, 1, "exit code for a missing file:")
    assert done.stderr.strip(), "a missing file should be reported on standard error"
    sys.path.insert(0, os.getcwd())
    from logreport.parse import parse_line
    entry = parse_line("2026-03-01T12:00:03 PATCH /api/items/3 200 123ms")
    same((entry.method, entry.path, entry.status, entry.duration_ms), ("PATCH", "/api/items/3", 200, 123))
    same(entry.time.utcoffset().total_seconds(), 0)


check("earlier behaviour is unchanged", old_behaviour)

Path(os.environ["HB_OUT"], "result.json").write_text(json.dumps({"checks": checks}, indent=2))
