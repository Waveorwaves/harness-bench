"""Directory tasks: a prompt, a seed workspace, a hidden evaluator and an optional reference.

    tasks/<id>/task.json     {"evaluator_command": "...", "evaluator_timeout_seconds": 120}
    tasks/<id>/prompt.md     what the agent is told
    tasks/<id>/seed/         starting workspace (may be empty for a from-scratch build)
    tasks/<id>/evaluator/    never mounted into the agent's sandbox
    tasks/<id>/reference/    files that, laid over the seed, must pass the evaluator

The evaluator command runs with the candidate workspace copy as its working directory and
writes $HB_OUT/result.json: {"checks": [{"name": "...", "passed": true}, ...]}.

A task whose result is a page can add "capture" to task.json:

    {"path": "index.html", "width": 1280, "height": 800, "times_ms": [1000, 3000], "probe": "<js>",
     "clip": {"duration_ms": 2500, "frames": 20}}

The page is then screenshotted in a headless browser before evaluation, and the evaluator
finds the frames and capture.json under $HB_CAPTURE: console errors, every request the page
made, how much changed between frames, frames per second and the probe's value. The clip is
a short run of small frames for people to judge motion from.

"script": "steps.json" names a file in evaluator/ listing interaction steps (click, type,
press, reload, eval). They are carried out with real input events after the stills, and the
values of the `eval` steps appear in capture.json under "interaction". This is how a page's
behaviour is graded, not just its looks.
"""

from dataclasses import dataclass
import difflib
import hashlib
import json
from pathlib import Path

IGNORED = {"__pycache__", ".DS_Store", ".git"}


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    seed: Path
    evaluator: Path
    reference: Path | None
    command: str
    timeout: int
    capture: dict | None
    seed_revision: str
    evaluator_revision: str


def tree_hash(directory, *extra):
    digest = hashlib.sha256()
    files = sorted(p for p in Path(directory).rglob("*")
                   if p.is_file() and not IGNORED & set(p.relative_to(directory).parts))
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    for value in extra:
        digest.update(b"\1" + value.encode())
    return digest.hexdigest()[:16]


def load(root, entry):
    directory = Path(root) / entry["spec"]
    if not (directory / "task.json").is_file():
        raise ValueError(f"task {entry['id']}: {entry['spec']} is not a runnable task directory "
                         "(needs task.json, prompt.md, seed/ and evaluator/)")
    settings = json.loads((directory / "task.json").read_text(encoding="utf-8"))
    command = settings.get("evaluator_command")
    timeout = settings.get("evaluator_timeout_seconds", 120)
    if not isinstance(command, str) or not command.strip():
        raise ValueError(f"task {entry['id']}: evaluator_command is required")
    if type(timeout) is not int or timeout < 1:
        raise ValueError(f"task {entry['id']}: invalid evaluator_timeout_seconds")
    capture = settings.get("capture")
    if capture is not None:
        capture = {"path": "index.html", "width": 1280, "height": 800, "times_ms": [1000, 3000], "probe": None,
                   "clip": None, "script": None, **capture}
        if capture["script"] is not None and not (directory / "evaluator" / capture["script"]).is_file():
            raise ValueError(f"task {entry['id']}: capture script {capture['script']} is not in evaluator/")
        if capture["clip"] is not None:
            capture["clip"] = {"duration_ms": 2500, "frames": 20, "scale": 0.5, "quality": 70, **capture["clip"]}
        if (not isinstance(capture["path"], str) or type(capture["width"]) is not int or type(capture["height"]) is not int
                or not capture["times_ms"] or any(type(t) is not int or t < 0 for t in capture["times_ms"])):
            raise ValueError(f"task {entry['id']}: invalid capture settings")
    for name in ("seed", "evaluator"):
        if not (directory / name).is_dir():
            raise ValueError(f"task {entry['id']}: missing {name}/")
    prompt = (directory / "prompt.md").read_text(encoding="utf-8")
    reference = directory / "reference"
    return Task(entry["id"], prompt, directory / "seed", directory / "evaluator",
                reference if reference.is_dir() else None, command, timeout, capture,
                tree_hash(directory / "seed", prompt),
                tree_hash(directory / "evaluator", command, str(timeout),
                          *([json.dumps(capture, sort_keys=True)] if capture else [])))


def reference_change(task):
    """How big the reference solution's change is: (files, lines added, lines removed) against the seed.

    A yardstick for the size of an agent's own change, not a target: a good solution may be larger.
    """
    if not task.reference:
        return None
    files = added = removed = 0
    for path in sorted(p for p in task.reference.rglob("*") if p.is_file() and not IGNORED & set(p.relative_to(task.reference).parts)):
        original = task.seed / path.relative_to(task.reference)
        try:
            new = path.read_text(encoding="utf-8").splitlines()
            old = original.read_text(encoding="utf-8").splitlines() if original.is_file() else []
        except UnicodeDecodeError:
            continue
        changes = [line for line in difflib.ndiff(old, new) if line[:2] in ("+ ", "- ")]
        if changes:
            files += 1
            added += sum(line.startswith("+ ") for line in changes)
            removed += sum(line.startswith("- ") for line in changes)
    return files, added, removed
