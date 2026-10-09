import argparse
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import threading

from . import adapters, judging, manual, runner, sandbox, site
from .core import make_plan, report


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def load_secrets(path):
    """Read NAME=value lines from a private file into this process's environment. Returns the names set.

    This is how API keys reach the harnesses without being typed into a shell or a suite file.
    A variable already set in the shell wins. Values are never printed or written anywhere.
    """
    names = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.removeprefix("export ").partition("=")
        name = name.strip()
        if not separator or not name.replace("_", "a").isalnum() or name[0].isdigit():
            raise ValueError(f"{path} line {number}: expected NAME=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value and name not in os.environ:
            os.environ[name] = value
            names.append(name)
    return names


def stop_on_signal(number, _frame):
    # One signal is enough. Further ones must not cut short the clean-up the first one started.
    for other in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, other):
            signal.signal(getattr(signal, other), signal.SIG_IGN)
    raise SystemExit(128 + number)


def add_sandbox(parser):
    parser.add_argument("--sandbox", choices=("docker", "local"), default="docker",
                        help="local has no isolation and is limited to the mock adapter and task validation")
    parser.add_argument("--image", default="harness-bench:latest", help="docker image holding the harnesses")
    parser.add_argument("--root", type=Path, default=Path("."), help="project directory containing tasks/ and runs/")
    parser.add_argument("--env-file", type=Path,
                        help="private file of NAME=value lines (API keys) to make available; default: .env in the project directory")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan, run and report coding-harness experiments.")
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan", help="expand a suite into an ordered list of runs")
    planner.add_argument("--suite", required=True, type=Path)
    planner.add_argument("--output", required=True, type=Path)
    reporter = commands.add_parser("report", help="summarise recorded results")
    reporter.add_argument("--plan", required=True, type=Path)
    reporter.add_argument("--results", type=Path)
    reporter.add_argument("--html", type=Path, help="also write the results page to this file")
    reporter.add_argument("--root", type=Path, default=Path("."),
                          help="project directory, used to read each run's checks and screenshots for the page")
    pinner = commands.add_parser("pin", help="record task revisions and harness versions in a suite")
    pinner.add_argument("--suite", required=True, type=Path)
    pinner.add_argument("--output", required=True, type=Path)
    add_sandbox(pinner)
    validator = commands.add_parser("validate-tasks", help="check each task's seed fails and reference passes")
    validator.add_argument("--suite", required=True, type=Path)
    add_sandbox(validator)
    checker = commands.add_parser("check", help="verify tasks, harnesses and settings without calling a model")
    checker.add_argument("--suite", required=True, type=Path)
    add_sandbox(checker)
    grader = commands.add_parser("grade", help="grade any folder against a task, for work done outside the runner")
    grader.add_argument("--task", required=True, type=Path, help="task directory, such as tasks/kanban-undo")
    grader.add_argument("--workspace", required=True, type=Path, help="the folder to grade")
    grader.add_argument("--output", type=Path, help="keep the evaluation files and screenshots here")
    grader.add_argument("--trusted", action="store_true",
                        help="required with --sandbox local: you accept running the folder's code on this machine")
    add_sandbox(grader)
    executor = commands.add_parser("run", help="execute the pending runs of a plan")
    executor.add_argument("--plan", required=True, type=Path)
    executor.add_argument("--limit", type=int, help="stop after this many runs")
    executor.add_argument("--harness", help="only run this harness id, or several separated by commas")
    executor.add_argument("--model", help="only run this model id")
    executor.add_argument("--repetition", type=int,
                          help="only run this repetition, e.g. 1 for a quick first pass; later passes add to the same results")
    executor.add_argument("--retry-blocked", action="store_true", help="discard blocked records and run them again")
    add_sandbox(executor)
    preparer = commands.add_parser("judge-prepare", help="build a blind side-by-side judging folder for a visual task")
    preparer.add_argument("--plan", required=True, type=Path)
    preparer.add_argument("--task", required=True)
    preparer.add_argument("--per-pair", type=int, help="at most this many matches between any two configurations")
    preparer.add_argument("--seed", type=int, default=0)
    preparer.add_argument("--replace", action="store_true",
                          help="overwrite an existing judging folder; picks already made for it will no longer match")
    preparer.add_argument("--model", help="pair only this model's attempts, in a folder of its own")
    preparer.add_argument("--root", type=Path, default=Path("."))
    modeler = commands.add_parser("judge-model", help="have a command-line model answer the pairs")
    modeler.add_argument("--folder", required=True, type=Path, help="folder written by judge-prepare")
    modeler.add_argument("--command", required=True, dest="judge_command",
                         help="command line containing {prompt}; runs in the folder")
    modeler.add_argument("--label", required=True, help="name for this judge in reports")
    modeler.add_argument("--output", required=True, type=Path)
    modeler.add_argument("--single-order", action="store_true", help="ask each pair once instead of once per side")
    ranker = commands.add_parser("rank", help="rank configurations from one or more picks files")
    ranker.add_argument("--folder", required=True, type=Path)
    ranker.add_argument("--picks", required=True, type=Path, nargs="+")
    for name, description in (("manual-start", "lay out a fresh folder and the prompt for a run done by hand in a desktop app"),
                              ("manual-finish", "measure, grade and record what the app left"),
                              ("manual-list", "show the runs by hand that are still waiting")):
        by_hand = commands.add_parser(name, help=description)
        by_hand.add_argument("--plan", required=True, type=Path)
        by_hand.add_argument("--root", type=Path, default=Path("."))
        if name != "manual-list":
            by_hand.add_argument("--harness", required=True)
            by_hand.add_argument("--task", required=True)
            by_hand.add_argument("--model", help="needed only if this harness runs the task with more than one model")
            by_hand.add_argument("--repetition", type=int, default=1)
            by_hand.add_argument("--workspaces", type=Path,
                                 help="keep the folders the apps work in here, outside the project, where the app "
                                      "cannot stumble on the hidden checks; default: manual/ inside the project")
        if name == "manual-finish":
            by_hand.add_argument("--seconds", type=float, help="how long the app worked; without it, the time since manual-start is used")
            by_hand.add_argument("--cost-usd", type=float, help="what the app says the run cost")
            by_hand.add_argument("--input-tokens", type=int, help="input tokens not read from cache")
            by_hand.add_argument("--cached-input-tokens", type=int, help="input tokens read from cache, where the app reports them")
            by_hand.add_argument("--cache-write-tokens", type=int, help="tokens written to cache, where the app reports them")
            by_hand.add_argument("--tool-calls", type=int)
            by_hand.add_argument("--turns", type=int, help="model calls, where the app reports them")
            by_hand.add_argument("--subagents", type=int, help="helper sessions the app started, where it reports them")
            by_hand.add_argument("--output-tokens", type=int)
            by_hand.add_argument("--interventions", type=int, default=0, help="how many times you had to step in")
            by_hand.add_argument("--app-version")
            by_hand.add_argument("--sandbox", choices=("docker", "local"), default="docker")
            by_hand.add_argument("--image", default="harness-bench:latest")
    carrier = commands.add_parser("carry-over", help="bring results into a plan that extends another, where the runs are unchanged")
    carrier.add_argument("--from", dest="old", required=True, type=Path, help="the plan the runs were made under")
    carrier.add_argument("--to", dest="new", required=True, type=Path, help="the extended plan")
    carrier.add_argument("--root", type=Path, default=Path("."))
    commands.add_parser("adapters", help="list the harness adapters")
    commands.add_parser("cleanup", help="remove containers and throwaway folders left by a runner that was killed")
    args = parser.parse_args(argv)
    # A closed terminal or a plain `kill` must stop a running agent and clean up, exactly as Ctrl-C does.
    # Raising here unwinds through the code that kills the container and deletes the copied logins.
    for name in ("SIGTERM", "SIGHUP"):
        # A signal the caller chose to ignore (nohup, for one) stays ignored.
        if (hasattr(signal, name) and threading.current_thread() is threading.main_thread()
                and signal.getsignal(getattr(signal, name)) is not signal.SIG_IGN):
            signal.signal(getattr(signal, name), stop_on_signal)
    try:
        if hasattr(args, "env_file"):
            secrets = args.env_file or args.root / ".env"
            if args.env_file or secrets.is_file():
                loaded = load_secrets(secrets)
                if stat.S_IMODE(secrets.stat().st_mode) & 0o077:
                    print(f"warning: {secrets} can be read by other users of this machine; run: chmod 600 {secrets}", file=sys.stderr)
                if loaded:
                    print(f"Loaded from {secrets}: {', '.join(loaded)}", file=sys.stderr)
        if args.command == "plan":
            plan = make_plan(load_json(args.suite))
            write_new(args.output, plan)
            print(f"Wrote {len(plan['runs'])} planned runs to {args.output}; pins complete: {plan['ready']}")
        elif args.command == "report":
            plan = load_json(args.plan)
            records = []
            if args.results:
                for line_number, line in enumerate(args.results.read_text(encoding="utf-8").splitlines(), 1):
                    if line.strip():
                        try:
                            records.append(json.loads(line))
                        except ValueError as error:
                            raise ValueError(f"results line {line_number}: {error}") from error
            print(report(plan, records, args.root), end="")
            if args.html:
                args.html.parent.mkdir(parents=True, exist_ok=True)
                args.html.write_text(site.render(plan, records, args.root, args.html.parent / "media"), encoding="utf-8")
                print(f"\nWrote {args.html}")
        elif args.command == "judge-prepare":
            folder = judging.prepare(load_json(args.plan), args.root, args.task, per_pair=args.per_pair, seed=args.seed,
                                     replace=args.replace, model=args.model)
            pairs = len(judging.read_key(folder)["pairs"])
            print(f"Wrote {pairs} pairs to {folder}\nOpen {folder / 'index.html'} to judge. "
                  f"The key is beside the folder, in {judging.key_path(folder).name}; do not give it to judges.")
        elif args.command == "judge-model":
            if args.output.exists():  # find out before paying for the answers, not after
                raise ValueError(f"{args.output} already exists")
            write_new(args.output, judging.judge_with_model(args.folder, args.judge_command, args.label,
                                                             both_orders=not args.single_order))
            print(f"Wrote {args.output}")
        elif args.command == "rank":
            print(judging.ranking(args.folder, args.picks), end="")
        elif args.command == "manual-start":
            workspace, prompt, run = manual.start(load_json(args.plan), args.root, args.harness, args.task, args.model, args.repetition,
                                                  workspaces=args.workspaces)
            print(f"Folder to open in the app:\n  {workspace}\nPrompt to paste, exactly as it is:\n  {prompt}\n"
                  "Pick the model this run is for, start the app on that folder, and let it finish without helping it.\n"
                  "Then run manual-finish with the same --harness and --task, adding --seconds and whatever usage the app shows.")
        elif args.command == "manual-finish":
            record = manual.finish(load_json(args.plan), args.root, sandbox.make(args.sandbox, args.image), args.harness, args.task,
                                   args.model, args.repetition, seconds=args.seconds, cost_usd=args.cost_usd,
                                   input_tokens=args.input_tokens, output_tokens=args.output_tokens,
                                   interventions=args.interventions, app_version=args.app_version, workspaces=args.workspaces,
                                   cached_input_tokens=args.cached_input_tokens, cache_write_tokens=args.cache_write_tokens,
                                   tool_calls=args.tool_calls, turns=args.turns,
                                   subagents=args.subagents)
            print(f"Recorded: {record['status']}, {record['checks_passed']}/{record['checks_total']} checks, "
                  f"{record['elapsed_seconds']}s" + (" (includes your handling)" if record["time_includes_handling"] else ""))
        elif args.command == "manual-list":
            pending = manual.waiting(load_json(args.plan), args.root)
            for run, folder in pending:
                print(f"{run['harness_id']}  {run['task_id']}  model {run.get('model_id')}  repeat {run['repetition']}"
                      + (f"  started: {folder}" if folder else ""))
            print(f"{len(pending)} run(s) by hand waiting")
        elif args.command == "cleanup":
            print(f"{runner.cleanup()} item(s) removed")
        elif args.command == "carry-over":
            carried, skipped, refused = runner.carry_over(load_json(args.old), load_json(args.new), args.root)
            print(f"Carried over {len(carried)} run(s); {len(skipped)} already there; {len(refused)} refused.")
            for run_id, reason in refused:
                print(f"  refused {run_id}: {reason}")
            return 1 if refused else 0
        elif args.command == "adapters":
            for adapter in adapters.ADAPTERS.values():
                if adapter.id == "manual":
                    print("manual: (a desktop app, run by hand with manual-start and manual-finish)")
                    continue
                print(f"{adapter.id}: {' '.join(adapter.command(adapters.Launch('<prompt>', '<model>', '<effort>', 'single', (), {'telemetry': '<telemetry>', 'mock': '<mock>'})))}")
        else:
            box = sandbox.make(args.sandbox, args.image)
            if args.command == "pin":
                suite = load_json(args.suite)
                make_plan(suite)
                pinned = runner.pin(suite, args.root, box)
                write_new(args.output, pinned)
                missing = make_plan(pinned)["not_ready_reasons"]
                print(f"Wrote {args.output}" + (f"; still missing: {'; '.join(missing)}" if missing else "; all pins set"))
            elif args.command == "check":
                suite = load_json(args.suite)
                make_plan(suite)
                lines, problems = runner.preflight(suite, args.root, box)
                print("\n".join(lines))
                print(f"{problems} problem(s)" if problems else "Ready.")
                return 1 if problems else 0
            elif args.command == "grade":
                if args.sandbox == "local" and not args.trusted:
                    raise ValueError("the local sandbox runs the folder's code on this machine with no isolation; "
                                     "use the docker sandbox, or add --trusted if you wrote the code yourself")
                checks, error = runner.grade(args.root, args.task, args.workspace, box, args.output)
                for item in checks:
                    print(f"{'pass' if item['passed'] else 'FAIL'}  {item['name']}"
                          + ("" if item["passed"] or not item.get("detail") else f"\n      {item['detail'][:300]}"))
                passed = sum(item["passed"] for item in checks)
                print(error if error else f"{passed}/{len(checks)} checks passed")
                return 0 if checks and passed == len(checks) else 1
            elif args.command == "validate-tasks":
                for entry in load_json(args.suite)["tasks"]:
                    verdict = runner.validate_task(args.root, entry, box)
                    print(f"{entry['id']}: seed {verdict['seed']}, reference {verdict['reference']} - ok")
            else:
                results = runner.execute(load_json(args.plan), args.root, box, limit=args.limit,
                                         harness=args.harness, model=args.model, repetition=args.repetition,
                                         retry_blocked=args.retry_blocked)
                print(f"Results: {results}")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
