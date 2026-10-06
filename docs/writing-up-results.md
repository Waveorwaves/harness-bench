# Writing up results

A template for the day real runs exist. Fill in every line; where you cannot, say so. The point of the template is that a reader can tell what was measured, how much to trust it, and what was not looked at.

## Setup

- **Date of the runs** and how long they took. Providers change models behind a fixed name.
- **Suite** file and plan id. Tasks, repeats, time limit.
- **Harnesses** with the versions `pin` recorded, and anything set away from their defaults.
- **Models** with the exact names passed to each harness, reasoning effort, and how each was paid for.
- **Sandbox**: image tag, CPUs and memory.

## Results

1. **Overall test first.** For each model and mode: number of harnesses, best-minus-worst pass rate, p-value. If it finds nothing, say that plainly and stop interpreting pairs.
2. **Pass rate with intervals**, per harness and model. Paste the table; do not round the intervals away.
3. **Head-to-head verdicts** that are "clear", with their plausible ranges. Mention how many pairs were compared.
4. **Cost per pass**, and which basis it uses (reported, or list price). Include the runs that failed.
5. **Time and tokens**: medians. Note any harness whose usage could not be read.
6. **By task**: where the differences come from. One task driving everything is a different finding from a broad gap.
7. **What tripped them up**: the hidden checks failed most often, and whether one harness fails a check the others pass.
8. **Blocked and ungraded runs**: how many, and why. A harness that could not log in has not been measured.
9. **Visual tasks**: who judged, how many pairs, the ranking with intervals, and agreement between judges. State whether a person judged at all.
10. **Subagent mode**, if run: how many runs really started subagents, then the difference in pass rate and in cost.

## What this does not show

Copy the relevant lines from [methodology.md](methodology.md#threats-to-validity) and add what was specific to your run: tasks left out, a harness that kept timing out, a provider outage half-way through.

## One-paragraph summary

Write it last. A good one names the conditions ("with model X on these ten tasks, five repeats"), gives the one or two differences that were clear, gives the cost per pass, and says what stayed within noise. Avoid "A is better than B" without the conditions attached.
