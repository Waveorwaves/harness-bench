# Methodology

How Harness Bench is designed, what each number means, and what the results can and cannot support.

## The question

Given the same model and the same task, does the choice of coding harness change how often the work is correct, how long it takes and what it costs? And is any difference bigger than the run-to-run noise of a single harness?

## Design

**A controlled matrix.** A suite crosses tasks × models × modes × harnesses × repetitions. Within one model and mode, only the harness changes: the prompt, starting files, time limit, container and model name are the same.

**Randomised blocks.** One block is one task, model, mode and repetition. Blocks are shuffled with the suite's seed, and the harnesses inside each block run back to back in shuffled order. Slow drift (provider load, rate limits) then hits every harness about equally instead of piling onto whichever ran last.

**Pinned inputs.** `pin` records a content hash of each task's seed and evaluator and the version each harness reports inside the sandbox. A run whose task files or harness version no longer match is recorded as blocked, not executed. The plan's id is a hash of the whole pinned suite, so results cannot be attached to a suite that has since changed.

**Isolation.** Every run gets a fresh workspace in its own container, with a throwaway home directory. The evaluator never enters that container. After the agent exits, the workspace is copied and evaluated in a second container with no network.

**Honest missing data.** A number the harness did not report is recorded as unknown, never as zero. Subscription usage is not converted into dollars.

**Nothing the agent leaves behind is trusted.** The size of its change is measured by comparing its files directly with the task's seed, without git, so no ignore file, attribute file, nested repository or local git setting can hide or distort it. Pipes, unreadable files, enormous files and over-long paths cannot stop the run. Its files are kept as an archive, not as a live folder, so nothing in them can act on whoever browses the results. A login it may have altered is never copied back unless the suite asks for that. The harness is told nothing about the experiment: no task id, run id or benchmark name appears in its environment or its repository.

**Stopping means stopped.** Ctrl-C, a closed terminal or `kill` all end the running agent, confirm its container is gone, and delete the copied logins; that clean-up cannot itself be interrupted. Only an outright `kill -9` leaves things behind, and `cleanup` removes them.

## Outcomes of a run

| Status | Meaning | Counts toward pass rate |
|---|---|---|
| passed | every hidden check passed | yes |
| failed | at least one hidden check failed | yes |
| timed out | the harness hit the time limit (its work is still evaluated and stored) | yes, as not passed |
| blocked | the run never fairly started or could not be graded: missing login, version drift, the harness would not launch, it exited with an error within 20 seconds having changed nothing, or the evaluation machinery itself was unavailable | no |

A harness that works for ten minutes and then crashes is a failure, not a blocked run. The 20-second rule looks only at time, exit code and whether any file changed, never at token counts, so that harnesses whose usage cannot be read are treated like the rest. It cannot catch a login failure that exits cleanly; `check` and a one-run probe per harness are there for that. An evaluator that runs but returns nothing is also counted as a failure, because a candidate can cause that, and such runs are listed separately in every report.

Blocked runs are reported beside the others so they cannot quietly disappear.

## Metrics

| Metric | Definition |
|---|---|
| Pass rate | passed ÷ attempted (attempted = passed + failed + timed out), with a 95% Wilson interval |
| Checks passed | per-run count of hidden checks, kept for partial credit and diagnosis |
| Time | wall-clock seconds from launch to exit, median per configuration |
| Tokens | uncached input, cached input, cache writes and output, kept separate so they are comparable across providers |
| Reported cost | what the harness says an API-billed run cost |
| List-price cost | tokens × the suite's price table; an estimate that puts subscription and API runs on one scale |
| Cost per pass | cost of every attempted run, failures included, ÷ passes. This is the number to decide with |
| Change size | files changed, lines added and removed against the seed, from a baseline the agent cannot reach; also shown as a multiple of the reference solution's change, a rough sign of work beyond what was asked |
| Turns and tool calls | where the harness reports them |
| Subagents started | where the harness reports it; shows whether a run in a "use subagents" mode really used any |
| Hardest checks | for each hidden check, the share of runs that passed it: what trips agents up, across harnesses |

## Statistics

**Pass-rate intervals** use the Wilson score interval, which behaves sensibly at the small sample sizes a personal budget allows (a 3-for-3 result is reported as 44%–100%, not 100% ± 0).

**Head-to-head comparisons** answer the question in the title of this page. For two harnesses on the same model and mode, each task's true pass probability is given the posterior Beta(passes + 1, failures + 1), and the difference between the two harnesses' task-averaged probabilities is sampled to get a 95% interval. The verdict is "clear" only when the whole interval is on one side of zero; otherwise it is "within noise". This interval covers rerunning the same tasks. It says nothing about tasks outside the suite.

Reports show the observed gap beside this plausible range. With few repeats the range sits closer to zero than the observed gap, sometimes excluding it: three passes out of three is treated as "probably reliable", not "certain".

A plain bootstrap over repetitions was the first design and was replaced after review: a task that passed every repetition resamples to itself, so the interval collapsed and two identical harnesses were called "clearly" different in up to three quarters of simulated one-repeat experiments.

**How many repeats?** `python3 scripts/calibrate_compare.py` simulates two harnesses on five tasks and counts how often the verdict is "clear":

| Repeats | Identical harnesses (false alarm) | True rates 80% vs 60% | 80% vs 40% | 90% vs 30% |
|---:|---:|---:|---:|---:|
| 1 | 0–1% | 0% | 3% | 8% |
| 2 | 0–2% | 6% | 31% | 69% |
| 3 | 1–4% | 12% | 52% | 91% |
| 5 | 1–4% | 29% | 78% | 100% |
| 8 | 3–4% | 49% | 97% | 100% |

Two things follow. A "clear" verdict can be trusted: false alarms stay under 5%. But "within noise" is weak evidence of no difference: with three repeats, a real 40-point gap is missed about half the time, and a 20-point gap almost always. Five repeats is a sensible minimum for a pilot, and small gaps need more tasks, not only more repeats.

**Do the harnesses differ at all?** Before reading any pair, each model and mode gets one permutation test. If the harness made no difference, then within a block (the same task and repetition) it would not matter which harness produced which outcome; so outcomes are shuffled among the harnesses inside every block, and the spread of pass rates actually seen is compared with the shuffled spreads. This is exact for the randomised-block design, needs no distributional assumption, and is a single test however many harnesses there are. Simulated with four harnesses on five tasks:

| Repeats | No real difference (false alarm) | One harness at 80%, three at 50% | 90%, 70%, 50%, 30% |
|---:|---:|---:|---:|
| 1 | 1–3% | 5% | 20% |
| 3 | 4–6% | 36% | 87% |
| 5 | 4% | 61% | 97% |

These are the figures `scripts/calibrate_compare.py` prints, from 300 simulated experiments per cell, so each carries a point or two of simulation noise; the test's false-alarm rate is 5% by construction.

Read the overall test first. If it finds nothing, the pairwise verdicts below it are not worth interpreting.

**Multiple comparisons.** Eight harnesses give 28 pairs per model and mode. The report states how many pairs were compared. Because the per-pair false-alarm rate is under 5%, a handful of "clear" verdicts among 28 pairs deserves a rerun before it is believed.

**Visual tasks** are ranked from blind side-by-side picks with the Bradley–Terry model, shown on an Elo-style scale with bootstrap intervals. Pairwise picks are used because people (and models) are far more consistent at "which of these two is better" than at giving a score out of ten.

**Judge agreement.** When a model judges the same pairs as a person, the report gives raw agreement and Cohen's kappa. A model judge is asked each pair twice with the sides swapped; if its answer follows the side rather than the attempt, the pair is recorded as a tie and counted, which measures and removes position bias.

## How tasks are validated

A task is only usable if all of these hold:

1. **The untouched seed fails** the hidden checks (`validate-tasks`).
2. **A reference solution passes** all of them (`validate-tasks`).
3. **Every check tests behaviour stated in the prompt or the seed's README.** Hidden inputs are fine; hidden requirements are not.
4. **An independent solver, given only the prompt and seed, can pass.** See the calibration table in [tasks.md](tasks.md).
5. **A weaker solver does not always pass**, so the task can tell configurations apart.
6. **The checks keep catching known defects.** Six tasks store a real flawed attempt (`variants/known-defect`) with the list of checks it must fail. The test suite replays each one and requires exactly those failures, so editing a check cannot quietly stop it catching what it once caught.

## Threats to validity

- **Few tasks.** Nine tasks are a pilot. Conclusions apply to these tasks, mostly in JavaScript, at this size.
- **Task authorship.** The tasks, references and checks were written by one author with an AI assistant. Independent blind solves reduce, but do not remove, the risk that a check encodes an unstated assumption.
- **Model drift.** Providers change models behind a fixed name. Results carry dates; rerun before relying on old numbers.
- **Harness defaults.** A harness's own system prompt, tool set and default settings are part of what is being measured. Where a setting can be matched (model, reasoning effort) it is; where it cannot, the comparison is of whole configurations.
- **The container is not your laptop.** Harnesses run headless, without your personal configuration, memory files or plugins. That is fairer and less like daily use.
- **Software rendering.** Visual tasks are screenshotted without a GPU. Frame rate there is indicative only and is not a pass condition.
- **Cost estimates.** List-price cost assumes the price table is right and that token counts are complete. Cache-write pricing is missing for some providers and is then left out of the estimate rather than guessed.
- **Logins.** A harness's login file is copied into the container, where the agent can read it. A refresh made there is discarded unless write-back is turned on, and write-back cannot tell a genuine refresh from content the agent wrote. A login kept only for the benchmark limits both risks.
- **Container runtimes.** Written for Docker Desktop on macOS and ordinary Docker on Linux. Rootless Docker, Podman and SELinux hosts need mount options this does not set.
- **Evaluator trust.** Candidate code runs inside the evaluator's process or page. A candidate that set out to cheat the checks could; nothing here defends against a deliberately adversarial agent.
- **Judging.** Picks reflect the judges' taste. Report who judged, how many pairs, and the agreement between judges.

## What a result does and does not say

A "clear" head-to-head verdict says: on these tasks, with this model, rerunning would very probably show the same ordering. It does not say the harness is better in general, on your codebase, or with a different model. Treat the suite as a way to replace a hunch with a number for the conditions you tested, and to notice when a difference you thought you saw is noise.
