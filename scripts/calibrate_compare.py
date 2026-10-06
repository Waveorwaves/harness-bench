"""How often do the head-to-head verdict and the overall test raise a flag, by simulation?

Two simulated harnesses are run through the real `compare` on a plan of five tasks.
With equal true pass rates, "clear" is a false alarm. With different rates, it is a detection.

    python3 scripts/calibrate_compare.py            # about five minutes
"""

import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness_bench.core import compare, make_plan, omnibus  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TRIALS = 500


def plan_with(repetitions, harnesses=2):
    suite = json.loads((ROOT / "suites/demo-mock.json").read_text())
    suite.update(repetitions=repetitions, models=suite["models"][:1], modes=suite["modes"][:1],
                 harnesses=suite["harnesses"][:harnesses])
    for task in suite["tasks"]:
        task.update(seed_revision="simulated", evaluator_revision="simulated")
    for harness in suite["harnesses"]:
        harness["version"] = "simulated"
    return make_plan(suite)


def share_called_clear(plan, first_rate, second_rate, rng):
    first = plan["configuration"]["harnesses"][0]["id"]
    clear = 0
    for trial in range(TRIALS):
        records = [{"run_id": run["run_id"],
                    "status": "passed" if rng.random() < (first_rate if run["harness_id"] == first else second_rate) else "failed"}
                   for run in plan["runs"]]
        clear += compare(plan, records, draws=800, seed=trial)[0]["clear"]
    return clear / TRIALS


def share_overall_significant(plan, rates, rng, trials=300):
    names = [harness["id"] for harness in plan["configuration"]["harnesses"]]
    hits = 0
    for trial in range(trials):
        records = [{"run_id": run["run_id"],
                    "status": "passed" if rng.random() < rates[names.index(run["harness_id"])] else "failed"}
                   for run in plan["runs"]]
        hits += omnibus(plan, records, shuffles=400, seed=trial)[0]["p_value"] < 0.05
    return hits / trials


def overall_table(rng):
    print("\nOverall test (p below 0.05), 4 harnesses, 5 tasks, 300 simulated experiments per cell.\n")
    print("| Repeats | All four at 50% | All four at 80% | One at 80%, three at 50% | 90%, 70%, 50%, 30% |")
    print("|---:|---:|---:|---:|---:|")
    for repetitions in (1, 3, 5):
        plan = plan_with(repetitions, harnesses=4)
        cells = [share_overall_significant(plan, rates, rng) for rates in
                 ((0.5,) * 4, (0.8,) * 4, (0.8, 0.5, 0.5, 0.5), (0.9, 0.7, 0.5, 0.3))]
        print(f"| {repetitions} | " + " | ".join(f"{cell:.0%}" for cell in cells) + " |")
    print("\nThe first two columns are false alarms and should be about 5%. The last two are detections.")


def main():
    rng = random.Random(20261005)
    print(f"{TRIALS} simulated experiments per cell, 5 tasks, two harnesses.\n")
    print("| Repeats | Same rate 20% | Same rate 50% | Same rate 80% | 80% vs 60% | 80% vs 40% | 90% vs 30% |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for repetitions in (1, 2, 3, 5, 8):
        plan = plan_with(repetitions)
        cells = [share_called_clear(plan, a, b, rng) for a, b in
                 ((0.2, 0.2), (0.5, 0.5), (0.8, 0.8), (0.8, 0.6), (0.8, 0.4), (0.9, 0.3))]
        print(f"| {repetitions} | " + " | ".join(f"{cell:.0%}" for cell in cells) + " |")
    print("\nThe first three columns are false alarms and should stay under 5%. The last three are the chance of detecting a real gap.")
    overall_table(rng)


if __name__ == "__main__":
    main()
