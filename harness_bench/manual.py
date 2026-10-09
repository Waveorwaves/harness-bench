"""Runs done by hand in a desktop app, recorded into the same results as automatic runs.

Some harnesses have no command line to launch. For those, `start` lays out a fresh folder
and the prompt, a person runs the task in the app, and `finish` measures and grades what
the app left, exactly as the runner would: change size, hidden checks in the sandbox,
screenshots for pages. What the tool cannot see (tokens, cost, how often the person had to
step in) is typed in, and stays unknown if it is not.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from . import runner, tasks
from .core import require, validate_plan


def find_run(plan, harness_id, task_id, model_id=None, repetition=1):
    configuration = plan["configuration"]
    harness = next((h for h in configuration["harnesses"] if h["id"] == harness_id), None)
    require(harness, f"no harness {harness_id} in this plan")
    require(harness["adapter"] == "manual", f"{harness_id} is run automatically; use `run`")
    matches = [run for run in plan["runs"] if run["harness_id"] == harness_id and run["task_id"] == task_id
               and run["repetition"] == repetition and model_id in (None, run.get("model_id"))]
    require(matches, f"the plan has no run of {task_id} by {harness_id}"
            + (f" with model {model_id}" if model_id else "") + f", repeat {repetition}")
    require(len(matches) == 1, f"{harness_id} runs {task_id} with several models; say which with --model: "
            + ", ".join(sorted(run["model_id"] for run in matches)))
    return matches[0]


def folder_for(root, run, workspaces=None):
    """Where the person works: a short path that is easy to open in an app.

    By default that is inside the project, which also holds the task's hidden checks and reference
    solution a few folders up. An app works on the real machine and could read them, so for runs that
    are to be compared with sandboxed ones, give `workspaces`: a folder outside the project.
    """
    base = Path(workspaces).expanduser().resolve() if workspaces else Path(root).resolve() / "manual"
    return base / run["harness_id"] / runner.run_directory(Path("."), run).name


def notes_for(root, plan, run):
    """Where the prompt and the start time are kept: with the plan's results, never beside the folder the app works in.

    An app can look around the folder it is given. What it finds there should be what a sandboxed
    harness would find: the task's starting files and nothing about the experiment.
    """
    folder = Path(root).resolve() / "runs" / plan["plan_id"][:16] / "by-hand"
    name = runner.run_directory(Path("."), run).name
    return folder / f"{name}.prompt.md", folder / f"{name}.started.json"


def start(plan, root, harness_id, task_id, model_id=None, repetition=1, workspaces=None):
    """Lay out a fresh workspace and the prompt. Returns (workspace, prompt file, run)."""
    validate_plan(plan)
    require(plan["ready"], "plan is not ready: " + "; ".join(plan["not_ready_reasons"]))
    run = find_run(plan, harness_id, task_id, model_id, repetition)
    results = Path(root).resolve() / "runs" / plan["plan_id"][:16] / "results.jsonl"
    require(run["run_id"] not in {record["run_id"] for record in runner.read_results(results)},
            "this run is already recorded")
    entry = next(t for t in plan["configuration"]["tasks"] if t["id"] == task_id)
    task = tasks.load(root, entry)
    require((task.seed_revision, task.evaluator_revision) == (entry["seed_revision"], entry["evaluator_revision"]),
            "task files differ from the pinned revisions")
    workspace = folder_for(root, run, workspaces)
    require(not workspace.exists(), f"{workspace} already exists: finish that run, or delete the folder to start again")
    workspace.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task.seed, workspace)
    runner.seed_repository(workspace)
    prompt, marker = notes_for(root, plan, run)
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(task.prompt, encoding="utf-8")
    marker.write_text(json.dumps(
        {"run_id": run["run_id"], "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
    return workspace, prompt, run


def finish(plan, root, sandbox, harness_id, task_id, model_id=None, repetition=1, *, seconds=None, cost_usd=None,
           input_tokens=None, output_tokens=None, interventions=0, app_version=None, workspaces=None,
           cached_input_tokens=None, cache_write_tokens=None, tool_calls=None, turns=None, subagents=None):
    """Measure and grade what the app left, and append the record. Returns the record."""
    validate_plan(plan)
    root = Path(root).resolve()
    run = find_run(plan, harness_id, task_id, model_id, repetition)
    configuration = plan["configuration"]
    workspace = folder_for(root, run, workspaces)
    prompt, marker = notes_for(root, plan, run)
    require(workspace.is_dir() and marker.is_file(), f"nothing to finish: run manual-start first ({workspace} is missing)")
    started = json.loads(marker.read_text())
    require(started["run_id"] == run["run_id"], "this folder was started for a different plan; start it again")
    base = root / "runs" / plan["plan_id"][:16]
    results = base / "results.jsonl"
    require(run["run_id"] not in {record["run_id"] for record in runner.read_results(results)},
            "this run is already recorded")
    task = tasks.load(root, next(t for t in configuration["tasks"] if t["id"] == task_id))
    began = datetime.fromisoformat(started["started_at"])
    timed = seconds is not None
    elapsed = float(seconds) if timed else (datetime.now(timezone.utc) - began).total_seconds()

    directory = runner.run_directory(base, run)
    runner.remove_tree(directory)
    directory.mkdir(parents=True)
    (base / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    kept = directory / "workspace"
    runner.copy_tree(workspace, kept)
    # Looking at the folder in Finder leaves a .DS_Store in it. That is macOS's file, not the app's work.
    for finder_file in kept.rglob(".DS_Store"):
        finder_file.unlink()
    files, added, removed = runner.change_stats(task.seed, kept, directory / "changes.patch")
    runner.set_aside_repositories(kept)
    passed, total, error, setup_fault = runner.evaluate(task, kept, directory, sandbox)
    runner.archive_workspace(kept, directory / "workspace.tar.gz")
    require(not setup_fault, f"the result could not be graded, so nothing was recorded: {error}")

    model = next((m for m in configuration.get("models", []) if m["id"] == run.get("model_id")), None)
    # Tokens are whatever could be read for this app: typed in from its screen, or taken from its own log.
    usage = {"input_tokens": input_tokens, "cached_input_tokens": cached_input_tokens, "cache_write_tokens": cache_write_tokens,
             "output_tokens": output_tokens}
    record = {
        "run_id": run["run_id"], "status": "passed" if total and passed == total else "failed",
        "elapsed_seconds": round(elapsed, 1), "human_interventions": interventions, "human_minutes": 0,
        "attempts": 1, "checks_passed": passed, "checks_total": total,
        "evidence_ref": directory.relative_to(root).as_posix(), **usage,
        "turns": turns, "tool_calls": tool_calls, "subagents": subagents, "cost_usd": cost_usd,
        "list_price_usd": runner.list_price(usage, (model or {}).get("price_per_mtok")),
        "files_changed": files, "lines_added": added, "lines_removed": removed,
        "manual": True, "mock": False, "sandbox": "none: run by hand in a desktop app",
        # Without a typed time, the clock ran from manual-start to manual-finish, the person's handling included.
        "time_includes_handling": not timed, "harness_version": app_version,
        "started_at": started["started_at"],
    }
    if error:
        record["evaluator_error"] = error
    with results.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    runner.remove_tree(workspace)
    for leftover in (marker, prompt):
        leftover.unlink(missing_ok=True)
    return record


def waiting(plan, root):
    """Manual runs not yet recorded, as (run, folder if started)."""
    manual = {h["id"] for h in plan["configuration"]["harnesses"] if h["adapter"] == "manual"}
    results = Path(root).resolve() / "runs" / plan["plan_id"][:16] / "results.jsonl"
    done = {record["run_id"] for record in runner.read_results(results)}
    return [(run, folder_for(root, run) if folder_for(root, run).is_dir() else None)
            for run in plan["runs"] if run["harness_id"] in manual and run["run_id"] not in done]
