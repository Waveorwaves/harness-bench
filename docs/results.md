# Result Records

Results are one JSON object per line. Every record must reference a planned run_id and a pinned, ready plan. The CLI accepts partial result files and explicitly reports missing runs. No field represents an inferred measurement.

Required fields:
- run_id: identifier from the plan.
- status: passed, failed, timed_out, or blocked.
- elapsed_seconds: nonnegative number; null only for blocked runs.
- human_interventions: nonnegative integer.
- human_minutes: nonnegative number.
- attempts: nonnegative integer, bounded by the planned retry budget; zero only for blocked runs.
- checks_passed, checks_total: nonnegative integers; passed requires all checks passed and total > 0.
- evidence_ref: nonempty reference to saved evaluator output/transcript. This planner validates the record structure, not the artifact contents.
- input_tokens, output_tokens, cost_usd: optional nonnegative measurements or null. Unknown costs remain null, including subscription costs.
- cached_input_tokens, cache_write_tokens, turns, tool_calls, files_changed, lines_added, lines_removed: optional nonnegative integers or null. input_tokens excludes cached input.
- list_price_usd: optional estimate from tokens and the suite's price table; null unless every needed price is present.

The runner also writes mock, sandbox, harness_version, started_at, exit_code, blocked_reason, evaluator_error, logins_changed_in_run, credentials_refreshed, credentials_refused, not_archived and usage_error for diagnosis. 

## What a run leaves behind

`runs/<plan id>/<task>.<harness>.<model>.<mode>.<repeat>/` holds:

- `workspace.tar.gz`: the files as the agent left them, packed. A folder an agent wrote can act on whoever opens it (git settings, editor tasks, shell hooks); an archive cannot. Unpack it somewhere deliberate to look inside. Every `.git` in it has been renamed `.git-as-left-by-agent`, and files over 50 MB are left out.
- `changes.patch`: the difference from the seed, computed by comparing files directly.
- `agent.stdout`, `agent.stderr`: the harness's raw output, kept so usage can be re-parsed later.
- `telemetry/`: usage files a harness writes for itself.
- `evaluation/result.json`: every hidden check with its verdict and detail.
- `capture/` (visual tasks): stills, clip frames and `capture.json`.

`runs/<plan id>/plan.json` is the archived plan and `results.jsonl` the records. `runs/` is not committed: it can contain private prompts and provider output.

Harness/model/task/evaluator identity and budgets come from the immutable plan. Before running, archive plan and configuration; changing either starts a new experiment. Do not publish raw transcripts containing secrets or private documents.

