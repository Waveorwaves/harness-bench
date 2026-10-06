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
| Codex | yes | written from the JSON event format; not yet checked on a live run |
| Pi | yes | written from Pi's bundled JSON-mode docs; not yet checked on a live run |
| oh-my-pi | yes | shares Pi's parser; not yet checked on a live run |
| OpenCode | yes | written from memory of the event format; the least certain |
| Hermes | yes | reads its `--usage-file` report, field names taken from its source |
| Droid | yes | none yet: runs record time and checks but no tokens |

Hosted agents with no local command line (Devin, Capy) do not fit this adapter shape. They need an adapter that submits the task through their API and downloads the resulting workspace, and they cannot be given a model of your choice, so they belong in a separate "as sold" comparison.
