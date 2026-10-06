"""Fake agent used to exercise the runner. Its output is synthetic, never a measurement.

    mock_agent.py noop | reference | hang | crash
    mock_agent.py variant <name>        (copies tasks/<id>/variants/<name>/ into the workspace)
    mock_agent.py rotate <path>         (rewrites a login file under its home, like a token refresh)
    mock_agent.py litter                (solves the task but leaves pipes, locked folders and a nested repository)
    mock_agent.py profile skill=0.7 cost=1.5 [boost=0.1] [mode=subagents]

`profile` imitates an agent of a given skill so the reports have something to show: seeded by
the run id, it applies all, some or none of the task's reference solution and invents usage.
"""

import json
import os
from pathlib import Path
import random
import shutil
import sys
import time


def apply(files, reference):
    for source in files:
        target = Path.cwd() / source.relative_to(reference)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def main(arguments):
    behavior = arguments[0] if arguments else "noop"
    usage = {"input_tokens": 1000, "cached_input_tokens": 4000, "cache_write_tokens": None,
             "output_tokens": 200, "reported_cost_usd": None, "turns": 3, "tool_calls": 2, "subagents": None}
    if behavior == "hang":
        Path("agent.pid").write_text(str(os.getpid()))  # lets a test confirm the agent was stopped
        time.sleep(3600)
    if behavior == "crash":
        return 3
    reference = Path(os.environ.get("HB_REFERENCE", ""))
    files = sorted(path for path in reference.rglob("*") if path.is_file()) if os.environ.get("HB_REFERENCE") else []
    if behavior == "reference":
        apply(files, reference)
    if behavior == "rotate":
        # Imitates a harness that refreshes its login file while it runs.
        with open(Path.home() / arguments[1], "a", encoding="utf-8") as handle:
            handle.write("refreshed\n")
    if behavior == "litter":
        # Leaves the kinds of thing a real agent can leave behind, to prove the runner copes.
        os.mkfifo("pipe")
        Path("locked").mkdir()
        Path("locked/file").write_text("x")
        os.chmod("locked", 0o500)
        Path("unreadable").write_text("x")
        os.chmod("unreadable", 0)
        Path("nested").mkdir()
        os.system("git init -q nested")
        Path(".gitignore").write_text("*\n")
        # A path too long for the operating system to spell out in one go.
        here = os.getcwd()
        for _ in range(6):
            os.mkdir("d" * 200)
            os.chdir("d" * 200)
        Path("deep.txt").write_text("x")
        os.chdir(here)
        apply(files, reference)
    if behavior == "variant":
        # A named alternative solution kept with the task: usually a deliberately weaker one.
        variant = Path(os.environ["HB_VARIANTS"]) / arguments[1]
        apply(sorted(path for path in variant.rglob("*") if path.is_file()), variant)
    if behavior == "profile":
        options = dict(argument.split("=", 1) for argument in arguments[1:])
        team = options.get("mode") == "subagents"
        skill = float(options.get("skill", 0.5)) + float(options.get("boost", 0)) + (0.05 if team else 0)
        cost = float(options.get("cost", 1)) * (1.8 if team else 1)
        rng = random.Random(os.environ.get("HB_RUN_ID", ""))
        roll = rng.random()
        if roll < skill:
            apply(files, reference)
        elif roll < skill + (1 - skill) / 2:
            apply(rng.sample(files, max(1, len(files) // 2)), reference)
        time.sleep(rng.uniform(0.02, 0.25) * cost)
        turns = rng.randint(4, 14)
        usage.update(input_tokens=int(rng.uniform(6000, 14000) * cost), cached_input_tokens=int(rng.uniform(20000, 90000) * cost),
                     output_tokens=int(rng.uniform(1500, 6000) * cost), turns=turns, tool_calls=turns + rng.randint(0, 9),
                     subagents=(rng.randint(0, 4) if team else 0))
    print(json.dumps({"type": "mock_usage", **usage}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
