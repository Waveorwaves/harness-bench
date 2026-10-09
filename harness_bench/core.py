"""Standard-library experiment planning and reporting. This module never launches a harness."""

import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics

from . import tasks


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value)


def price_table(value):
    return value is None or (isinstance(value, dict) and value
                             and set(value) <= {"input", "cached_input", "cache_write", "output"}
                             and all(number(v) for v in value.values()))


def strings(value):
    return isinstance(value, list) and all(nonempty(item) for item in value)


def make_plan(suite):
    require(isinstance(suite, dict), "suite must be an object")
    version = suite.get("schema_version")
    require(type(version) is int and version in (1, 2), "unsupported suite schema")
    require(identifier(suite.get("suite_id")), "invalid suite_id")
    require(suite.get("comparison") == "controlled", "starter supports controlled comparisons only")
    require(type(suite.get("seed")) is int, "seed must be an integer")
    require(integer(suite.get("repetitions"), 1), "repetitions must be positive")
    if version == 1:
        require(nonempty(suite.get("model")), "model is required")
        require(nonempty(suite.get("reasoning_effort")), "reasoning_effort is required")
    else:
        # Schema 2 crosses every harness with several models and modes (e.g. single vs subagents).
        for collection in ("models", "modes"):
            entries = suite.get(collection)
            require(isinstance(entries, list) and entries, f"{collection} must be a nonempty list")
            seen = set()
            for entry in entries:
                require(isinstance(entry, dict) and identifier(entry.get("id")), f"invalid {collection} id")
                require(entry["id"] not in seen, f"duplicate {collection} id: {entry['id']}")
                seen.add(entry["id"])
        for model in suite["models"]:
            require(nonempty(model.get("name")), f"model name is required: {model['id']}")
            effort = model.get("reasoning_effort")
            require(effort is None or nonempty(effort), f"invalid reasoning_effort: {model['id']}")
            require(price_table(model.get("price_per_mtok")), f"invalid price_per_mtok: {model['id']}")
            require(model.get("billing", "api") in ("api", "subscription"), f"invalid billing: {model['id']}")
            names = model.get("harness_names", {})
            require(isinstance(names, dict) and all(nonempty(v) for v in names.values()),
                    f"invalid harness_names: {model['id']}")
            # A model may need different provider settings in each harness.
            for field in ("harness_args", "harness_env"):
                extra = model.get(field, {})
                require(isinstance(extra, dict) and all(strings(v) for v in extra.values()),
                        f"invalid {field}: {model['id']}")
        for mode in suite["modes"]:
            require(isinstance(mode.get("prompt_suffix", ""), str), f"invalid prompt_suffix: {mode['id']}")
    budget = suite.get("budget")
    require(isinstance(budget, dict), "budget is required")
    require(integer(budget.get("timeout_seconds"), 1), "timeout_seconds must be positive")
    require(integer(budget.get("max_retries")), "max_retries must be nonnegative")

    missing = []
    for collection, pins in (("tasks", ("seed_revision", "evaluator_revision")),
                             ("harnesses", ("version",))):
        entries = suite.get(collection)
        require(isinstance(entries, list) and entries, f"{collection} must be a nonempty list")
        seen = set()
        for entry in entries:
            require(isinstance(entry, dict), f"{collection} entries must be objects")
            name = entry.get("id")
            require(identifier(name), f"invalid {collection} id")
            require(name not in seen, f"duplicate {collection} id: {name}")
            seen.add(name)
            for field in ("model", "reasoning_effort", "budget"):
                require(field not in entry or (field in suite and entry[field] == suite[field]),
                        f"controlled comparison cannot override {field}: {name}")
            for pin in pins:
                value = entry.get(pin)
                require(value is None or nonempty(value), f"invalid {pin}: {name}")
                if value is None:
                    missing.append(f"{collection}/{name}: pin {pin}")
            if collection == "tasks":
                require(nonempty(entry.get("spec")), f"missing task spec: {name}")
            elif version == 2:
                require(identifier(entry.get("adapter")), f"harness adapter is required: {name}")
                require(entry.get("billing", "api") in ("api", "subscription"), f"invalid billing: {name}")
                for field in ("args", "env", "credentials"):
                    require(strings(entry.get(field, [])), f"{field} must be a list of strings: {name}")
                require(type(entry.get("write_back_logins", False)) is bool, f"write_back_logins must be true or false: {name}")
                # A harness run by hand can be given fewer repeats than the rest.
                require(integer(entry.get("repetitions", 1), 1), f"harness repetitions must be a positive whole number: {name}")
                # A harness can be limited to the modes, models and tasks it is able to run.
                for field in ("modes", "models", "tasks"):
                    chosen = entry.get(field)
                    known = {item["id"] for item in suite[field]}
                    require(chosen is None or (strings(chosen) and chosen and set(chosen) <= known),
                            f"harness {field} must name suite {field}: {name}")

    # Clone before hashing so callers cannot mutate an existing plan through the input.
    configuration = json.loads(json.dumps(suite, allow_nan=False))
    serialized = json.dumps(configuration, sort_keys=True, separators=(",", ":"))
    plan_id = hashlib.sha256(serialized.encode()).hexdigest()
    rng = random.Random(configuration["seed"])
    models = configuration.get("models", [None])
    modes = configuration.get("modes", [None])
    blocks = [(task, model, mode, repetition)
              for task in configuration["tasks"] for model in models for mode in modes
              for repetition in range(1, configuration["repetitions"] + 1)]
    rng.shuffle(blocks)
    runs = []
    for task, model, mode, repetition in blocks:
        harnesses = list(configuration["harnesses"])
        rng.shuffle(harnesses)
        for harness in harnesses:
            if mode and (mode["id"] not in harness.get("modes", [mode["id"]])
                         or model["id"] not in harness.get("models", [model["id"]])
                         or task["id"] not in harness.get("tasks", [task["id"]])
                         or repetition > harness.get("repetitions", repetition)):
                continue
            run = {"task_id": task["id"], "harness_id": harness["id"], "repetition": repetition}
            parts = [task["id"], harness["id"]]
            if model:
                run.update(model_id=model["id"], mode_id=mode["id"])
                parts += [model["id"], mode["id"]]
            runs.append({"run_id": ":".join([plan_id[:16], *parts, str(repetition)]), **run})
    return {"schema_version": 1, "plan_id": plan_id, "configuration": configuration,
            "ready": not missing, "not_ready_reasons": missing, "runs": runs}


def validate_plan(plan):
    require(isinstance(plan, dict), "plan must be an object")
    expected = make_plan(plan.get("configuration"))
    require(plan == expected, "plan differs from its configuration; generate a new plan")


def validate_results(plan, records):
    validate_plan(plan)
    require(not records or plan["ready"], "results require a plan with all revisions and versions pinned")
    planned = {run["run_id"]: run for run in plan["runs"]}
    seen = set()
    for record in records:
        require(isinstance(record, dict), "result must be an object")
        run_id = record.get("run_id")
        require(isinstance(run_id, str) and run_id in planned, "unknown run_id")
        require(run_id not in seen, f"duplicate result: {run_id}")
        seen.add(run_id)
        status = record.get("status")
        require(status in ("passed", "failed", "timed_out", "blocked"), "invalid status")
        require("elapsed_seconds" in record, "elapsed_seconds is required")
        elapsed = record["elapsed_seconds"]
        require(number(elapsed) or (status == "blocked" and elapsed is None), "invalid elapsed_seconds")
        for field in ("human_interventions", "attempts", "checks_passed", "checks_total"):
            require(integer(record.get(field)), f"{field} must be a nonnegative integer")
        require(number(record.get("human_minutes")), "invalid human_minutes")
        require(record["attempts"] > 0 or status == "blocked", "only blocked runs can have zero attempts")
        require(record["attempts"] <= plan["configuration"]["budget"]["max_retries"] + 1,
                "attempts exceed retry budget")
        require(record["checks_passed"] <= record["checks_total"], "passed checks exceed total")
        if status == "passed":
            require(record["checks_total"] > 0 and record["checks_passed"] == record["checks_total"],
                    "passed status requires a nonempty, fully passing evaluation")
        require(nonempty(record.get("evidence_ref")), "evidence_ref is required")
        for field in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens",
                      "turns", "tool_calls", "subagents", "files_changed", "lines_added", "lines_removed"):
            require(record.get(field) is None or integer(record[field]), f"invalid {field}")
        for field in ("cost_usd", "list_price_usd"):
            require(record.get(field) is None or number(record[field]), f"invalid {field}")


def wilson(passed, total, z=1.96):
    """95% Wilson score interval; behaves sensibly for the tiny samples a pilot produces."""
    if not total:
        return None
    rate = passed / total
    centre = rate + z * z / (2 * total)
    spread = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total))
    scale = 1 + z * z / total
    return max(0.0, (centre - spread) / scale), min(1.0, (centre + spread) / scale)


def median(values):
    return statistics.median(values) if values else None


def per_pass(results, field, passed):
    """Cost of every attempted run, failures included, divided by the passes it bought."""
    attempted = [r for r in results if r["status"] != "blocked"]
    if not passed or any(r.get(field) is None for r in attempted):
        return None
    return sum(r[field] for r in attempted) / passed


def per_run(results, field):
    attempted = [r for r in results if r["status"] != "blocked"]
    if not attempted or any(r.get(field) is None for r in attempted):
        return None
    return sum(r[field] for r in attempted) / len(attempted)


def compare(plan, records, draws=4000, seed=0):
    """Pairwise harness differences in pass rate, with an interval for run-to-run noise.

    Within one model and mode, each task's true pass probability for a harness is given the
    posterior Beta(passes + 1, failures + 1), and the difference between two harnesses'
    task-averaged probabilities is sampled. Tasks count equally. A plain bootstrap is not used
    because a cell that passed (or failed) every repetition would resample to itself and claim
    certainty from as little as one run. In simulation with identical harnesses this calls a
    gap "clear" in under 5% of experiments at every repeat count tried (docs/methodology.md).

    The interval answers "is this gap bigger than rerunning the same tasks would produce?",
    not "would it hold on other tasks".
    """
    by_id = {record["run_id"]: record for record in records}
    configuration = plan["configuration"]
    cells = {}
    for run in plan["runs"]:
        status = by_id.get(run["run_id"], {}).get("status")
        if status in ("passed", "failed", "timed_out"):
            slice_key = (run.get("model_id", configuration.get("model")), run.get("mode_id", "single"))
            cells.setdefault(slice_key, {}).setdefault(run["harness_id"], {}).setdefault(
                run["task_id"], []).append(status == "passed")
    rng = random.Random(seed)
    mean = statistics.fmean
    comparisons = []
    for (model, mode), harnesses in cells.items():
        names = [h["id"] for h in configuration["harnesses"] if h["id"] in harnesses]
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                tasks = sorted(set(harnesses[first]) & set(harnesses[second]))
                if not tasks:
                    continue
                observed = (mean(mean(harnesses[first][task]) for task in tasks)
                            - mean(mean(harnesses[second][task]) for task in tasks))

                def plausible(name):
                    return mean(rng.betavariate(sum(outcomes) + 1, len(outcomes) - sum(outcomes) + 1)
                                for outcomes in (harnesses[name][task] for task in tasks))

                sampled = sorted(plausible(first) - plausible(second) for _ in range(draws))
                low, high = sampled[int(0.025 * draws)], sampled[min(draws - 1, int(0.975 * draws))]
                better, worse = (first, second) if observed >= 0 else (second, first)
                if observed < 0:
                    observed, low, high = -observed, -high, -low
                comparisons.append({
                    "model": model, "mode": mode, "better": better, "worse": worse, "tasks": len(tasks),
                    "difference": observed, "low": low, "high": high,
                    # "Clear" means the whole interval is on one side of zero.
                    "clear": low > 0,
                })
    models = [model["id"] for model in configuration.get("models", [])]
    modes = [mode["id"] for mode in configuration.get("modes", [])]
    comparisons.sort(key=lambda item: (models.index(item["model"]) if item["model"] in models else 0,
                                       modes.index(item["mode"]) if item["mode"] in modes else 0))
    return comparisons


def omnibus(plan, records, shuffles=2000, seed=0):
    """Do the harnesses differ at all? One permutation test per model and mode.

    If the harness made no difference, then within one block (same task, same repetition) it
    would not matter which harness produced which outcome. So the outcomes are shuffled among
    the harnesses inside every block, many times, and the spread of the harnesses' pass rates
    is compared with the spread actually seen. The p-value is the share of shuffles that are
    at least as spread out. One test per slice avoids the many-pairs problem of `compare`.
    """
    by_id = {record["run_id"]: record for record in records}
    configuration = plan["configuration"]
    slices = {}
    for run in plan["runs"]:
        status = by_id.get(run["run_id"], {}).get("status")
        if status in ("passed", "failed", "timed_out"):
            key = (run.get("model_id", configuration.get("model")), run.get("mode_id", "single"))
            slices.setdefault(key, {}).setdefault((run["task_id"], run["repetition"]), []).append(
                (run["harness_id"], status == "passed"))
    rng = random.Random(seed)

    def spread(blocks):
        passed, attempted = {}, {}
        for block in blocks:
            for harness, outcome in block:
                passed[harness] = passed.get(harness, 0) + outcome
                attempted[harness] = attempted.get(harness, 0) + 1
        rates = [passed[harness] / attempted[harness] for harness in attempted]
        return statistics.pvariance(rates), max(rates) - min(rates), len(rates)

    tests = []
    for (model, mode), blocks in slices.items():
        blocks = [block for block in blocks.values() if len(block) > 1]
        if not blocks:
            continue
        observed, gap, harnesses = spread(blocks)
        if harnesses < 2:
            continue
        extreme = 0
        for _ in range(shuffles):
            shuffled = []
            for block in blocks:
                outcomes = [outcome for _, outcome in block]
                rng.shuffle(outcomes)
                shuffled.append([(harness, outcome) for (harness, _), outcome in zip(block, outcomes)])
            extreme += spread(shuffled)[0] >= observed - 1e-12
        tests.append({"model": model, "mode": mode, "harnesses": harnesses, "blocks": len(blocks),
                      "spread": gap, "p_value": (1 + extreme) / (1 + shuffles)})
    models = [model["id"] for model in configuration.get("models", [])]
    modes = [mode["id"] for mode in configuration.get("modes", [])]
    tests.sort(key=lambda item: (models.index(item["model"]) if item["model"] in models else 0,
                                 modes.index(item["mode"]) if item["mode"] in modes else 0))
    return tests


def reference_sizes(plan, root):
    """Lines the reference solution adds and removes, per task, where the task folders can be read."""
    sizes = {}
    for entry in plan["configuration"]["tasks"] if root else []:
        try:
            change = tasks.reference_change(tasks.load(root, entry))
        except (OSError, ValueError):
            change = None
        if change and change[1] + change[2]:
            sizes[entry["id"]] = change[1] + change[2]
    return sizes


def private(text, root):
    """Take this machine's folder names out of text that will be published in a report."""
    for folder, short in ((str(Path(root).resolve()), "."), (str(Path.home()), "~")):
        text = text.replace(folder, short)
    return re.sub(r"/(private/)?var/folders/\S*?/T/", "<tmp>/", text)


def run_details(plan, records, root):
    """Per-run facts for the HTML page, with each run's failed hidden checks read from its folder."""
    by_id = {record["run_id"]: record for record in records}
    configuration = plan["configuration"]
    sizes = reference_sizes(plan, root)
    runs, checks = [], {}
    for run in plan["runs"]:
        record = by_id.get(run["run_id"])
        if not record:
            continue
        failed = None
        result = Path(root) / record["evidence_ref"] / "evaluation" / "result.json" if root else None
        if result and result.is_file() and record["status"] != "blocked":
            try:
                verdicts = json.loads(result.read_text(encoding="utf-8"))["checks"]
                verdicts = [c for c in verdicts if isinstance(c, dict) and type(c.get("passed")) is bool]
            except (OSError, ValueError, KeyError, TypeError):
                verdicts = []
            # No readable verdicts means the failed checks are unknown, which is not the same as none.
            failed = [{"name": str(c.get("name")), "detail": private(str(c.get("detail", "")), root)[:240]}
                      for c in verdicts if not c["passed"]] if verdicts else None
            for check in verdicts:
                if isinstance(check, dict) and type(check.get("passed")) is bool:
                    tally = checks.setdefault((run["task_id"], str(check.get("name"))), [0, 0])
                    tally[0] += check["passed"]
                    tally[1] += 1
        runs.append({
            "task": run["task_id"], "harness": run["harness_id"],
            "model": run.get("model_id", configuration.get("model")), "mode": run.get("mode_id", "single"),
            "repetition": run["repetition"], "status": record["status"], "folder": record["evidence_ref"],
            "failed": failed,
            "reason": private(record.get("blocked_reason") or record.get("evaluator_error")
                              or record.get("harness_error") or "", root or ".") or None,
            # Lines touched, as a multiple of what the reference solution touches.
            "change_ratio": (round((record["lines_added"] + record["lines_removed"]) / sizes[run["task_id"]], 2)
                             if run["task_id"] in sizes and record.get("lines_added") is not None
                             and record["status"] != "blocked" else None),
            **{field: record.get(field) for field in (
                "checks_passed", "checks_total", "elapsed_seconds", "input_tokens", "cached_input_tokens",
                "output_tokens", "cost_usd", "list_price_usd", "turns", "tool_calls", "subagents",
                "files_changed", "lines_added", "lines_removed", "exit_code")},
            # Anything a person added about this run: an earlier attempt, a figure that was derived.
            "note": record.get("note"),
        })
    hardest = sorted(({"task": task, "name": name, "passed": passed, "runs": total}
                      for (task, name), (passed, total) in checks.items()),
                     key=lambda item: (item["passed"] / item["runs"], item["task"], item["name"]))
    return runs, hardest


def summarize(plan, records, root=None):
    """One row per harness, model and mode. The markdown report and the HTML page both read this.

    With `root`, each run's failed checks are read from its folder, for the page's run explorer.
    """
    validate_results(plan, records)
    by_id = {record["run_id"]: record for record in records}
    configuration = plan["configuration"]
    mock = {h["id"] for h in configuration["harnesses"] if h.get("adapter") == "mock"}
    by_hand = {h["id"] for h in configuration["harnesses"] if h.get("adapter") == "manual"}
    groups = {}
    for run in plan["runs"]:
        key = (run["harness_id"], run.get("model_id", configuration.get("model")), run.get("mode_id", "single"))
        groups.setdefault(key, []).append(run)
    rows = []
    for harness in configuration["harnesses"]:
        for (harness_id, model, mode), runs in groups.items():
            if harness_id != harness["id"]:
                continue
            results = [by_id[run["run_id"]] for run in runs if run["run_id"] in by_id]
            counts = {status: sum(r["status"] == status for r in results)
                      for status in ("passed", "failed", "timed_out", "blocked")}
            # Blocked runs never reached the model, so they are not evidence about pass rate.
            attempted = len(results) - counts["blocked"]
            tasks = {}
            for run in runs:
                cell = tasks.setdefault(run["task_id"], {"passed": 0, "attempted": 0, "planned": 0})
                cell["planned"] += 1
                status = by_id.get(run["run_id"], {}).get("status")
                cell["passed"] += status == "passed"
                cell["attempted"] += status in ("passed", "failed", "timed_out")
            rows.append({
                "harness": harness_id, "mock": harness_id in mock, "manual": harness_id in by_hand,
                "model": model, "mode": mode,
                **counts, "pending": len(runs) - len(results), "recorded": len(results), "attempted": attempted,
                "pass_rate": counts["passed"] / attempted if attempted else None,
                "interval": wilson(counts["passed"], attempted),
                # Time is for runs that really ran; a blocked run's seconds say nothing about the harness.
                "seconds": median([r["elapsed_seconds"] for r in results
                                   if r["status"] != "blocked" and r["elapsed_seconds"] is not None]),
                "seconds_known": sum(r["status"] != "blocked" and r["elapsed_seconds"] is not None for r in results),
                "evaluator_errors": sum(bool(r.get("evaluator_error")) for r in results),
                # Did runs in a "use subagents" mode really start any? Known only where the harness reports it.
                "subagents_known": sum(r.get("subagents") is not None for r in results),
                "subagents_used": sum(bool(r.get("subagents")) for r in results),
                **{field: median([r[field] for r in results if r.get(field) is not None])
                   for field in ("input_tokens", "cached_input_tokens", "output_tokens", "turns", "tool_calls")},
                **{f"{field}_total": sum(r[field] for r in results if r.get(field) is not None)
                   for field in ("cost_usd", "list_price_usd")},
                **{f"{field}_known": sum(r.get(field) is not None for r in results)
                   for field in ("cost_usd", "list_price_usd")},
                # A run's reported cost can be a floor worked out from a total, not a figure read for that run.
                "cost_usd_floor": any(r.get("cost_usd_is_floor") for r in results),
                "cost_usd_per_run": per_run(results, "cost_usd"),
                "list_price_usd_per_run": per_run(results, "list_price_usd"),
                "cost_usd_per_pass": per_pass(results, "cost_usd", counts["passed"]),
                "list_price_usd_per_pass": per_pass(results, "list_price_usd", counts["passed"]),
                "human_interventions": sum(r["human_interventions"] for r in results),
                "human_minutes": sum(r["human_minutes"] for r in results),
                "tasks": tasks,
            })
    details = run_details(plan, records, root)
    for row in rows:
        ratios = [run["change_ratio"] for run in details[0] if run["change_ratio"] is not None
                  and (run["harness"], run["model"], run["mode"]) == (row["harness"], row["model"], row["mode"])]
        row["change_ratio"] = median(ratios)
    # Plan order is shuffled; present rows in the suite's own order.
    models = [model["id"] for model in configuration.get("models", [])]
    modes = [mode["id"] for mode in configuration.get("modes", [])]
    harnesses = [harness["id"] for harness in configuration["harnesses"]]
    rows.sort(key=lambda row: (harnesses.index(row["harness"]),
                               models.index(row["model"]) if row["model"] in models else 0,
                               modes.index(row["mode"]) if row["mode"] in modes else 0))
    return {
        "suite_id": configuration["suite_id"], "plan_id": plan["plan_id"], "ready": plan["ready"],
        "not_ready_reasons": plan["not_ready_reasons"], "recorded": len(records), "planned": len(plan["runs"]),
        "repetitions": configuration["repetitions"], "has_mock": bool(mock), "has_manual": bool(by_hand),
        "tasks": [task["id"] for task in configuration["tasks"]],
        "models": list(dict.fromkeys(row["model"] for row in rows)),
        "modes": list(dict.fromkeys(row["mode"] for row in rows)),
        "rows": rows,
        "comparisons": compare(plan, records),
        "overall": omnibus(plan, records),
        **dict(zip(("runs", "checks"), details)),
    }


def known(row, field, digits=4):
    return f"{row[field + '_total']:.{digits}f} ({row[field + '_known']}/{row['recorded']})" if row[field + "_known"] else "unknown"


def report(plan, records, root=None):
    summary = summarize(plan, records, root)
    lines = [f"# {summary['suite_id']}", "",
             f"Plan: {summary['plan_id']}",
             f"Pins complete: {'yes' if summary['ready'] else 'no'}.",
             f"Recorded: {summary['recorded']}/{summary['planned']}; pending: {summary['planned'] - summary['recorded']}.", "",
             "| Harness | Model | Mode | Passed | Failed | Timed out | Blocked | Pending | Pass rate (95% CI) | Median measured seconds | Known cost USD (coverage) | USD per pass | List-price USD (coverage) | List-price USD per pass | Median tokens in / cached / out | Human interventions / minutes |",
             "|---|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|---|---:|---|---|"]
    names = {}
    for row in summary["rows"]:
        name = names[id(row)] = row["harness"] + (" (mock)" if row["mock"] else " (manual)" if row["manual"] else "")
        rate = (f"{row['pass_rate']:.0%} ({row['interval'][0]:.0%}–{row['interval'][1]:.0%}, n={row['attempted']})"
                if row["attempted"] else "unknown")
        seconds = f"{row['seconds']:.2f} ({row['seconds_known']}/{row['attempted']})" if row["seconds_known"] else "unknown"
        tokens = " / ".join("unknown" if row[field] is None else f"{row[field]:.0f}"
                            for field in ("input_tokens", "cached_input_tokens", "output_tokens"))
        each = ["unknown" if row[field] is None else f"{row[field]:.4f}"
                for field in ("cost_usd_per_pass", "list_price_usd_per_pass")]
        human = f"{row['human_interventions']} / {row['human_minutes']:.2f}" if row["recorded"] else "unknown"
        cells = [name, row["model"], row["mode"], row["passed"], row["failed"], row["timed_out"], row["blocked"],
                 row["pending"], rate, seconds, known(row, "cost_usd"), each[0], known(row, "list_price_usd"),
                 each[1], tokens, human]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    if len(summary["tasks"]) > 1:
        lines.extend(["", "Passes out of attempted runs, by task:", "",
                      "| Harness | Model | Mode | " + " | ".join(summary["tasks"]) + " |",
                      "|---|---|---|" + "---|" * len(summary["tasks"])])
        for row in summary["rows"]:
            cells = [f"{row['tasks'][task]['passed']}/{row['tasks'][task]['attempted']}" if task in row["tasks"] else "–"
                     for task in summary["tasks"]]
            lines.append("| " + " | ".join([names[id(row)], str(row["model"]), row["mode"], *cells]) + " |")
    if summary["overall"]:
        lines.extend(["", "Do the harnesses differ at all? One permutation test per model and mode (outcomes shuffled among harnesses within each task and repetition):", "",
                      "| Model | Mode | Harnesses | Best minus worst pass rate | p-value |", "|---|---|---:|---:|---:|"])
        for item in summary["overall"]:
            lines.append(f"| {item['model']} | {item['mode']} | {item['harnesses']} | {round(item['spread'] * 100)} pts | {'<0.001' if item['p_value'] < 0.001 else format(item['p_value'], '.3f')} |")
        lines.extend(["", "A small p-value (conventionally below 0.05) means a spread this large would be unusual if the harness made no difference."])
    if summary["comparisons"]:
        lines.extend(["", "Head to head, same model and mode (difference in pass rate, with a 95% interval for run-to-run noise on these tasks):", "",
                      "| Model | Mode | Better | Worse | Observed gap | Plausible range | Verdict |", "|---|---|---|---|---:|---|---|"])
        for item in summary["comparisons"]:
            lines.append(f"| {item['model']} | {item['mode']} | {item['better']} | {item['worse']} | "
                         f"{round(item['difference'] * 100):+d} pts | {round(item['low'] * 100):+d} to {round(item['high'] * 100):+d} pts | "
                         f"{'clear' if item['clear'] else 'within noise'} |")
        lines.extend(["", "The plausible range is cautious: with few repeats it sits closer to zero than the observed gap, because a task passed three times out of three may still fail the fourth. "
                      f"{len(summary['comparisons'])} pairs were compared without correction. For two identical harnesses, fewer than 1 in 20 pairs would be called 'clear' by chance."])
    teams = [(names[id(row)], row) for row in summary["rows"] if row["subagents_known"]]
    if teams:
        lines.extend(["", "Runs that started at least one subagent, out of runs where the harness reports it:", ""]
                     + [f"- {name} / {row['model']} / {row['mode']}: {row['subagents_used']}/{row['subagents_known']}"
                        for name, row in teams])
    broken = [(names[id(row)], row) for row in summary["rows"] if row["evaluator_errors"]]
    if broken:
        lines.extend(["", "Runs where the evaluator itself produced no result. They are counted as failures; inspect them before trusting these rows:", ""]
                     + [f"- {name} / {row['model']} / {row['mode']}: {row['evaluator_errors']}" for name, row in broken])
    hardest = [item for item in summary["checks"] if item["passed"] < item["runs"]][:10]
    if hardest:
        lines.extend(["", "Hidden checks failed most often, across every harness:", "",
                      "| Task | Check | Passed |", "|---|---|---:|"]
                     + [f"| {item['task']} | {item['name']} | {item['passed']}/{item['runs']} |" for item in hardest])
    if summary["not_ready_reasons"]:
        lines.extend(["", "Missing pins:", ""] + [f"- {reason}" for reason in summary["not_ready_reasons"]])
    if summary["has_manual"]:
        lines.extend(["", "Rows marked (manual) were run by hand in a desktop app, outside the sandbox, with the model chosen in the app. Their time includes the person's handling unless a time was typed in, and tokens and cost are whatever was typed in."])
    if summary["has_mock"]:
        lines.extend(["", "Rows marked (mock) come from the built-in fake agent that exercises the pipeline; they are not benchmark measurements."])
    lines.extend(["", "No ranking is inferred. Missing measurements remain unknown. Timing includes all measured statuses; compare quality and failures alongside speed.",
                  "Pass rate excludes blocked runs. Cost per pass divides the cost of every attempted run, failures included, by the number of passes. Known cost is what the harness reported for API billing; list-price cost is tokens multiplied by the suite's price table and is an estimate, not an invoice.",
                  "Version pins alone do not verify access, tool parity, environment isolation, or evidence contents."])
    return "\n".join(lines) + "\n"
