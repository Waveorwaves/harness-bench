# Adding a harness

A harness needs one adapter in `harness_bench/adapters.py` and an install step in `docker/Dockerfile`.

## The adapter

```python
Adapter("name", ("name", "--version"), name_command, name_parse, env={})
```

- **`name_command(run)`** returns the argument list that runs the harness once, unattended, in the current directory. `run` carries the prompt, model name, reasoning effort, mode, extra arguments from the suite, and sandbox paths. It must: skip every approval prompt (the container is the sandbox), not resume or save sessions, and print machine-readable output if the harness has it.
- **`name_parse(stdout, telemetry_dir)`** returns the usage fields in `USAGE_FIELDS`. Start from `empty()` and fill in only what you find. Never estimate: a field you cannot read stays `None`.
- Keep input tokens **uncached**. If the harness reports input including cached tokens, subtract them (see `codex_parse`).

## Checklist before trusting it

1. `python3 -m harness_bench adapters` prints the command; compare it with the harness's `--help`.
2. Add the harness to a suite and run `check`: it must be found in the image and report a version.
3. Run one real task: `run --limit 1 --harness name`. Then read `runs/<plan>/<run>/agent.stdout`.
4. Compare the parsed tokens and cost in `results.jsonl` with what the harness or the provider's dashboard shows for that run.
5. Add a parser test in `tests/test_runner.py` using a trimmed copy of that real output.

## State of the built-in adapters

| Harness | Command checked against `--help` | Usage parser |
|---|---|---|
| Claude Code | yes | checked against the real output of one trivial call (2.1.289, 2026-10-05), including the subagent count; not yet checked on a full task run |
| Codex | yes | checked against a real run in Docker (codex-cli 0.160.1, 2026-10-06): tokens, cached tokens and tool calls match the raw output; a subscription reports no cost |
| Pi | yes | checked against a real run in Docker (Pi 1.0.4, 2026-10-06): tokens, reported cost, model calls and tool calls match the raw output; a login failure it exits cleanly from is detected |
| oh-my-pi | yes | shares Pi's parser; checked against real runs in Docker on both models (omp 18.6.1, 2026-10-06) |
| OpenCode | yes | checked against real runs in Docker on both models (1.18.34, 2026-10-06): tokens, cost, steps and tool calls match the raw output. Its own cost uses its own price list, which differs from Pi's |
| Hermes | yes | checked against real runs in Docker on both models (0.21.5, 2026-10-06): tokens and model calls match its usage report. It reports no tool-call count, and its cost is an estimate, which is not recorded |
| Droid | yes | checked against a real run in Docker (droid 0.235.0, 2026-10-08): tokens and turns from its result object; no tool-call count. Its help text lists models incompletely: ask for a model by id to see whether it is offered |
| Devin | yes | reads the session it exports; checked against a real run in Docker (devin 3000.11.3, 2026-10-07): tokens, model calls and tool calls |

Installed in the image: Codex, Pi, oh-my-pi (which needs Bun), OpenCode, Claude Code, and, through their vendors' own installers, Droid and Hermes. Hermes keeps its login in its own folder rather than the home folder, so the image wraps it in a small launcher (`docker/hermes-launcher`) that moves a copied login into place.

Hosted agents with no local command line (Devin, Capy) do not fit this adapter shape. They need an adapter that submits the task through their API and downloads the resulting workspace, and they cannot be given a model of your choice, so they belong in a separate "as sold" comparison.
