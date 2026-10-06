"""Capture analysis and blind judging, on synthetic images and a scripted judge."""

import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

from harness_bench import judging, runner, sandbox
from harness_bench.capture import capture
from harness_bench.core import make_plan

ROOT = Path(__file__).resolve().parents[1]


def png(rows):
    """Encode rows of (r, g, b) pixels, using a different PNG filter on each row."""
    width, raw, previous = len(rows[0]), b"", [0] * (len(rows[0]) * 3)
    for index, row in enumerate(rows):
        flat = [channel for pixel in row for channel in pixel]
        kind = index % 3
        if kind == 0:
            line = flat
        elif kind == 1:
            line = [(value - (flat[i - 3] if i >= 3 else 0)) & 255 for i, value in enumerate(flat)]
        else:
            line = [(value - previous[i]) & 255 for i, value in enumerate(flat)]
        raw += bytes([kind, *line])
        previous = flat

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, len(rows), 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class CaptureAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, True)

    def write(self, name, rows):
        path = self.directory / name
        path.write_bytes(png(rows))
        return path

    def test_png_round_trip_through_every_filter_used(self):
        rows = [[(x * 40 % 256, y * 60 % 256, (x + y) * 25 % 256) for x in range(6)] for y in range(5)]
        width, height, decoded, channels = capture.read_png(self.write("a.png", rows))
        self.assertEqual((width, height, channels), (6, 5, 3))
        self.assertEqual([[tuple(line[x * 3:x * 3 + 3]) for x in range(6)] for line in decoded], rows)

    def test_blank_and_busy_pictures_are_told_apart(self):
        blank, _ = capture.describe(self.write("blank.png", [[(20, 20, 20)] * 16 for _ in range(16)]))
        busy, _ = capture.describe(self.write("busy.png", [[(x * 16, y * 16, 128) for x in range(16)] for y in range(16)]))
        self.assertEqual((blank["distinct_colors"], blank["dominant_share"]), (1, 1.0))
        self.assertGreater(busy["distinct_colors"], 10)
        self.assertLess(busy["dominant_share"], 0.2)

    def test_changed_fraction(self):
        still = [(10, 10, 10)] * 100
        moved = [(10, 10, 10)] * 75 + [(200, 10, 10)] * 25
        self.assertEqual(capture.changed_fraction(still, still), 0)
        self.assertEqual(capture.changed_fraction(still, moved), 0.25)
        self.assertEqual(capture.changed_fraction(still, moved[:50]), 1.0)


class FakePage:
    """Stands in for a browser tab: answers the interaction layer's calls and remembers them."""

    def __init__(self, present=("#here",)):
        self.present, self.calls = present, []

    def call(self, method, params=None, timeout=30):
        self.calls.append((method, params or {}))
        if method == "Runtime.evaluate":
            expression = params["expression"]
            if "querySelectorAll(" in expression and "getBoundingClientRect" in expression:
                found = any(json.dumps(selector) in expression for selector in self.present)
                spot = {"x": 10, "y": 20, "visible": True, "near": {"x": 10, "y": 20}}
                return {"result": {"value": spot if found else None}}
            if expression == "explode()":
                return {"exceptionDetails": {"exception": {"description": "ReferenceError: explode is not defined\n at x"}}}
            return {"result": {"value": 42}}
        return {}

    def listen(self, seconds, until=None):
        return True


class InteractionTests(unittest.TestCase):
    def test_steps_become_real_input_events(self):
        page = FakePage()
        values, problems = capture.interact(page, [
            {"do": "click", "selector": "#here"},
            {"do": "type", "selector": "#here", "text": "hello"},
            {"do": "press", "key": "Enter"},
            {"do": "press", "key": "Tab", "shift": True},
            {"do": "dblclick", "selector": "#here"},
            {"do": "eval", "name": "answer", "script": "6 * 7"},
            {"do": "reload"},
        ])
        self.assertEqual((values, problems), ({"answer": 42}, []))
        sent = [(method, params) for method, params in page.calls if method.startswith(("Input.", "Page."))]
        # The pointer moves onto a control before pressing it, as a person's would.
        self.assertEqual([params["type"] for _, params in sent[:3]], ["mouseMoved", "mousePressed", "mouseReleased"])
        self.assertIn(("Input.insertText", {"text": "hello"}), sent)
        enter = next(params for method, params in sent if method == "Input.dispatchKeyEvent" and params["key"] == "Enter")
        self.assertEqual((enter["type"], enter["windowsVirtualKeyCode"], enter["text"]), ("keyDown", 13, "\r"))
        shifted = next(params for method, params in sent if method == "Input.dispatchKeyEvent" and params["key"] == "Tab")
        self.assertEqual(shifted["modifiers"], 8)
        self.assertEqual([params["clickCount"] for _, params in sent if "clickCount" in params][-4:], [1, 1, 2, 2])
        self.assertEqual(sent[-1][0], "Page.reload")

    def test_a_step_that_cannot_be_done_is_recorded_and_the_rest_go_on(self):
        values, problems = capture.interact(FakePage(), [
            {"do": "click", "selector": "#missing"},
            {"do": "eval", "name": "broken", "script": "explode()"},
            {"do": "teleport"},
            {"do": "eval", "name": "after", "script": "1"},
        ])
        self.assertEqual(values, {"after": 42})
        self.assertEqual(len(problems), 3)
        self.assertIn("nothing visible matches #missing", problems[0])
        self.assertIn("ReferenceError", problems[1])
        self.assertIn("unknown action", problems[2])


# A stand-in judge: prefers the larger image file, whichever side it is on, and refuses to
# answer if it can see anything besides the two images.
SCRIPTED_JUDGE = r"""
import sys
from pathlib import Path
assert sorted(path.name for path in Path('.').iterdir()) == ['left.png', 'right.png'], 'the judge can see more than it should'
assert 'mock-' not in sys.argv[1]
sizes = Path('left.png').stat().st_size, Path('right.png').stat().st_size
print('Some reasoning that mentions LEFT and RIGHT.')
print('TIE' if sizes[0] == sizes[1] else 'LEFT' if sizes[0] > sizes[1] else 'RIGHT')
"""


class JudgingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        shutil.copytree(ROOT / "tasks/sunset-sail", self.root / "tasks/sunset-sail")
        suite = json.loads((ROOT / "suites/demo-showcase.json").read_text())
        suite.update(repetitions=2, tasks=suite["tasks"][:1], harnesses=[
            {"id": name, "adapter": "mock", "args": ["noop"], "version": None}
            for name in ("mock-polished", "mock-basic", "mock-faulty")])
        self.plan = make_plan(runner.pin(suite, self.root, sandbox.make("local")))
        # Stand in for real captures: bigger files for the harness a sensible judge should prefer.
        sizes = {"mock-polished": 3000, "mock-basic": 2000, "mock-faulty": 1000}
        base = self.root / "runs" / self.plan["plan_id"][:16]
        for run in self.plan["runs"]:
            frames = runner.run_directory(base, run) / "capture"
            frames.mkdir(parents=True)
            (frames / "frame-3000.png").write_bytes(b"x" * sizes[run["harness_id"]])
            (frames / "clip-000.jpg").write_bytes(b"y")
            (frames / "capture.json").write_text(json.dumps({
                "frames": [{"file": "frame-3000.png"}], "clip": [{"file": "clip-000.jpg", "offset_ms": 0}]}))

    def test_prepare_is_blind_and_balanced(self):
        folder = judging.prepare(self.plan, self.root, "sunset-sail")
        key = judging.read_key(folder)
        self.assertEqual(len(key["pairs"]), 6)
        self.assertEqual(len(key["attempts"]), 6)
        # The folder can be handed over as it is: no key inside, no harness name in any file or name.
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["index.html", "media"])
        for harness in ("mock-polished", "mock-basic", "mock-faulty"):
            for path in folder.rglob("*"):
                self.assertNotIn(harness, path.name)
                if path.suffix == ".html":
                    self.assertNotIn(harness, path.read_text())
        sides = [key["attempts"][pair[side]]["configuration"][0] for pair in key["pairs"] for side in ("left", "right")]
        self.assertEqual({name: sides.count(name) for name in set(sides)},
                         {"mock-polished": 4, "mock-basic": 4, "mock-faulty": 4})
        self.assertTrue(all((folder / "media" / pair["left"] / "still.png").is_file() for pair in key["pairs"]))
        with self.assertRaisesRegex(ValueError, "already exists"):
            judging.prepare(self.plan, self.root, "sunset-sail")
        self.assertEqual(len(judging.read_key(judging.prepare(self.plan, self.root, "sunset-sail", per_pair=1, replace=True))["pairs"]), 3)

    def test_picks_from_an_earlier_set_of_pairs_are_rejected(self):
        folder = judging.prepare(self.plan, self.root, "sunset-sail")
        old = judging.read_key(folder)
        picks = self.root / "picks.json"
        picks.write_text(json.dumps({"judge": "x", "task_id": "sunset-sail", "pairs_id": old["pairs_id"],
                                     "picks": [{"pair": "p001", "winner": "left"}]}))
        self.assertIn("Judge: x", judging.ranking(folder, [picks]))
        folder = judging.prepare(self.plan, self.root, "sunset-sail", seed=1, replace=True)
        self.assertNotEqual(judging.read_key(folder)["pairs_id"], old["pairs_id"])
        with self.assertRaisesRegex(ValueError, "different set of pairs"):
            judging.ranking(folder, [picks])

    def test_a_failed_preparation_leaves_nothing_behind(self):
        base = self.root / "runs" / self.plan["plan_id"][:16]
        broken = runner.run_directory(base, self.plan["runs"][0]) / "capture" / "frame-3000.png"
        broken.unlink()
        with self.assertRaises(OSError):
            judging.prepare(self.plan, self.root, "sunset-sail")
        self.assertFalse((base / "judging" / "sunset-sail").exists())
        self.assertEqual(list((base / "judging").glob("*")) if (base / "judging").exists() else [], [])
        broken.write_bytes(b"x")
        folder = judging.prepare(self.plan, self.root, "sunset-sail")
        kept = judging.read_key(folder)["pairs_id"]
        # A replacement that fails must leave the earlier folder and key exactly as they were.
        broken.unlink()
        with self.assertRaises(OSError):
            judging.prepare(self.plan, self.root, "sunset-sail", replace=True)
        self.assertEqual(judging.read_key(folder)["pairs_id"], kept)
        self.assertTrue((folder / "index.html").is_file())

    def test_page_data_cannot_break_out_of_its_script(self):
        self.plan["configuration"]  # the task prompt is embedded in the page; make it hostile
        prompt = self.root / "tasks/sunset-sail/prompt.md"
        prompt.write_text(prompt.read_text() + "\n</script><!--<script>alert(1)")
        plan = make_plan(runner.pin(self.plan["configuration"], self.root, sandbox.make("local")))
        base = self.root / "runs" / plan["plan_id"][:16]
        for run in plan["runs"]:
            frames = runner.run_directory(base, run) / "capture"
            frames.mkdir(parents=True)
            (frames / "frame-3000.png").write_bytes(b"x")
            (frames / "capture.json").write_text(json.dumps({"frames": [{"file": "frame-3000.png"}]}))
        page = (judging.prepare(plan, self.root, "sunset-sail") / "index.html").read_text()
        data = page[page.index("const DATA = "):page.index("const $ =")]
        self.assertNotIn("<", data)
        self.assertIn("alert(1)", data)

    def test_needs_two_configurations_with_captures(self):
        base = self.root / "runs" / self.plan["plan_id"][:16]
        for run in self.plan["runs"]:
            if run["harness_id"] != "mock-polished":
                shutil.rmtree(runner.run_directory(base, run))
        with self.assertRaisesRegex(ValueError, "at least two"):
            judging.prepare(self.plan, self.root, "sunset-sail")

    def test_scripted_judge_ranks_and_side_bias_becomes_ties(self):
        folder = judging.prepare(self.plan, self.root, "sunset-sail")
        script = self.root / "judge.py"
        script.write_text(SCRIPTED_JUDGE)
        fair = judging.judge_with_model(folder, f"{sys.executable} {script} {{prompt}}", "scripted", log=lambda _: None)
        self.assertEqual((len(fair["picks"]), fair["stats"]["changed_with_side"], fair["stats"]["asked"]), (6, 0, 12))
        biased = judging.judge_with_model(folder, f"{sys.executable} -c \"print('LEFT')\" {{prompt}}", "always-left", log=lambda _: None)
        self.assertEqual(biased["stats"]["changed_with_side"], 6)
        self.assertEqual({pick["winner"] for pick in biased["picks"]}, {"tie"})
        mute = judging.judge_with_model(folder, f"{sys.executable} -c \"print('no idea')\" {{prompt}}", "mute", log=lambda _: None)
        self.assertEqual((mute["picks"], mute["stats"]["unreadable"]), ([], 6))
        failing = judging.judge_with_model(folder, f"{sys.executable} -c \"print('LEFT'); raise SystemExit(3)\" {{prompt}}", "fails", log=lambda _: None)
        self.assertEqual((failing["picks"], failing["stats"]["unreadable"]), ([], 6))
        peeking = judging.judge_with_model(folder, f"{sys.executable} -c \"import os; print(os.listdir('.'))\" {{prompt}}", "peek", log=lambda _: None)
        self.assertEqual(peeking["stats"]["unreadable"], 6)

        for name, document in (("fair", fair), ("biased", biased)):
            (self.root / f"{name}.json").write_text(json.dumps(document))
        text = judging.ranking(folder, [self.root / "fair.json", self.root / "biased.json"])
        order = [line.split("|")[2].strip().split(" / ")[0] for line in text.split("## Judge: scripted")[1].splitlines()
                 if line.startswith("| ") and line[2].isdigit()][:3]
        self.assertEqual(order, ["mock-polished", "mock-basic", "mock-faulty"])
        self.assertIn("Agreement between judges", text)
        self.assertIn("different answer when the sides were swapped on 6 of 6 pairs", text)

    def test_command_line_round_trip(self):
        from harness_bench.__main__ import main
        import contextlib, io
        folder = judging.prepare(self.plan, self.root, "sunset-sail")
        script = self.root / "judge.py"
        script.write_text(SCRIPTED_JUDGE)
        picks = self.root / "picks.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assertEqual(main(["judge-model", "--folder", str(folder), "--label", "scripted", "--output", str(picks),
                                   "--command", f"{sys.executable} {script} {{prompt}}"]), 0)
            self.assertEqual(main(["rank", "--folder", str(folder), "--picks", str(picks)]), 0)
        self.assertEqual(len(json.loads(picks.read_text())["picks"]), 6)
        self.assertIn("| 1 | mock-polished", output.getvalue())

    def test_picks_for_another_task_are_rejected(self):
        folder = judging.prepare(self.plan, self.root, "sunset-sail")
        wrong = self.root / "wrong.json"
        pairs_id = judging.read_key(folder)["pairs_id"]
        wrong.write_text(json.dumps({"judge": "x", "pairs_id": pairs_id, "task_id": "other", "picks": []}))
        with self.assertRaisesRegex(ValueError, "different task"):
            judging.ranking(folder, [wrong])
        wrong.write_text(json.dumps({"judge": "x", "pairs_id": pairs_id, "task_id": "sunset-sail",
                                     "picks": [{"pair": "p999", "winner": "left"}]}))
        with self.assertRaisesRegex(ValueError, "invalid pick"):
            judging.ranking(folder, [wrong])

    def test_last_answer(self):
        self.assertEqual(judging.last_answer("LEFT is sharper but overall...\n\nRIGHT"), "right")
        self.assertEqual(judging.last_answer("Both are fine.\nTie."), "tie")
        # The final line wins even when it is not capitalised and an earlier line shouted the other answer.
        self.assertEqual(judging.last_answer("RIGHT has more detail, but the lighting...\nFinal answer: Left"), "left")
        self.assertEqual(judging.last_answer("The right one is flat.\n**LEFT**"), "left")
        self.assertIsNone(judging.last_answer("the one on the left or the one on the right, hard to say"))
        # A sentence that merely contains one of the words is not a vote.
        self.assertIsNone(judging.last_answer("Error: you have no credits left"))
        self.assertIsNone(judging.last_answer("I could not open the right image"))
        self.assertIsNone(judging.last_answer("LEFT or RIGHT, it is close"))
        self.assertIsNone(judging.last_answer("The LEFT image is clearly worse."))
        self.assertIsNone(judging.last_answer("It is NOT a TIE."))
        self.assertEqual(judging.last_answer("...\nVerdict: tie."), "tie")
        self.assertIsNone(judging.last_answer(""))


if __name__ == "__main__":
    unittest.main()
