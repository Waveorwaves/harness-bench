import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import threading

from . import adapters, judging, runner, sandbox, site
from .core import make_plan, report


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


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
    executor.add_argument("--harness", help="only run this harness id")
    executor.add_argument("--retry-blocked", action="store_true", help="discard blocked records and run them again")
    add_sandbox(executor)
    preparer = commands.add_parser("judge-prepare", help="build a blind side-by-side judging folder for a visual task")
    preparer.add_argument("--plan", required=True, type=Path)
    preparer.add_argument("--task", required=True)
    preparer.add_argument("--per-pair", type=int, help="at most this many matches between any two configurations")
    preparer.add_argument("--seed", type=int, default=0)
    preparer.add_argument("--replace", action="store_true",
                          help="overwrite an existing judging folder; picks already made for it will no longer match")
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
                                     replace=args.replace)
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
        elif args.command == "cleanup":
            print(f"{runner.cleanup()} item(s) removed")
        elif args.command == "adapters":
            for adapter in adapters.ADAPTERS.values():
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
                                         harness=args.harness, retry_blocked=args.retry_blocked)
                print(f"Results: {results}")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
