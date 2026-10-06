"""Synthetic records below are validation fixtures, never benchmark measurements."""

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from harness_bench.__main__ import main
from harness_bench.core import make_plan, report, validate_results

ROOT = Path(__file__).resolve().parents[1]


class BenchTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads((ROOT / "suites/pilot.json").read_text())

    def pinned(self):
        suite = copy.deepcopy(self.suite)
        for task in suite["tasks"]:
            task.update(seed_revision="synthetic-seed", evaluator_revision="synthetic-grader")
        for harness in suite["harnesses"]:
            harness["version"] = "synthetic-test-version"
        return make_plan(suite)

    def record(self, plan, **changes):
        record = dict(run_id=plan["runs"][0]["run_id"], status="passed", elapsed_seconds=8,
                      human_interventions=0, human_minutes=0, attempts=1,
                      checks_passed=2, checks_total=2, evidence_ref="synthetic-fixture",
                      cost_usd=None)
        record.update(changes)
        return record

    def test_balanced_reproducible_plan(self):
        plan = make_plan(self.suite)
        self.assertEqual(plan, make_plan(copy.deepcopy(self.suite)))
        self.assertEqual(len(plan["runs"]), 18)
        self.assertEqual(len({run["run_id"] for run in plan["runs"]}), 18)
        for i in range(0, 18, 2):
            first, second = plan["runs"][i:i + 2]
            self.assertEqual(first["task_id"], second["task_id"])
            self.assertEqual(first["repetition"], second["repetition"])
            self.assertEqual({first["harness_id"], second["harness_id"]}, {"codex", "pi"})

    def test_controlled_settings_cannot_differ(self):
        self.suite["harnesses"][0]["model"] = "different-model"
        with self.assertRaisesRegex(ValueError, "cannot override"):
            make_plan(self.suite)

    def test_duplicate_task_rejected(self):
        self.suite["tasks"].append(copy.deepcopy(self.suite["tasks"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            make_plan(self.suite)

    def test_unpinned_plan_refuses_results(self):
        plan = make_plan(self.suite)
        self.assertFalse(plan["ready"])
        self.assertEqual(len(plan["not_ready_reasons"]), 8)
        with self.assertRaisesRegex(ValueError, "pinned"):
            validate_results(plan, [self.record(plan)])

    def test_inconsistent_results_rejected(self):
        plan = self.pinned()
        changes = [dict(checks_passed=0, checks_total=0), dict(checks_passed=1),
                   dict(checks_passed=3), dict(attempts=0), dict(attempts=2),
                   dict(elapsed_seconds=None), dict(elapsed_seconds=float("nan")),
                   dict(human_interventions=True), dict(input_tokens=-1),
                   dict(cost_usd=float("inf")), dict(evidence_ref=" ")]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_results(plan, [self.record(plan, **change)])

    def test_duplicate_and_unknown_run_rejected(self):
        plan = self.pinned()
        record = self.record(plan)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_results(plan, [record, record])
        with self.assertRaisesRegex(ValueError, "unknown"):
            validate_results(plan, [self.record(plan, run_id="unknown")])

    def test_partial_report_preserves_unknown_cost_and_pending(self):
        plan = self.pinned()
        output = report(plan, [self.record(plan)])
        self.assertIn("Recorded: 1/18; pending: 17", output)
        self.assertIn("unknown", output)
        self.assertNotIn("0.0000", output)

    def test_known_zero_cost_is_distinct(self):
        plan = self.pinned()
        self.assertIn("0.0000 (1/1)", report(plan, [self.record(plan, cost_usd=0)]))

    def test_blocked_run_and_timeout_are_reported(self):
        plan = self.pinned()
        blocked = self.record(plan, status="blocked", attempts=0, elapsed_seconds=None,
                              checks_passed=0, checks_total=0)
        timeout = self.record(plan, run_id=plan["runs"][1]["run_id"], status="timed_out",
                              elapsed_seconds=900, checks_passed=0)
        self.assertIn("Recorded: 2/18; pending: 16", report(plan, [blocked, timeout]))

    def test_modified_plan_rejected(self):
        plan = self.pinned()
        plan["runs"][0]["task_id"] = "different-task"
        with self.assertRaisesRegex(ValueError, "differs"):
            report(plan, [])

    def test_cli_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            args = ["plan", "--suite", str(ROOT / "suites/pilot.json"), "--output", str(path)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 0)
                self.assertEqual(main(args), 2)
                self.assertEqual(main(["report", "--plan", str(path)]), 0)


if __name__ == "__main__":
    unittest.main()
