"""Every task in the repository must have a failing seed and a passing reference."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from harness_bench import runner, sandbox, tasks

ROOT = Path(__file__).resolve().parents[1]
TASKS = sorted(path.parent.name for path in (ROOT / "tasks").glob("*/task.json"))


class TaskTests(unittest.TestCase):
    def test_every_task_validates(self):
        self.assertGreaterEqual(len(TASKS), 11)
        box = sandbox.make("local")
        for name in TASKS:
            entry = {"id": name, "spec": f"tasks/{name}"}
            task = tasks.load(ROOT, entry)
            command = json.loads((ROOT / "tasks" / name / "task.json").read_text())["evaluator_command"]
            with self.subTest(task=name):
                if command.startswith("node") and not shutil.which("node"):
                    self.skipTest("node is not installed")
                if task.capture and not os.environ.get("HB_BROWSER") and not shutil.which("chromium"):
                    self.skipTest("no browser for capture: set HB_BROWSER")
                verdict = runner.validate_task(ROOT, entry, box)
                passed, total = map(int, verdict["reference"].split("/"))
                self.assertEqual(passed, total)
                self.assertGreaterEqual(total, 7)

    def test_known_defects_fail_exactly_the_checks_they_should(self):
        """Real flawed attempts kept with each task: the hidden checks must keep catching them, and only them."""
        box = sandbox.make("local")
        fixtures = sorted((ROOT / "tasks").glob("*/variants/*/expected.json"))
        self.assertGreaterEqual(len(fixtures), 6)
        for expected in fixtures:
            task_directory = expected.parents[2]
            task = tasks.load(ROOT, {"id": task_directory.name, "spec": f"tasks/{task_directory.name}"})
            with self.subTest(task=task.id, variant=expected.parent.name), tempfile.TemporaryDirectory() as scratch:
                if task.command.startswith("node") and not shutil.which("node"):
                    self.skipTest("node is not installed")
                if task.capture and not os.environ.get("HB_BROWSER") and not shutil.which("chromium"):
                    self.skipTest("no browser for capture: set HB_BROWSER")
                workspace = Path(scratch) / "workspace"
                shutil.copytree(task.seed, workspace)
                shutil.copytree(expected.parent, workspace, dirs_exist_ok=True)
                checks, error = runner.grade(ROOT, task_directory, workspace, box)
                self.assertIsNone(error)
                self.assertEqual(sorted(check["name"] for check in checks if not check["passed"]),
                                 sorted(json.loads(expected.read_text())["fails"]))

    def test_prompts_do_not_leak_evaluators(self):
        for name in TASKS:
            prompt = (ROOT / "tasks" / name / "prompt.md").read_text()
            self.assertNotIn("evaluator", prompt.lower(), name)
            self.assertFalse((ROOT / "tasks" / name / "seed" / "check.py").exists(), name)
            self.assertFalse((ROOT / "tasks" / name / "seed" / "check.mjs").exists(), name)


if __name__ == "__main__":
    unittest.main()
