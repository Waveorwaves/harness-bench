"""One adapter per harness: how to launch it headless and how to read its usage output.

Parsers return None for anything they cannot find. They never guess: a missing number
stays missing. Raw output is always kept beside the run so it can be re-parsed later.

Token fields are normalised so they do not overlap:
  input_tokens         uncached input
  cached_input_tokens  input read from the provider's cache
  cache_write_tokens   input written to the cache (None where the provider does not report it)
  output_tokens        output, including reasoning where the harness folds it in

`subagents` is how many subagents the run started, where the harness says. It shows whether
a run in a "use subagents" mode really did.

`turns` is the number of model calls, where the harness reports them one by one.

`error` is the harness's own account of a failure to reach the model (an expired login, a
refused request), taken from its output. A harness can exit cleanly after such a failure,
and without this a run that never started would be scored as a failed attempt.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable

USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens",
                "reported_cost_usd", "turns", "tool_calls", "subagents", "error")


@dataclass(frozen=True)
class Launch:
    """Everything an adapter needs to build its command line."""
    prompt: str
    model: str | None
    effort: str | None
    mode: str
    args: tuple  # extra arguments from the suite's harness entry
    paths: dict  # sandbox paths by mount name; "telemetry" is writable and outside the workspace


@dataclass(frozen=True)
class Adapter:
    id: str
    version: tuple
    command: Callable[[Launch], list]
    parse: Callable[[str, Path], dict]
    # Environment the harness needs to run unattended inside a container.
    env: dict = field(default_factory=dict)


def empty():
    return dict.fromkeys(USAGE_FIELDS)


def events(text):
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                yield value


def count(value):
    return value if type(value) is int and value >= 0 else None


def money(value):
    return value if type(value) in (int, float) and value >= 0 else None


def total(values):
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def optional(flag, value):
    return [flag, value] if value else []


# --- Claude Code -----------------------------------------------------------------

def claude_command(run):
    return ["claude", "-p", run.prompt, "--output-format", "json", "--dangerously-skip-permissions",
            *optional("--model", run.model), *optional("--effort", run.effort), *run.args]


def claude_parse(stdout, telemetry):
    """Reads the final `result` object. Its shape was checked against Claude Code 2.1.289 on 2026-10-05."""
    usage = empty()
    try:
        document = json.loads(stdout)
    except ValueError:
        document = None
    candidates = document if isinstance(document, list) else [document] if document else list(events(stdout))
    results = [e for e in candidates if isinstance(e, dict) and e.get("type") == "result"]
    if not results:
        return usage
    result = results[-1]
    models = [m for m in (result.get("modelUsage") or {}).values() if isinstance(m, dict)]
    if models:
        # Per-model totals cover everything the run spent, including models used by subagents.
        usage.update(input_tokens=total(count(m.get("inputTokens")) for m in models),
                     cached_input_tokens=total(count(m.get("cacheReadInputTokens")) for m in models),
                     cache_write_tokens=total(count(m.get("cacheCreationInputTokens")) for m in models),
                     output_tokens=total(count(m.get("outputTokens")) for m in models))
    else:
        tokens = result.get("usage") or {}
        usage.update(input_tokens=count(tokens.get("input_tokens")),
                     cached_input_tokens=count(tokens.get("cache_read_input_tokens")),
                     cache_write_tokens=count(tokens.get("cache_creation_input_tokens")),
                     output_tokens=count(tokens.get("output_tokens")))
    usage.update(reported_cost_usd=money(result.get("total_cost_usd")), turns=count(result.get("num_turns")),
                 subagents=count((result.get("subagent_stats") or {}).get("spawned")))
    return usage


# --- Codex -----------------------------------------------------------------------

def codex_command(run):
    effort = ["-c", f'model_reasoning_effort="{run.effort}"'] if run.effort else []
    return ["codex", "exec", "--json", "--skip-git-repo-check", "--ephemeral",
            "--dangerously-bypass-approvals-and-sandbox", *optional("-m", run.model), *effort, *run.args, run.prompt]


def codex_parse(stdout, telemetry):
    """Reads `turn.completed` usage. Checked against the output of a real run (codex-cli 0.160.1, 2026-10-06)."""
    usage = empty()
    seen = list(events(stdout))
    problems = [(e.get("error") or {}).get("message") or e.get("message") for e in seen
                if e.get("type") in ("error", "turn.failed")]
    usage["error"] = next((str(p).splitlines()[0][:300] for p in problems if p), None)
    turns = [e.get("usage") or {} for e in seen if e.get("type") == "turn.completed"]
    if not turns:
        return usage
    cached = total(count(t.get("cached_input_tokens")) for t in turns)
    with_cache = total(count(t.get("input_tokens")) for t in turns)
    # Codex reports input including the cached part; separate them. A Codex "turn" is the whole
    # job, not one model call, so it is not reported as turns.
    usage.update(input_tokens=None if with_cache is None else with_cache - (cached or 0),
                 cached_input_tokens=cached,
                 cache_write_tokens=total(count(t.get("cache_write_input_tokens")) for t in turns),
                 output_tokens=total(count(t.get("output_tokens")) for t in turns),
                 tool_calls=sum(1 for e in seen if e.get("type") == "item.completed"
                                and (e.get("item") or {}).get("type") not in
                                (None, "agent_message", "reasoning", "error", "todo_list")))
    return usage


# --- Pi and oh-my-pi (same JSON event stream) --------------------------------------

def pi_command(run):
    return ["pi", "-p", "--mode", "json", "--no-session", *optional("--model", run.model),
            *optional("--thinking", run.effort), *run.args, run.prompt]


def omp_command(run):
    return ["omp", "-p", "--mode", "json", "--no-session", "--auto-approve",
            *optional("--model", run.model), *optional("--thinking", run.effort), *run.args, run.prompt]


def pi_parse(stdout, telemetry):
    """Sums the usage of every assistant message. Checked against the output of a real run (Pi 1.0.4, 2026-10-06)."""
    usage = empty()
    messages = [e["message"] for e in events(stdout) if e.get("type") == "message_end"
                and isinstance(e.get("message"), dict) and e["message"].get("role") == "assistant"]
    failures = [str(m.get("errorMessage") or "the harness reported an error") for m in messages if m.get("stopReason") == "error"]
    usage["error"] = failures[0].splitlines()[0][:300] if failures else None
    tokens = [m["usage"] for m in messages if isinstance(m.get("usage"), dict)]
    if not tokens:
        return usage
    usage.update(input_tokens=total(count(t.get("input")) for t in tokens),
                 cached_input_tokens=total(count(t.get("cacheRead")) for t in tokens),
                 cache_write_tokens=total(count(t.get("cacheWrite")) for t in tokens),
                 output_tokens=total(count(t.get("output")) for t in tokens),
                 reported_cost_usd=total(money((t.get("cost") or {}).get("total")) for t in tokens),
                 turns=len(messages),
                 tool_calls=sum(1 for m in messages for block in m.get("content") or []
                                if isinstance(block, dict) and block.get("type") == "toolCall"))
    return usage


# --- OpenCode --------------------------------------------------------------------

def opencode_command(run):
    return ["opencode", "run", "--format", "json", "--auto", *optional("-m", run.model),
            *optional("--variant", run.effort), *run.args, run.prompt]


def opencode_parse(stdout, telemetry):
    """Sums `step_finish` usage. Checked against the output of real runs (OpenCode 1.18.34, 2026-10-06)."""
    usage = empty()
    failures = [e.get("error") or {} for e in events(stdout) if e.get("type") == "error"]
    if failures:
        message = (failures[0].get("data") or {}).get("message") or "the harness reported an error"
        usage["error"] = f"{failures[0].get('name') or 'error'}: {message}".splitlines()[0][:300]
    steps = [e.get("part") or {} for e in events(stdout) if e.get("type") == "step_finish"]
    tokens = [s["tokens"] for s in steps if isinstance(s.get("tokens"), dict)]
    if not tokens:
        return usage
    usage.update(input_tokens=total(count(t.get("input")) for t in tokens),
                 cached_input_tokens=total(count((t.get("cache") or {}).get("read")) for t in tokens),
                 cache_write_tokens=total(count((t.get("cache") or {}).get("write")) for t in tokens),
                 output_tokens=total(count(t.get("output")) for t in tokens),
                 reported_cost_usd=total(money(s.get("cost")) for s in steps),
                 turns=len(steps),
                 tool_calls=sum(1 for e in events(stdout) if e.get("type") == "tool_use"))
    return usage


# --- Factory Droid ---------------------------------------------------------------

def droid_command(run):
    mission = ["--mission"] if run.mode == "subagents" else []
    # A custom model (your own key, defined in Droid's settings file) takes its effort from that file, not from -r.
    effort = [] if (run.model or "").startswith("custom:") else optional("-r", run.effort)
    return ["droid", "exec", "-o", "json", "--skip-permissions-unsafe", *mission,
            *optional("-m", run.model), *effort, *run.args, run.prompt]


def droid_parse(stdout, telemetry):
    """Reads the single result object Droid prints. Checked against the output of a real run (droid 0.235.0, 2026-10-08)."""
    usage = empty()
    result = next((event for event in events(stdout) if event.get("type") == "result"), None)
    if result is None:
        return usage
    if result.get("is_error"):
        usage["error"] = (str(result.get("result") or "").strip().splitlines() or ["the harness reported an error"])[0][:300]
    tokens = result.get("usage")
    if isinstance(tokens, dict):
        # Input here does not include what was read from or written to cache; those are counted separately.
        usage.update(input_tokens=count(tokens.get("input_tokens")),
                     cached_input_tokens=count(tokens.get("cache_read_input_tokens")),
                     cache_write_tokens=count(tokens.get("cache_creation_input_tokens")),
                     output_tokens=count(tokens.get("output_tokens")),
                     turns=count(result.get("num_turns")))
    return usage


def unparsed(stdout, telemetry):
    """Usage format not confirmed yet; report nothing rather than guess."""
    return empty()


# --- Hermes ----------------------------------------------------------------------

def hermes_command(run):
    return ["hermes", "-z", run.prompt, "--usage-file", f"{run.paths['telemetry']}/hermes-usage.json",
            *optional("-m", run.model), *optional("--reasoning", run.effort), *run.args]


def hermes_parse(stdout, telemetry):
    usage = empty()
    try:
        report = json.loads((Path(telemetry) / "hermes-usage.json").read_text())
    except (OSError, ValueError):
        return usage
    if not isinstance(report, dict):
        return usage
    if report.get("failed"):
        said = [line.strip() for line in stdout.splitlines() if line.strip()]
        usage["error"] = (said[0] if said else "the harness reported a failure")[:300]
    usage.update(input_tokens=count(report.get("input_tokens")),
                 cached_input_tokens=count(report.get("cache_read_tokens")),
                 cache_write_tokens=count(report.get("cache_write_tokens")),
                 output_tokens=count(report.get("output_tokens")),
                 turns=count(report.get("api_calls")))
    # Hermes labels this an estimate; keep it only when it says the figure is known.
    if report.get("cost_status") in ("actual", "known", "exact"):
        usage["reported_cost_usd"] = money(report.get("estimated_cost_usd"))
    return usage


# --- Devin (command line) ----------------------------------------------------------

def devin_command(run):
    # Devin's model names carry the effort (gpt-6-1-sol-medium), so there is no separate effort option.
    # The prompt goes after `--` so that nothing in it can be read as an option.
    return ["devin", "-p", *optional("--model", run.model), "--permission-mode", "dangerous",
            "--respect-workspace-trust", "false", "--export", f"{run.paths['telemetry']}/devin-export.json",
            *run.args, "--", run.prompt]


def devin_parse(stdout, telemetry):
    """Reads the session Devin exports. Checked against the export of a real run (devin 3000.11.3, 2026-10-07)."""
    usage = empty()
    try:
        report = json.loads((Path(telemetry) / "devin-export.json").read_text())
    except (OSError, ValueError):
        return usage
    steps = [step for step in report.get("steps") or [] if isinstance(step, dict)] if isinstance(report, dict) else []
    calls = [step["metrics"] for step in steps if isinstance(step.get("metrics"), dict)]
    if not calls:
        return usage
    prompt = total(count(call.get("prompt_tokens")) for call in calls)
    cached = total(count(call.get("cached_tokens")) for call in calls)
    usage.update(
        # Devin's prompt count includes what was read from cache. What it calls cache creation is new input:
        # its price list has no separate charge for it, so it is counted under input and not as a cache write.
        input_tokens=None if prompt is None else prompt - (cached or 0),
        cached_input_tokens=cached, cache_write_tokens=0,
        output_tokens=total(count(call.get("completion_tokens")) for call in calls),
        turns=len(calls),
        tool_calls=sum(len(step.get("tool_calls") or []) for step in steps))
    return usage


# --- DeepSeek Harness --------------------------------------------------------------

def dsh_command(run):
    """One task through `dsh --profile headless`. The provider, model and effort are profile settings and not
    options, so they are written to a small patch file first (JSON, which its YAML reader accepts). The file is
    left in telemetry as a record of what was asked for. The model is named "provider/model"."""
    launch = ["dsh", "--profile", "headless"]
    script = 'exec "$@"'
    setup = []
    if run.model:
        provider, _, model = run.model.partition("/")
        selection = {"provider": provider, "model": model, **({"reasoningEffort": run.effort} if run.effort else {})}
        patch = json.dumps([{"id": "agent-default-model", "name": "@deepseek-ai/dsh-agent-default-model", "config": selection}])
        path = f"{run.paths['telemetry']}/dsh-model.yml"
        script = 'printf "%s\\n" "$1" > "$2" && shift 2 && exec "$@"'
        setup = [patch, path]
        launch += ["--patch", path]
    # The prompt goes after `--` so that nothing in it can be read as an option.
    return ["sh", "-c", script, "dsh-launch", *setup, *launch, *run.args, "--json", "--", run.prompt]


def dsh_parse(stdout, telemetry):
    """Sums the usage each step reports. Checked against the output of a real run (dsh 0.2.0-rc.2 on DeepSeek's
    API and on gpt-6.1-sol through Codex, 2026-10-08). Both gave input apart from what came from the cache; the
    Codex route left cache figures out of a step when they were zero.

    A step that was retried reports no usage, which leaves the run's total unknowable: the token fields then stay
    empty and are not given as a partial sum."""
    usage = empty()
    steps, complete, tools = [], True, 0
    for event in events(stdout):
        kind = event.get("type")
        if kind == "error" and usage["error"] is None:
            usage["error"] = (str(event.get("message") or "").strip().splitlines() or ["the harness reported an error"])[0][:300]
        elif kind == "tool_call":
            tools += 1
        elif kind == "status" and event.get("phase") == "turn_end":
            # A turn can end on a failed model call and still print a final answer; only this says so.
            reason = event.get("reason") if isinstance(event.get("reason"), dict) else {}
            if reason.get("kind") == "error" and usage["error"] is None:
                said = reason.get("error") if isinstance(reason.get("error"), dict) else {}
                usage["error"] = (str(said.get("message") or "").strip().splitlines() or ["the harness reported an error"])[0][:300]
        elif kind == "status" and event.get("phase") == "step_end":
            if isinstance(event.get("usage"), dict):
                steps.append(event["usage"])
            else:
                complete = False
    if not steps:
        return usage
    usage.update(turns=len(steps) + (0 if complete else 1), tool_calls=tools)
    if not complete:
        return usage
    uncached, cached, written, output = [], [], [], []
    for step in steps:
        given, out = count(step.get("inputTokens")), count(step.get("outputTokens"))
        read, write = count(step.get("cacheReadTokens")), count(step.get("cacheWriteTokens"))
        whole = count(step.get("totalTokens"))
        if given is None or out is None:
            return usage
        if whole is not None:
            # Some routes leave a cache figure out when it is zero, but every step gives a total, and the total
            # settles what is missing. Where it counts the cache apart from input, whatever it holds beyond input,
            # output and cache reads is what was written to the cache. Where input plus output alone reach it,
            # the cached part is inside input and is taken out.
            read = read or 0
            rest = whole - given - out - read
            if write is None and rest >= 0:
                write = rest
            if whole == given + out:
                given = max(given - read - (write or 0), 0)
        uncached.append(given); cached.append(read); written.append(write); output.append(out)
    usage.update(input_tokens=sum(uncached), output_tokens=sum(output),
                 cached_input_tokens=None if None in cached else sum(cached),
                 cache_write_tokens=None if None in written else sum(written))
    return usage


# --- Mock (pipeline test) -----------------------------------------------------------

def mock_command(run):
    return ["python3", "-B", f"{run.paths['mock']}/mock_agent.py", *run.args, f"mode={run.mode}"]


def mock_parse(stdout, telemetry):
    usage = empty()
    for event in events(stdout):
        if event.get("type") == "mock_usage":
            usage.update({key: event.get(key) for key in USAGE_FIELDS})
    return usage


def manual_command(run):
    raise RuntimeError("a manual harness is run by hand: use manual-start and manual-finish")


SANDBOXED = {"IS_SANDBOX": "1"}

ADAPTERS = {adapter.id: adapter for adapter in (
    Adapter("mock", ("python3", "--version"), mock_command, mock_parse),
    # A desktop app with no command line. Its runs are recorded with manual-start and manual-finish.
    Adapter("manual", ("true",), manual_command, unparsed),
    Adapter("claude", ("claude", "--version"), claude_command, claude_parse, SANDBOXED),
    Adapter("codex", ("codex", "--version"), codex_command, codex_parse),
    Adapter("pi", ("pi", "--version"), pi_command, pi_parse),
    Adapter("omp", ("omp", "--version"), omp_command, pi_parse),
    Adapter("opencode", ("opencode", "--version"), opencode_command, opencode_parse),
    Adapter("droid", ("droid", "--version"), droid_command, droid_parse),
    Adapter("hermes", ("hermes", "--version"), hermes_command, hermes_parse),
    Adapter("devin", ("devin", "version"), devin_command, devin_parse),
    # Inside a container the container is the sandbox, as for the others: its own would only stop to ask.
    Adapter("dsh", ("dsh", "--version"), dsh_command, dsh_parse, {"DSH_PERMISSION_MODE": "danger-full-access"}),
)}


def get(adapter_id):
    if adapter_id not in ADAPTERS:
        raise ValueError(f"unknown adapter: {adapter_id} (known: {', '.join(ADAPTERS)})")
    return ADAPTERS[adapter_id]
