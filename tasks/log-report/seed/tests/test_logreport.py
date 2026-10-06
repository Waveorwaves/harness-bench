import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from logreport.cli import main
from logreport.parse import parse_line
from logreport.stats import status_classes, top_paths

LOG = """\
2026-03-01T12:00:03+00:00 GET /api/items 200 123ms
2026-03-01T12:00:04+00:00 GET /health 200 2ms
2026-03-01T12:00:09+00:00 POST /api/items 201 340ms

2026-03-01T12:01:00+00:00 GET /api/items 500 900ms
2026-03-01T12:01:30+00:00 GET /health 404 1ms
"""


class LogReportTests(unittest.TestCase):
    def run_cli(self, *arguments):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "access.log"
            log.write_text(LOG)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([str(log), *arguments])
        return code, output.getvalue()

    def test_parse_line(self):
        entry = parse_line("2026-03-01T12:00:03 GET /api/items 200 123ms")
        self.assertEqual((entry.method, entry.path, entry.status, entry.duration_ms), ("GET", "/api/items", 200, 123))
        self.assertEqual(entry.time.utcoffset().total_seconds(), 0)
        with self.assertRaises(ValueError):
            parse_line("nonsense")

    def test_counts(self):
        entries = [parse_line(line) for line in LOG.splitlines() if line]
        self.assertEqual(status_classes(entries), {"2xx": 3, "3xx": 0, "4xx": 1, "5xx": 1})
        self.assertEqual(top_paths(entries, 5), [("/api/items", 3), ("/health", 2)])

    def test_report(self):
        code, text = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(text, "total: 5\n2xx: 3\n3xx: 0\n4xx: 1\n5xx: 1\ntop paths:\n  /api/items 3\n  /health 2\n")
        self.assertTrue(self.run_cli("--top", "1")[1].endswith("top paths:\n  /api/items 3\n"))


if __name__ == "__main__":
    unittest.main()
