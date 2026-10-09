"""Pipeline tests. Every run here uses the mock agent or synthetic text; none is a measurement."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

from harness_bench import adapters, runner, sandbox
from harness_bench import site
from harness_bench.core import compare, make_plan, omnibus, report, summarize

ROOT = Path(__file__).resolve().parents[1]


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.suite = json.loads((ROOT / "suites/smoke.json").read_text())

    def test_matrix_respects_harness_modes(self):
        runs = make_plan(self.suite)["runs"]
        self.assertEqual(len(runs), 10)
        self.assertEqual(len({run["run_id"] for run in runs}), 10)
        self.assertEqual({run["mode_id"] for run in runs if run["harness_id"] == "mock-idle"}, {"single"})
        self.assertEqual({run["mode_id"] for run in runs if run["harness_id"] == "mock-solves"},
                         {"single", "subagents"})

    def test_matrix_respects_harness_models(self):
        self.suite["models"].append({"id": "second", "name": "second-model"})
        self.suite["harnesses"][1]["models"] = ["second"]
        runs = make_plan(self.suite)["runs"]
        self.assertEqual({run["model_id"] for run in runs if run["harness_id"] == "mock-idle"}, {"second"})
        self.assertEqual({run["model_id"] for run in runs if run["harness_id"] == "mock-solves"}, {"fake-model", "second"})
        self.suite["harnesses"][1]["models"] = ["missing"]
        with self.assertRaises(ValueError):
            make_plan(self.suite)

    def test_matrix_respects_harness_tasks(self):
        self.suite["tasks"].append({"id": "other", "spec": "tasks/other", "seed_revision": None, "evaluator_revision": None})
        self.suite["harnesses"][0]["tasks"] = ["other"]
        runs = make_plan(self.suite)["runs"]
        self.assertEqual({run["task_id"] for run in runs if run["harness_id"] == "mock-solves"}, {"other"})
        self.assertEqual({run["task_id"] for run in runs if run["harness_id"] == "mock-idle"}, {"smoke-slugify", "other"})

    def test_invalid_entries_rejected(self):
        for change in (lambda s: s["harnesses"][0].pop("adapter"),
                       lambda s: s["harnesses"][0].update(modes=["unknown"]),
                       lambda s: s["harnesses"][0].update(billing="free"),
                       lambda s: s["models"][0].update(price_per_mtok={"input": -1}),
                       lambda s: s["models"].append(dict(s["models"][0]))):
            suite = json.loads(json.dumps(self.suite))
            change(suite)
            with self.assertRaises(ValueError):
                make_plan(suite)


class ParserTests(unittest.TestCase):
    def parse(self, adapter, text, files=None):
        with tempfile.TemporaryDirectory() as directory:
            for name, content in (files or {}).items():
                Path(directory, name).write_text(json.dumps(content))
            return adapters.get(adapter).parse(text, Path(directory))

    def test_claude(self):
        usage = self.parse("claude", json.dumps({
            "type": "result", "total_cost_usd": 0.5, "num_turns": 4,
            "usage": {"input_tokens": 10, "cache_read_input_tokens": 90,
                      "cache_creation_input_tokens": 5, "output_tokens": 7}}))
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["cache_write_tokens"],
                          usage["output_tokens"], usage["reported_cost_usd"], usage["turns"]),
                         (10, 90, 5, 7, 0.5, 4))

    def test_claude_real_output_shape(self):
        # Keys as printed by `claude -p ... --output-format json` (Claude Code 2.1.289); values shortened.
        real = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 6, "total_cost_usd": 0.31,
                "duration_ms": 1655, "result": "done",
                "usage": {"input_tokens": 10, "cache_creation_input_tokens": 10238, "cache_read_input_tokens": 22383,
                          "output_tokens": 41, "output_tokens_details": {"thinking_tokens": 34}},
                "modelUsage": {
                    "claude-large": {"inputTokens": 10, "outputTokens": 41, "cacheReadInputTokens": 22383,
                                     "cacheCreationInputTokens": 10238, "costUSD": 0.2},
                    "claude-small": {"inputTokens": 500, "outputTokens": 900, "cacheReadInputTokens": 1000,
                                     "cacheCreationInputTokens": 0, "costUSD": 0.11}},
                "subagent_stats": {"spawned": 2, "completed": 2, "failed": 0}}
        usage = self.parse("claude", json.dumps(real))
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["cache_write_tokens"],
                          usage["output_tokens"], usage["turns"], usage["subagents"], usage["reported_cost_usd"]),
                         (510, 23383, 10238, 941, 6, 2, 0.31))

    def test_codex_separates_cached_input(self):
        lines = [{"type": "item.completed", "item": {"type": "command_execution"}},
                 {"type": "item.completed", "item": {"type": "agent_message"}},
                 {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 9}}]
        usage = self.parse("codex", "\n".join(map(json.dumps, lines)))
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["output_tokens"],
                          usage["tool_calls"], usage["reported_cost_usd"]), (40, 60, 9, 1, None))

    def test_codex_real_output_shape(self):
        # Event types and the usage object as printed by a real run (codex-cli 0.160.1); content left out.
        lines = [{"type": "thread.started"}, {"type": "turn.started"},
                 *[{"type": "item.completed", "item": {"type": kind}} for kind in
                   ("agent_message", "command_execution", "command_execution", "command_execution", "command_execution", "file_change", "agent_message")],
                 {"type": "turn.completed", "usage": {"input_tokens": 74084, "cached_input_tokens": 65152,
                                                      "cache_write_input_tokens": 0, "output_tokens": 1057, "reasoning_output_tokens": 146}}]
        usage = self.parse("codex", "\n".join(map(json.dumps, lines)))
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["cache_write_tokens"], usage["output_tokens"],
                          usage["tool_calls"], usage["turns"], usage["error"]), (8932, 65152, 0, 1057, 5, None, None))
        failed = self.parse("codex", json.dumps({"type": "turn.failed", "error": {"message": "401 Unauthorized\nmore"}}))
        self.assertEqual(failed["error"], "401 Unauthorized")

    def test_pi_reports_a_login_failure_it_exited_cleanly_from(self):
        # As printed by a real run whose Codex login had expired (Pi 1.0.4): one assistant message, an error, no tokens.
        message = {"role": "assistant", "content": [], "stopReason": "error",
                   "errorMessage": "OAuth refresh failed for openai-codex: OpenAI Codex token refresh failed (401): {\n  \"error\": {",
                   "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "cost": {"total": 0}}}
        usage = self.parse("pi", "\n".join(map(json.dumps, [{"type": "message_end", "message": {"role": "user"}},
                                                             {"type": "message_end", "message": message}])))
        self.assertEqual((usage["output_tokens"], usage["error"]),
                         (0, "OAuth refresh failed for openai-codex: OpenAI Codex token refresh failed (401): {"))

    def test_pi_sums_assistant_messages(self):
        message = {"role": "assistant", "content": [{"type": "toolCall"}, {"type": "text"}],
                   "usage": {"input": 3, "output": 2, "cacheRead": 10, "cacheWrite": 1, "cost": {"total": 0.01}}}
        lines = [{"type": "message_end", "message": {"role": "user"}},
                 {"type": "message_end", "message": message}, {"type": "message_end", "message": message}]
        usage = self.parse("omp", "\n".join(map(json.dumps, lines)))
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["output_tokens"],
                          usage["turns"], usage["tool_calls"]), (6, 20, 4, 2, 2))
        self.assertAlmostEqual(usage["reported_cost_usd"], 0.02)

    def test_hermes_reads_usage_file_and_ignores_estimates(self):
        usage = self.parse("hermes", "", {"hermes-usage.json": {
            "input_tokens": 5, "output_tokens": 6, "cache_read_tokens": 7, "api_calls": 2,
            "estimated_cost_usd": 0.3, "cost_status": "estimated"}})
        self.assertEqual((usage["input_tokens"], usage["output_tokens"], usage["cached_input_tokens"],
                          usage["turns"], usage["reported_cost_usd"]), (5, 6, 7, 2, None))

    def test_a_provider_refusal_is_reported_by_opencode_and_hermes(self):
        # Trimmed from real runs refused by a subscription's usage limit (2026-10-07).
        refused = {"type": "error", "timestamp": 1791352030186, "sessionID": "ses_x",
                   "error": {"name": "APIError", "data": {"message": "The usage limit has been reached", "statusCode": 429}}}
        usage = self.parse("opencode", json.dumps(refused))
        self.assertEqual((usage["error"], usage["output_tokens"]), ("APIError: The usage limit has been reached", None))
        said = "ChatGPT or Codex Subscription rate-limited every one of 3 attempts\n\nProvider said: HTTP 429\n"
        usage = self.parse("hermes", said, {"hermes-usage.json": {"input_tokens": None, "output_tokens": None, "api_calls": 1,
                                                                  "completed": False, "failed": True}})
        self.assertEqual((usage["error"], usage["output_tokens"]),
                         ("ChatGPT or Codex Subscription rate-limited every one of 3 attempts", None))
        worked = self.parse("hermes", "done", {"hermes-usage.json": {"input_tokens": 5, "output_tokens": 6, "failed": False}})
        self.assertIsNone(worked["error"])

    def test_droid_reads_its_result_object(self):
        # The result object of a real run (droid 0.235.0, 2026-10-08), with the reply text shortened.
        result = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 25500, "num_turns": 4,
                  "result": "Rewrote slugify.", "session_id": "a1038628",
                  "usage": {"input_tokens": 27728, "output_tokens": 2111, "cache_read_input_tokens": 10752,
                            "cache_creation_input_tokens": 0, "factory_credits": 4373, "ttft_ms": 1496.5}}
        usage = self.parse("droid", json.dumps(result))
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["cache_write_tokens"], usage["output_tokens"],
                          usage["turns"], usage["tool_calls"], usage["error"]), (27728, 10752, 0, 2111, 4, None, None))
        refused = self.parse("droid", json.dumps({"type": "result", "subtype": "error", "is_error": True, "result": "Insufficient credits\nmore"}))
        self.assertEqual((refused["error"], refused["output_tokens"]), ("Insufficient credits", None))
        launch = adapters.Launch("do it", "custom:deepseek-flash-0", "high", "single", (), {"telemetry": "/t", "mock": "/m"})
        self.assertNotIn("-r", adapters.get("droid").command(launch))   # a custom model takes its effort from the settings file
        self.assertIn("-r", adapters.get("droid").command(adapters.Launch("do it", "gpt-6.1-sol", "medium", "single", (), {"telemetry": "/t", "mock": "/m"})))

    def test_dsh_writes_its_model_settings_and_sums_step_usage(self):
        launch = adapters.Launch("--do it", "openai-codex/gpt-6.1-sol", "medium", "single", ("--patch", "/extra.yml"), {"telemetry": "/t", "mock": "/m"})
        command = adapters.get("dsh").command(launch)
        with tempfile.TemporaryDirectory() as folder:
            # Run the wrapper for real, with `echo` standing in for dsh, to see the file it writes and what it would launch.
            path = str(Path(folder) / "dsh-model.yml")
            staged = [path if part == "/t/dsh-model.yml" else "echo" if part == "dsh" else part for part in command]
            printed = subprocess.run(staged, capture_output=True, text=True, check=True).stdout.strip()
            written = json.loads(Path(path).read_text())
        self.assertEqual(written, [{"id": "agent-default-model", "name": "@deepseek-ai/dsh-agent-default-model",
                                    "config": {"provider": "openai-codex", "model": "gpt-6.1-sol", "reasoningEffort": "medium"}}])
        self.assertEqual(printed, f"--profile headless --patch {path} --patch /extra.yml --json -- --do it")
        self.assertEqual(adapters.get("dsh").env, {"DSH_PERMISSION_MODE": "danger-full-access"})

        def step(**usage):
            return json.dumps({"type": "status", "phase": "step_end", "turn": 1, "step": 1, **({"usage": usage} if usage else {})})
        call = json.dumps({"type": "tool_call", "callId": "c1", "tool": "bash", "input": {}})
        # Two steps as a real run on gpt-6.1-sol gave them (2026-10-08): input apart from the cache, zero cache figures left out.
        # The totals leave no room for cache writes, so those are known to be zero and not merely unreported.
        first = step(inputTokens=4216, outputTokens=50, totalTokens=4266)
        apart = step(inputTokens=198, outputTokens=57, totalTokens=4351, cacheReadTokens=4096)
        usage = self.parse("dsh", "\n".join(['{"type":"session","sessionId":"s"}', call, first, call, apart, '{"type":"final","text":"done"}']))
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["cache_write_tokens"], usage["output_tokens"],
                          usage["turns"], usage["tool_calls"], usage["error"]), (4414, 4096, 0, 107, 2, 2, None))
        # A total that holds more than input, output and cache reads: the rest was written to the cache.
        wrote = self.parse("dsh", step(inputTokens=100, outputTokens=20, cacheReadTokens=900, totalTokens=1320))
        self.assertEqual((wrote["input_tokens"], wrote["cached_input_tokens"], wrote["cache_write_tokens"]), (100, 900, 300))
        # Input that has the cached part inside it: taken out, and cache writes stay unknown.
        inside = self.parse("dsh", step(inputTokens=1000, outputTokens=30, cacheReadTokens=900, totalTokens=1030))
        self.assertEqual((inside["input_tokens"], inside["cached_input_tokens"], inside["cache_write_tokens"]), (100, 900, None))
        # A retried step reports no usage: the total is then unknown, not a partial sum.
        partial = self.parse("dsh", "\n".join([apart, step()]))
        self.assertEqual((partial["input_tokens"], partial["output_tokens"], partial["turns"]), (None, None, 2))
        # The end of a real run whose last model call failed after the work was done (2026-10-08).
        ended = self.parse("dsh", "\n".join([first, json.dumps({"type": "status", "phase": "turn_end", "turn": 1, "reason": {
            "kind": "error", "error": {"message": "WebSocket closed 1000", "code": "PI_AI_ERROR"}}}), '{"type":"final","text":"done"}']))
        self.assertEqual((ended["error"], ended["output_tokens"]), ("WebSocket closed 1000", 50))
        refused = self.parse("dsh", '{"type":"error","message":"MISSING_CREDENTIAL: no key\\nmore"}')
        self.assertEqual((refused["error"], refused["input_tokens"]), ("MISSING_CREDENTIAL: no key", None))

    def test_devin_reads_its_exported_session(self):
        # Trimmed from the export of a real run (devin 3000.11.3, 2026-10-07): the same fields, fewer steps.
        export = {"schema_version": "ATIF-v1.7", "agent": {"name": "devin", "model_name": "GPT-6.1 Sol Medium Thinking"},
                  "steps": [{"step_id": 1, "source": "system", "message": "..."},
                            {"step_id": 2, "source": "user", "message": "..."},
                            {"step_id": 3, "source": "agent", "tool_calls": [{}, {}, {}, {}],
                             "metrics": {"prompt_tokens": 9480, "completion_tokens": 310, "cached_tokens": 0,
                                         "extra": {"cache_creation_input_tokens": 9470}}},
                            {"step_id": 4, "source": "agent", "tool_calls": [{}],
                             "metrics": {"prompt_tokens": 15001, "completion_tokens": 92, "cached_tokens": 14804,
                                         "extra": {"cache_creation_input_tokens": 194}}},
                            {"step_id": 5, "source": "agent", "tool_calls": []}],
                  "final_metrics": {"total_prompt_tokens": 24481, "total_completion_tokens": 402, "total_cached_tokens": 14804}}
        usage = self.parse("devin", "plain text reply", {"devin-export.json": export})
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["cache_write_tokens"], usage["output_tokens"],
                          usage["turns"], usage["tool_calls"], usage["reported_cost_usd"]), (9677, 14804, 0, 402, 2, 5, None))
        self.assertEqual(set(self.parse("devin", "no export was written").values()), {None})

    def test_unrecognised_output_is_missing_not_zero(self):
        for adapter in adapters.ADAPTERS:
            usage = self.parse(adapter, "something went wrong\n{not json}\n")
            self.assertEqual(set(usage.values()), {None}, adapter)

    def test_every_adapter_builds_a_command(self):
        launch = adapters.Launch("do it", "m", "high", "single", ("--extra",), {"telemetry": "/t", "mock": "/m"})
        for adapter in adapters.ADAPTERS.values():
            if adapter.id == "manual":
                with self.assertRaisesRegex(RuntimeError, "by hand"):
                    adapter.command(launch)
                continue
            argv = adapter.command(launch)
            self.assertTrue(all(isinstance(part, str) for part in argv), adapter.id)
            self.assertIn("--extra", argv, adapter.id)


class ComparisonTests(unittest.TestCase):
    def plan(self):
        suite = json.loads((ROOT / "suites/smoke.json").read_text())
        suite["repetitions"] = 4
        suite["modes"] = suite["modes"][:1]
        suite["harnesses"] = suite["harnesses"][:3]
        for task in suite["tasks"]:
            task.update(seed_revision="synthetic", evaluator_revision="synthetic")
        for harness in suite["harnesses"]:
            harness["version"] = "synthetic"
        return make_plan(suite)

    def records(self, plan, outcome):
        return [dict(run_id=run["run_id"], status="passed" if outcome(run) else "failed", elapsed_seconds=1,
                     human_interventions=0, human_minutes=0, attempts=1, checks_total=1,
                     checks_passed=int(outcome(run)), evidence_ref="synthetic") for run in plan["runs"]]

    def test_identical_outcomes_are_within_noise(self):
        plan = self.plan()
        pairs = compare(plan, self.records(plan, lambda run: run["repetition"] % 2 == 0))
        self.assertEqual(len(pairs), 3)
        for pair in pairs:
            self.assertEqual(pair["difference"], 0)
            self.assertFalse(pair["clear"])
            self.assertLessEqual(pair["low"], 0)
            self.assertGreaterEqual(pair["high"], 0)

    def test_consistent_gap_is_clear_and_ordered(self):
        plan = self.plan()
        pairs = compare(plan, self.records(plan, lambda run: run["harness_id"] == "mock-idle"))
        clear = [pair for pair in pairs if pair["clear"]]
        self.assertEqual({(pair["better"], pair["worse"]) for pair in clear},
                         {("mock-idle", "mock-solves"), ("mock-idle", "mock-hangs")})
        self.assertTrue(all(pair["difference"] == 1 and 0 < pair["low"] < pair["high"] for pair in clear))

    def five_tasks(self, repetitions):
        suite = json.loads((ROOT / "suites/demo-mock.json").read_text())
        suite.update(repetitions=repetitions, models=suite["models"][:1], modes=suite["modes"][:1],
                     harnesses=suite["harnesses"][:2])
        for task in suite["tasks"]:
            task.update(seed_revision="synthetic", evaluator_revision="synthetic")
        for harness in suite["harnesses"]:
            harness["version"] = "synthetic"
        return make_plan(suite)

    def test_all_or_nothing_tasks_do_not_fake_certainty(self):
        # 9 of 15 against 6 of 15, where every task either always passes or always fails.
        plan = self.five_tasks(3)
        wins = {"mock-steady": {"md-preview", "kanban-undo", "expenses-csv"}, "mock-flaky": {"md-preview", "kanban-undo"}}
        (pair,) = compare(plan, self.records(plan, lambda run: run["task_id"] in wins[run["harness_id"]]))
        self.assertAlmostEqual(pair["difference"], 0.2)
        self.assertFalse(pair["clear"])
        self.assertLess(pair["low"], 0)
        self.assertGreater(pair["high"], pair["difference"])

    def test_one_repetition_is_never_enough_for_a_small_gap(self):
        plan = self.five_tasks(1)
        wins = {"mock-steady": {"md-preview", "kanban-undo", "expenses-csv"}, "mock-flaky": {"md-preview", "kanban-undo"}}
        (pair,) = compare(plan, self.records(plan, lambda run: run["task_id"] in wins[run["harness_id"]]))
        self.assertFalse(pair["clear"])

    def test_overall_test_sees_a_real_difference_and_not_a_fake_one(self):
        plan = self.five_tasks(4)
        same = omnibus(plan, self.records(plan, lambda run: run["repetition"] % 2 == 0))
        self.assertEqual([(item["harnesses"], item["blocks"], item["spread"], item["p_value"]) for item in same], [(2, 20, 0.0, 1.0)])
        (different,) = omnibus(plan, self.records(plan, lambda run: run["harness_id"] == "mock-steady"))
        self.assertEqual(different["spread"], 1.0)
        self.assertLess(different["p_value"], 0.001)
        # A task everyone passes or everyone fails carries no evidence either way.
        (uninformative,) = omnibus(plan, self.records(plan, lambda run: run["task_id"] == "md-preview"))
        self.assertEqual(uninformative["p_value"], 1.0)
        self.assertEqual(omnibus(plan, []), [])

    def test_deterministic_and_needs_shared_tasks(self):
        plan = self.plan()
        records = self.records(plan, lambda run: (run["repetition"] + len(run["harness_id"])) % 3 == 0)
        self.assertEqual(compare(plan, records), compare(plan, records))
        only = [r for r in records if ":mock-solves:" in r["run_id"]]
        self.assertEqual(compare(plan, only), [])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(runner.remove_tree, self.root)
        shutil.copytree(ROOT / "tasks/smoke-slugify", self.root / "tasks/smoke-slugify")
        self.suite = json.loads((ROOT / "suites/smoke.json").read_text())
        self.suite.update(repetitions=1, budget={"timeout_seconds": 2, "max_retries": 0})
        self.box = sandbox.make("local")

    def run_plan(self, **options):
        plan = make_plan(runner.pin(self.suite, self.root, self.box))
        results = runner.execute(plan, self.root, self.box, log=lambda _: None, **options)
        return plan, runner.read_results(results)

    def test_task_validation(self):
        self.assertEqual(runner.validate_task(self.root, self.suite["tasks"][0], self.box),
                         {"seed": "1/7", "reference": "7/7"})
        shutil.copy(self.root / "tasks/smoke-slugify/reference/slugify.py",
                    self.root / "tasks/smoke-slugify/seed/slugify.py")
        with self.assertRaisesRegex(ValueError, "already passes"):
            runner.validate_task(self.root, self.suite["tasks"][0], self.box)

    def test_every_outcome_is_recorded(self):
        plan, records = self.run_plan()
        status = {r["run_id"].split(":")[2]: r for r in records}
        self.assertEqual({name: r["status"] for name, r in status.items()},
                         {"mock-solves": "passed", "mock-idle": "failed",
                          "mock-hangs": "timed_out", "mock-crashes": "blocked"})
        solved = status["mock-solves"]
        self.assertTrue(solved["mock"])
        self.assertEqual((solved["files_changed"], solved["input_tokens"], solved["cost_usd"]), (1, 1000, None))
        self.assertAlmostEqual(solved["list_price_usd"], 0.0022)
        self.assertIsNone(status["mock-hangs"]["input_tokens"])
        evidence = self.root / solved["evidence_ref"]
        self.assertTrue((evidence / "changes.patch").read_text().startswith("--- a/slugify.py\n+++ b/slugify.py\n"))
        # The agent's files are kept packed, never as a live folder, and never include the hidden checks.
        self.assertFalse((evidence / "workspace").exists())
        with tarfile.open(evidence / "workspace.tar.gz") as archive:
            names = archive.getnames()
        self.assertIn("workspace/slugify.py", names)
        self.assertFalse(any(name.endswith("check.py") for name in names))
        self.assertIn("(mock)", report(plan, records))

    def test_page_data_names_the_failed_checks_of_each_run(self):
        plan, records = self.run_plan()
        summary = summarize(plan, records, self.root)
        by_harness = {run["harness"]: run for run in summary["runs"]}
        self.assertEqual(by_harness["mock-solves"]["failed"], [])
        self.assertEqual(len(by_harness["mock-idle"]["failed"]), 6)
        self.assertIn("accented letters", [check["name"] for check in by_harness["mock-idle"]["failed"]])
        self.assertIsNone(by_harness["mock-crashes"]["failed"])
        self.assertIn("without changing the workspace", by_harness["mock-crashes"]["reason"])
        hardest = summary["checks"][0]
        self.assertEqual((hardest["task"], hardest["runs"]), ("smoke-slugify", 4))
        self.assertLess(hardest["passed"], hardest["runs"])
        # Without the run folders the page still builds; it just has no per-check detail.
        self.assertTrue(all(run["failed"] is None for run in summarize(plan, records)["runs"]))
        page = site.render(plan, records, self.root, self.root / "page" / "media")
        self.assertIn("accented letters", page)
        self.assertNotIn("/*DATA*/null", page)
        self.assertIn("Hidden checks failed most often", report(plan, records, self.root))

    def test_resume_skips_recorded_runs_and_retries_blocked(self):
        _, first = self.run_plan(limit=2)
        self.assertEqual(len(first), 2)
        _, everything = self.run_plan()
        self.assertEqual(len(everything), 5)
        self.assertEqual([r["run_id"] for r in everything[:2]], [r["run_id"] for r in first])
        _, again = self.run_plan(retry_blocked=True)
        self.assertEqual(len(again), 5)

    def test_one_repetition_at_a_time_adds_to_the_same_results(self):
        self.suite["repetitions"] = 2
        plan, first = self.run_plan(repetition=1)
        self.assertEqual(len(first), len(plan["runs"]) // 2)
        self.assertEqual({r["repetition"] for r in plan["runs"] if r["run_id"] in {x["run_id"] for x in first}}, {1})
        _, everything = self.run_plan()
        self.assertEqual(len(everything), len(plan["runs"]))
        self.assertEqual([r["run_id"] for r in everything[:len(first)]], [r["run_id"] for r in first])

    def test_several_harnesses_can_be_named(self):
        plan = make_plan(runner.pin(self.suite, self.root, self.box))
        ids = sorted({run["harness_id"] for run in plan["runs"]})
        _, some = self.run_plan(harness=",".join(ids[:2]))
        self.assertEqual(len(some), sum(run["harness_id"] in ids[:2] for run in plan["runs"]))
        with self.assertRaisesRegex(ValueError, "no such harness"):
            self.run_plan(harness="not-a-harness")

    def test_one_model_at_a_time(self):
        plan, none = self.run_plan(model="no-such-model")
        self.assertEqual(none, [])
        wanted = plan["runs"][0].get("model_id")
        _, some = self.run_plan(model=wanted)
        self.assertEqual(len(some), sum(run.get("model_id") == wanted for run in plan["runs"]))

    def test_changed_task_blocks_instead_of_running(self):
        plan = make_plan(runner.pin(self.suite, self.root, self.box))
        (self.root / "tasks/smoke-slugify/evaluator/check.py").write_text("raise SystemExit(0)\n")
        records = runner.read_results(runner.execute(plan, self.root, self.box, log=lambda _: None))
        self.assertEqual({r["status"] for r in records}, {"blocked"})

    def test_real_harness_refused_without_isolation(self):
        self.suite["harnesses"].append({"id": "codex", "adapter": "codex", "version": "x"})
        plan = make_plan(runner.pin(self.suite, self.root, self.box) | {})
        with self.assertRaisesRegex(ValueError, "no isolation"):
            runner.execute(plan, self.root, self.box)

    def test_missing_price_stays_unknown(self):
        usage = dict(input_tokens=10, cached_input_tokens=5, cache_write_tokens=None, output_tokens=1)
        self.assertIsNone(runner.list_price(usage, {"input": 1, "output": 2}))
        self.assertIsNone(runner.list_price(usage, None))
        self.assertIsNone(runner.list_price({**usage, "output_tokens": None}, {"input": 1, "output": 2, "cached_input": 1}))
        prices = {"input": 1, "output": 2, "cached_input": 1}
        self.assertAlmostEqual(runner.list_price(usage, prices), 17 / 1_000_000)
        # Unknown tokens of a kind the table charges for make the whole estimate unknown, not smaller.
        self.assertIsNone(runner.list_price({**usage, "cached_input_tokens": None}, prices))
        self.assertIsNone(runner.list_price(usage, {**prices, "cache_write": 3}))

    def only(self, **harness):
        self.suite["harnesses"] = [{"id": "mock-one", "adapter": "mock", "version": None, **harness}]
        self.suite["modes"] = self.suite["modes"][:1]

    def test_agent_litter_does_not_stop_the_batch(self):
        # A pipe, a locked folder, an unreadable file, a nested empty repository and an ignore-everything file.
        self.only(args=["litter"])
        self.suite["harnesses"].append({"id": "mock-solves", "adapter": "mock", "args": ["reference"], "version": None})
        _, records = self.run_plan()
        self.assertEqual([r["status"] for r in records], ["passed", "passed"])
        littered = next(r for r in records if ":mock-one:" in r["run_id"])
        self.assertGreaterEqual(littered["files_changed"], 3)
        with tarfile.open(self.root / littered["evidence_ref"] / "workspace.tar.gz") as archive:
            names = archive.getnames()
        self.assertIn(f"workspace/{runner.AGENT_GIT}", names)
        self.assertFalse(any(part == ".git" for name in names for part in name.split("/")))
        # The same run can be repeated: its folder, read-only parts included, is cleared first.
        _, again = self.run_plan(retry_blocked=True)
        self.assertEqual(len(again), 2)

    def test_nothing_an_agent_writes_can_hide_or_distort_its_changes(self):
        seed, workspace = self.root / "seed", self.root / "w"
        for folder in (seed, workspace):
            folder.mkdir()
            (folder / "a.txt").write_text("one\n")
            (folder / "gone.txt").write_text("x\ny\n")
            (folder / "same.txt").write_text("unchanged\n")
        (workspace / "a.txt").write_text("one\ntwo\n")
        (workspace / "gone.txt").unlink()
        (workspace / ".gitignore").write_text("*\n")
        (workspace / ".gitattributes").write_text("* -diff\n")
        (workspace / "node_modules").mkdir()
        (workspace / "node_modules" / "big.js").write_text("x\n" * 100)
        (workspace / "nested").mkdir()
        (workspace / "nested" / "inside.js").write_text("a\nb\nc\n")
        subprocess.run(["git", "init", "-q", str(workspace / "nested")], check=True, capture_output=True)
        (workspace / "blob.bin").write_bytes(b"\0\1\2")
        (workspace / "secret").write_text("x")
        (workspace / "secret").chmod(0)
        os.symlink("/etc/hosts", workspace / "link")
        (seed / "c.txt").write_text("x\n-- comment\nend")
        (workspace / "c.txt").write_text("x\r\n++counter;\nend\n")
        files, added, removed = runner.change_stats(seed, workspace, self.root / "patch")
        # a.txt, gone.txt, .gitignore, .gitattributes, nested/inside.js, blob.bin, secret, link, c.txt.
        # In c.txt every line differs: a line ending, a line that starts like a diff header, a final newline.
        self.assertEqual((files, added, removed), (9, 1 + 1 + 1 + 3 + 1 + 3, 2 + 3))
        patch = (self.root / "patch").read_text()
        self.assertIn("+two", patch)
        self.assertIn("link to /etc/hosts", patch)
        self.assertNotIn("big.js", patch)
        self.assertEqual(runner.change_stats(seed, seed, self.root / "none"), (0, 0, 0))

    def test_every_repository_an_agent_leaves_is_set_aside(self):
        workspace = self.root / "w"
        (workspace / "deep" / "er").mkdir(parents=True)
        for folder in (workspace, workspace / "deep" / "er"):
            subprocess.run(["git", "init", "-q", str(folder)], check=True, capture_output=True)
        (workspace / "deep" / runner.AGENT_GIT).write_text("in the way")
        (workspace / "deep" / ".git").mkdir()
        runner.set_aside_repositories(workspace)
        self.assertEqual(sorted(str(path.relative_to(workspace)) for path in workspace.rglob(".git*") if path.name != "info"
                                and ".git-as" in path.name and path.parent.name in ("w", "deep", "er")),
                         [runner.AGENT_GIT, f"deep/{runner.AGENT_GIT}", f"deep/{runner.AGENT_GIT}-1", f"deep/er/{runner.AGENT_GIT}"])
        self.assertFalse(any(path.name.lower() == ".git" for path in workspace.rglob("*")))

    def test_refreshed_login_is_returned_and_copies_are_removed(self):
        login = self.root / "host-auth.json"
        login.write_text("token-1\n")
        login.chmod(0o600)
        self.addCleanup(lambda: [path.unlink() for path in self.root.glob("host-auth.json.*")])
        before = set(Path(tempfile.gettempdir()).glob("hb-home-*"))
        # By default nothing is written back: the run only notes that the copy changed.
        self.only(args=["rotate", ".tool/auth.json"], credentials=[f"{login}:.tool/auth.json"])
        _, records = self.run_plan()
        self.assertEqual(login.read_text(), "token-1\n")
        self.assertEqual(records[0]["logins_changed_in_run"], 1)
        self.assertNotIn("credentials_refreshed", records[0])
        # With the suite's say-so, the refreshed login comes back.
        self.only(args=["rotate", ".tool/auth.json"], credentials=[f"{login}:.tool/auth.json"], write_back_logins=True)
        _, records = self.run_plan()
        self.assertEqual(login.read_text(), "token-1\nrefreshed\n")
        self.assertEqual(login.stat().st_mode & 0o777, 0o600)
        self.assertEqual(records[0]["credentials_refreshed"], 1)
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("hb-home-*")), before)

    def login(self, original='{"token": "one"}', refreshed='{"token": "two"}'):
        home = self.root / "home"
        (home / ".tool").mkdir(parents=True, exist_ok=True)
        source, held = self.root / "auth.json", home / ".tool" / "auth.json"
        source.write_text(original)
        source.chmod(0o600)
        before = runner.digest(source)
        if refreshed is not None:
            held.write_text(refreshed)
        return source, held, before, home

    def test_login_changed_on_both_sides_is_left_alone(self):
        source, held, before, home = self.login()
        source.write_text('{"token": "changed here"}')
        self.assertEqual(runner.return_credentials([(source, held, before)], home), (0, 1))
        self.assertEqual(source.read_text(), '{"token": "changed here"}')

    def test_an_unchanged_or_removed_login_is_left_alone(self):
        source, held, before, home = self.login(refreshed='{"token": "one"}')
        self.assertEqual(runner.return_credentials([(source, held, before)], home), (0, 0))
        held.unlink()
        self.assertEqual(runner.return_credentials([(source, held, before)], home), (0, 0))
        self.assertEqual(source.read_text(), '{"token": "one"}')

    def test_a_refreshed_login_keeps_a_backup_and_its_permissions(self):
        source, held, before, home = self.login()
        self.assertEqual(runner.return_credentials([(source, held, before)], home), (1, 0))
        self.assertEqual(source.read_text(), '{"token": "two"}')
        (backup,) = source.parent.glob("auth.json.harness-bench-backup-*")
        self.assertEqual(backup.read_text(), '{"token": "one"}')
        self.assertEqual((source.stat().st_mode & 0o777, backup.stat().st_mode & 0o777), (0o600, 0o600))
        self.assertFalse(source.with_name("auth.json.harness-bench-new").exists())
        # Several refreshes keep several originals, oldest dropped first.
        for round_number in range(8):
            held.write_text(json.dumps({"token": f"round {round_number}"}))
            self.assertEqual(runner.return_credentials([(source, held, runner.digest(source))], home), (1, 0))
        backups = sorted(source.parent.glob("auth.json.harness-bench-backup-*"))
        self.assertEqual(len(backups), runner.BACKUPS_KEPT)
        self.assertEqual(json.loads(backups[-1].read_text()), {"token": "round 6"})

    def test_a_link_planted_in_place_of_the_login_is_refused(self):
        # An agent swaps its login copy for a link to some other file on this machine.
        source, held, before, home = self.login(refreshed=None)
        private = self.root / "id_private"
        private.write_text('{"not": "a login"}')
        os.symlink(private, held)
        self.assertEqual(runner.return_credentials([(source, held, before)], home), (0, 1))
        self.assertEqual(source.read_text(), '{"token": "one"}')
        # The same through a linked folder.
        held.unlink()
        held.parent.rmdir()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "auth.json").write_text('{"token": "planted"}')
        os.symlink(elsewhere, held.parent)
        self.assertEqual(runner.return_credentials([(source, held, before)], home), (0, 1))
        self.assertEqual(source.read_text(), '{"token": "one"}')

    def test_a_half_written_or_foreign_login_is_refused(self):
        for bad in ("", "   ", '{"token": "tw', "-----BEGIN PRIVATE KEY-----", "[1, 2]", "x" * 200000,
                    '{"account": "someone else"}', '{"token": "two", "extra": 1}', "{}", "[" * 40000, "y" * (2 << 20)):
            source, held, before, home = self.login(refreshed=bad)
            self.assertEqual(runner.return_credentials([(source, held, before)], home), (0, 1), bad[:20])
            self.assertEqual(source.read_text(), '{"token": "one"}')

    def test_a_login_that_is_itself_a_link_stays_a_link(self):
        source, held, before, home = self.login()
        real = self.root / "dotfiles-auth.json"
        source.rename(real)
        os.symlink(real, source)
        self.assertEqual(runner.return_credentials([(source, held, before)], home), (1, 0))
        self.assertTrue(source.is_symlink())
        self.assertEqual(real.read_text(), '{"token": "two"}')

    def test_credentials_must_stay_inside_the_home(self):
        login = self.root / "auth.json"
        login.write_text("x")
        for target in ("../escape.json", "/etc/escape.json", ""):
            self.only(args=["noop"], credentials=[f"{login}:{target}"])
            _, records = self.run_plan()
            self.assertEqual(records[0]["status"], "blocked", target)
            self.assertIn("not usable", records[0]["blocked_reason"])

    def test_evaluator_that_cannot_start_blocks_instead_of_failing(self):
        settings = self.root / "tasks/smoke-slugify/task.json"
        settings.write_text(json.dumps({"evaluator_command": "no-such-evaluator-binary"}))
        self.only(args=["reference"])
        plan, records = self.run_plan()
        self.assertEqual(records[0]["status"], "blocked")
        self.assertIn("evaluator could not start", records[0]["blocked_reason"])
        self.assertIn("unknown", report(plan, records))

    def test_evaluator_that_runs_but_reports_nothing_is_a_visible_failure(self):
        settings = self.root / "tasks/smoke-slugify/task.json"
        settings.write_text(json.dumps({"evaluator_command": "true"}))
        self.only(args=["reference"])
        plan, records = self.run_plan()
        self.assertEqual((records[0]["status"], records[0]["checks_total"]), ("failed", 0))
        self.assertIn("evaluator_error", records[0])
        self.assertIn("evaluator itself produced no result", report(plan, records))

    def test_an_error_exit_after_real_work_is_a_failure_not_a_blocked_run(self):
        self.only(args=["crash"])
        _, quick = self.run_plan()
        self.assertEqual(quick[0]["status"], "blocked")
        limit, runner.NEVER_STARTED_SECONDS = runner.NEVER_STARTED_SECONDS, 0
        self.addCleanup(setattr, runner, "NEVER_STARTED_SECONDS", limit)
        _, slow = self.run_plan(retry_blocked=True)
        self.assertEqual(slow[0]["status"], "failed")

    def test_retrying_blocked_runs_of_one_harness_leaves_the_others(self):
        _, first = self.run_plan()
        crashed = next(r for r in first if ":mock-crashes:" in r["run_id"])
        _, second = self.run_plan(retry_blocked=True, harness="mock-solves")
        self.assertEqual(len(second), len(first))
        self.assertIn(crashed, second)

    def test_a_usage_parser_that_crashes_does_not_cost_the_run(self):
        from harness_bench import adapters
        self.only(args=["reference"])
        original = adapters.ADAPTERS["mock"]
        def explode(stdout, telemetry):
            raise AttributeError("'float' object has no attribute 'get'")
        adapters.ADAPTERS["mock"] = adapters.Adapter("mock", original.version, original.command, explode)
        self.addCleanup(adapters.ADAPTERS.__setitem__, "mock", original)
        _, records = self.run_plan()
        self.assertEqual((records[0]["status"], records[0]["input_tokens"]), ("passed", None))
        self.assertIn("AttributeError", records[0]["usage_error"])

    def test_a_harness_that_says_it_never_reached_the_model_is_blocked_not_failed(self):
        from harness_bench import adapters
        self.only(args=["noop"])
        original = adapters.ADAPTERS["mock"]
        adapters.ADAPTERS["mock"] = adapters.Adapter("mock", original.version, original.command,
                                                     lambda stdout, telemetry: {**adapters.empty(), "output_tokens": 0, "error": "login expired"})
        self.addCleanup(adapters.ADAPTERS.__setitem__, "mock", original)
        _, records = self.run_plan()
        self.assertEqual(records[0]["status"], "blocked")
        self.assertIn("login expired", records[0]["blocked_reason"])

    def test_an_unexpected_error_in_one_run_is_recorded_and_the_batch_goes_on(self):
        self.only(args=["reference"])
        self.suite["harnesses"].append({"id": "mock-solves", "adapter": "mock", "args": ["reference"], "version": None})
        original, calls = runner.change_stats, []
        def flaky(*arguments):
            calls.append(1)
            if len(calls) == 1:
                raise TypeError("something nobody expected")
            return original(*arguments)
        runner.change_stats = flaky
        self.addCleanup(setattr, runner, "change_stats", original)
        _, records = self.run_plan()
        self.assertEqual([r["status"] for r in records], ["blocked", "passed"])
        self.assertIn("TypeError", records[0]["blocked_reason"])

    def test_killing_the_runner_stops_the_agent_and_removes_copied_logins(self):
        login = self.root / "host-auth.json"
        login.write_text('{"token": "one"}')
        self.only(args=["hang"], credentials=[f"{login}:.tool/auth.json"])
        self.suite["budget"]["timeout_seconds"] = 60
        plan = make_plan(runner.pin(self.suite, self.root, self.box))
        (self.root / "plan.json").write_text(json.dumps(plan))
        before = set(Path(tempfile.gettempdir()).glob("hb-home-*"))
        process = subprocess.Popen([sys.executable, "-m", "harness_bench", "run", "--plan", str(self.root / "plan.json"),
                                    "--sandbox", "local", "--root", str(self.root)],
                                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        marker = None
        for _ in range(200):
            found = list(self.root.glob("runs/*/*/workspace/agent.pid"))
            if found and found[0].read_text().strip():
                marker = found[0]
                break
            time.sleep(0.05)
        self.assertIsNotNone(marker, "the agent never started")
        agent = int(marker.read_text())
        process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(timeout=20), 128 + signal.SIGTERM)
        time.sleep(0.2)
        with self.assertRaises(ProcessLookupError):
            os.kill(agent, 0)
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("hb-home-*")), before)

    def test_keys_come_from_a_private_file_without_being_shown(self):
        from harness_bench.__main__ import load_secrets, main
        import contextlib, io
        secrets = self.root / ".env"
        secrets.write_text("# keys\nHB_TEST_ONE=alpha-secret\nexport HB_TEST_TWO=\"beta secret\"\nHB_TEST_EMPTY=\n\nHB_TEST_SET=from-file\n")
        secrets.chmod(0o600)
        os.environ["HB_TEST_SET"] = "from-shell"
        for name in ("HB_TEST_ONE", "HB_TEST_TWO", "HB_TEST_EMPTY", "HB_TEST_SET"):
            self.addCleanup(os.environ.pop, name, None)
        self.assertEqual(load_secrets(secrets), ["HB_TEST_ONE", "HB_TEST_TWO"])
        self.assertEqual((os.environ["HB_TEST_ONE"], os.environ["HB_TEST_TWO"], os.environ["HB_TEST_SET"]),
                         ("alpha-secret", "beta secret", "from-shell"))
        self.assertNotIn("HB_TEST_EMPTY", os.environ)
        (self.root / "bad.env").write_text("this is not a key line\n")
        with self.assertRaisesRegex(ValueError, "line 1"):
            load_secrets(self.root / "bad.env")
        # The key reaches the agent through the suite's env list, and its value is never printed.
        for name in ("HB_TEST_ONE", "HB_TEST_TWO"):
            os.environ.pop(name)
        self.only(args=["reference"], env=["HB_TEST_ONE"])
        plan = make_plan(runner.pin(self.suite, self.root, self.box))
        (self.root / "plan.json").write_text(json.dumps(plan))
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(main(["run", "--plan", str(self.root / "plan.json"), "--sandbox", "local", "--root", str(self.root)]), 0)
        self.assertIn("passed", output.getvalue())
        self.assertIn("Loaded from", output.getvalue())
        self.assertNotIn("alpha-secret", output.getvalue())
        self.assertNotIn("alpha-secret", (self.root / "runs" / plan["plan_id"][:16] / "results.jsonl").read_text())

    def test_grading_a_folder_by_hand(self):
        from harness_bench.__main__ import main
        import contextlib, io
        task = self.root / "tasks/smoke-slugify"
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(main(["grade", "--task", str(task), "--workspace", str(task / "seed"), "--sandbox", "local"]), 2)
            self.assertEqual(main(["grade", "--task", str(task), "--workspace", str(task / "seed"),
                                   "--sandbox", "local", "--trusted"]), 1)
            self.assertEqual(main(["grade", "--task", str(task), "--workspace", str(task / "reference"),
                                   "--sandbox", "local", "--trusted", "--output", str(self.root / "kept")]), 0)
        text = output.getvalue()
        self.assertIn("no isolation", text)
        self.assertIn("1/7 checks passed", text)
        self.assertIn("FAIL  accented letters", text)
        self.assertIn("7/7 checks passed", text)
        self.assertTrue((self.root / "kept/evaluation/result.json").is_file())
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(main(["grade", "--task", str(task), "--workspace", str(task / "reference"), "--sandbox", "local",
                                   "--trusted", "--output", str(task / "reference" / "out")]), 2)
        self.assertIn("must not be inside the workspace", output.getvalue())

    def by_hand_plan(self):
        self.suite["modes"] = self.suite["modes"][:1]
        self.suite["repetitions"] = 3
        self.suite["harnesses"] = [
            {"id": "mock-solves", "adapter": "mock", "args": ["reference"], "version": None},
            {"id": "desk-app", "adapter": "manual", "version": "9.9", "repetitions": 1},
        ]
        return make_plan(runner.pin(self.suite, self.root, self.box))

    def test_a_harness_run_by_hand_joins_the_same_results(self):
        from harness_bench import manual
        plan = self.by_hand_plan()
        # One repeat for the app, three for the automatic harness.
        self.assertEqual(sum(run["harness_id"] == "desk-app" for run in plan["runs"]), 1)
        self.assertEqual(sum(run["harness_id"] == "mock-solves" for run in plan["runs"]), 3)
        # `run` leaves the hand-run alone and says it is waiting.
        said = []
        records = runner.read_results(runner.execute(plan, self.root, self.box, log=said.append))
        self.assertEqual(len(records), 3)
        self.assertTrue(any("by hand" in line for line in said))
        self.assertEqual(len(manual.waiting(plan, self.root)), 1)

        workspace, prompt, run = manual.start(plan, self.root, "desk-app", "smoke-slugify")
        self.assertEqual(prompt.read_text(), (self.root / "tasks/smoke-slugify/prompt.md").read_text())
        self.assertTrue((workspace / "slugify.py").is_file())
        self.assertFalse(any("check" in path.name for path in workspace.rglob("*")))
        with self.assertRaisesRegex(ValueError, "already exists"):
            manual.start(plan, self.root, "desk-app", "smoke-slugify")
        # The "app" does its work: here, by writing the reference solution into the folder.
        shutil.copy(self.root / "tasks/smoke-slugify/reference/slugify.py", workspace / "slugify.py")
        record = manual.finish(plan, self.root, self.box, "desk-app", "smoke-slugify", seconds=312, cost_usd=0.4,
                               input_tokens=9000, output_tokens=800, interventions=1, app_version="9.9")
        self.assertEqual((record["status"], record["checks_passed"], record["elapsed_seconds"], record["cost_usd"]),
                         ("passed", 7, 312.0, 0.4))
        self.assertEqual((record["manual"], record["human_interventions"], record["files_changed"], record["time_includes_handling"]),
                         (True, 1, 1, False))
        self.assertFalse(workspace.exists())
        self.assertEqual(manual.waiting(plan, self.root), [])
        with self.assertRaisesRegex(ValueError, "already recorded"):
            manual.start(plan, self.root, "desk-app", "smoke-slugify")
        everything = runner.read_results(self.root / "runs" / plan["plan_id"][:16] / "results.jsonl")
        text = report(plan, everything, self.root)
        self.assertIn("desk-app (manual)", text)
        self.assertIn("run by hand in a desktop app", text)
        self.assertIn('"has_manual": true', site.render(plan, everything, self.root))

    def test_a_hand_run_without_a_typed_time_says_so_and_wrong_requests_are_refused(self):
        from harness_bench import manual
        plan = self.by_hand_plan()
        with self.assertRaisesRegex(ValueError, "run automatically"):
            manual.start(plan, self.root, "mock-solves", "smoke-slugify")
        with self.assertRaisesRegex(ValueError, "no run"):
            manual.start(plan, self.root, "desk-app", "smoke-slugify", repetition=2)
        with self.assertRaisesRegex(ValueError, "manual-start first"):
            manual.finish(plan, self.root, self.box, "desk-app", "smoke-slugify")
        manual.start(plan, self.root, "desk-app", "smoke-slugify")
        record = manual.finish(plan, self.root, self.box, "desk-app", "smoke-slugify")
        self.assertEqual((record["status"], record["time_includes_handling"], record["cost_usd"], record["input_tokens"]),
                         ("failed", True, None, None))

    def test_results_carry_over_into_a_plan_that_only_adds_runs(self):
        first = self.by_hand_plan()
        made = runner.read_results(runner.execute(first, self.root, self.box, log=lambda _: None))
        self.assertEqual(len(made), 3)
        # Extending: one more harness run by hand. Nothing about the existing runs changes.
        self.suite["harnesses"].append({"id": "second-app", "adapter": "manual", "version": "1.0", "repetitions": 1})
        second = make_plan(runner.pin(self.suite, self.root, self.box))
        self.assertNotEqual(first["plan_id"], second["plan_id"])
        carried, skipped, refused = runner.carry_over(first, second, self.root)
        self.assertEqual((len(carried), skipped, refused), (3, [], []))
        moved = runner.read_results(self.root / "runs" / second["plan_id"][:16] / "results.jsonl")
        self.assertEqual({r["run_id"] for r in moved}, {r["run_id"] for r in second["runs"] if r["harness_id"] == "mock-solves"})
        self.assertEqual(sorted(r["carried_from"] for r in moved), sorted(r["run_id"] for r in made))
        self.assertTrue(all((self.root / r["evidence_ref"] / "agent.stdout").is_file() for r in moved))
        self.assertIn("mock-solves", report(second, moved, self.root))
        self.assertEqual(runner.carry_over(first, second, self.root)[:2], ([], [r["run_id"] for r in made]))   # safe to repeat
        self.assertEqual(len(runner.read_results(runner.execute(second, self.root, self.box, log=lambda _: None))), 3)  # nothing reruns
        # Another harness's name for the model is not an input of these runs; this harness's own would be.
        self.suite["models"][0]["harness_names"] = {"second-app": "some-other-name"}
        renamed = make_plan(runner.pin(self.suite, self.root, self.box))
        self.assertEqual(len(runner.carry_over(first, renamed, self.root)[0]), 3)
        self.suite["models"][0]["harness_names"] = {"mock-solves": "a-different-model"}
        self.assertEqual(len(runner.carry_over(first, make_plan(runner.pin(self.suite, self.root, self.box)), self.root)[2]), 3)
        self.suite["models"][0].pop("harness_names")
        # A longer time limit changes nothing about a run that ended on its own; the record says which limit it had.
        shorter = self.suite["budget"]["timeout_seconds"]
        self.suite["budget"]["timeout_seconds"] = shorter * 4
        longer = make_plan(runner.pin(self.suite, self.root, self.box))
        carried, _, refused = runner.carry_over(first, longer, self.root)
        self.assertEqual((len(carried), refused), (3, []))
        kept = runner.read_results(self.root / "runs" / longer["plan_id"][:16] / "results.jsonl")
        self.assertEqual({r["made_under_timeout_seconds"] for r in kept}, {shorter})
        self.suite["budget"]["timeout_seconds"] = max(1, shorter // 2)   # a shorter limit is a different test
        self.assertEqual(len(runner.carry_over(first, make_plan(runner.pin(self.suite, self.root, self.box)), self.root)[2]), 3)
        self.suite["budget"]["timeout_seconds"] = shorter
        # A run whose inputs changed is not carried: here the harness is launched differently.
        self.suite["harnesses"][0]["args"] = ["noop"]
        third = make_plan(runner.pin(self.suite, self.root, self.box))
        carried, _, refused = runner.carry_over(first, third, self.root)
        self.assertEqual((carried, len(refused)), ([], 3))
        self.assertIn("not the same", refused[0][1])

    def test_a_hand_run_can_be_worked_on_outside_the_project(self):
        from harness_bench import manual
        plan = self.by_hand_plan()
        elsewhere = self.root.parent / "elsewhere"
        self.addCleanup(shutil.rmtree, elsewhere, True)
        workspace, prompt, _ = manual.start(plan, self.root, "desk-app", "smoke-slugify", workspaces=elsewhere)
        self.assertTrue(workspace.is_relative_to(elsewhere.resolve()) and not workspace.is_relative_to(self.root.resolve()))
        self.assertFalse((self.root / "manual").exists())
        with self.assertRaisesRegex(ValueError, "manual-start first"):   # looked for in the wrong place
            manual.finish(plan, self.root, self.box, "desk-app", "smoke-slugify", seconds=5)
        shutil.copy(self.root / "tasks/smoke-slugify/reference/slugify.py", workspace / "slugify.py")
        (workspace / ".DS_Store").write_bytes(b"left by Finder when the folder was looked at")
        record = manual.finish(plan, self.root, self.box, "desk-app", "smoke-slugify", seconds=5, workspaces=elsewhere)
        self.assertEqual((record["status"], record["manual"], record["files_changed"]), ("passed", True, 1))
        self.assertFalse(workspace.exists())

    def test_run_folders_are_unique(self):
        base = Path("/x")
        first = runner.run_directory(base, {"run_id": "plan:a_b:c:m:single:1"})
        second = runner.run_directory(base, {"run_id": "plan:a:b_c:m:single:1"})
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
