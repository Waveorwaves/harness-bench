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
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable

USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens",
                "reported_cost_usd", "turns", "tool_calls", "subagents")


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
    usage = empty()
    turns = [e.get("usage") or {} for e in events(stdout) if e.get("type") == "turn.completed"]
    if not turns:
        return usage
    cached = total(count(t.get("cached_input_tokens")) for t in turns)
    with_cache = total(count(t.get("input_tokens")) for t in turns)
    # Codex reports input including the cached part; separate them.
    usage.update(input_tokens=None if with_cache is None else with_cache - (cached or 0),
                 cached_input_tokens=cached,
                 output_tokens=total(count(t.get("output_tokens")) for t in turns),
                 turns=len(turns),
                 tool_calls=sum(1 for e in events(stdout) if e.get("type") == "item.completed"
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
    usage = empty()
    messages = [e["message"] for e in events(stdout) if e.get("type") == "message_end"
                and isinstance(e.get("message"), dict) and e["message"].get("role") == "assistant"]
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
    usage = empty()
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
    return ["droid", "exec", "-o", "json", "--skip-permissions-unsafe", *mission,
            *optional("-m", run.model), *optional("-r", run.effort), *run.args, run.prompt]


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
    usage.update(input_tokens=count(report.get("input_tokens")),
                 cached_input_tokens=count(report.get("cache_read_tokens")),
                 cache_write_tokens=count(report.get("cache_write_tokens")),
                 output_tokens=count(report.get("output_tokens")),
                 turns=count(report.get("api_calls")))
    # Hermes labels this an estimate; keep it only when it says the figure is known.
    if report.get("cost_status") in ("actual", "known", "exact"):
        usage["reported_cost_usd"] = money(report.get("estimated_cost_usd"))
    return usage


# --- Mock (pipeline self-test; never a measurement) --------------------------------

def mock_command(run):
    return ["python3", "-B", f"{run.paths['mock']}/mock_agent.py", *run.args, f"mode={run.mode}"]


def mock_parse(stdout, telemetry):
    usage = empty()
    for event in events(stdout):
        if event.get("type") == "mock_usage":
            usage.update({key: event.get(key) for key in USAGE_FIELDS})
    return usage


SANDBOXED = {"IS_SANDBOX": "1"}

ADAPTERS = {adapter.id: adapter for adapter in (
    Adapter("mock", ("python3", "--version"), mock_command, mock_parse),
    Adapter("claude", ("claude", "--version"), claude_command, claude_parse, SANDBOXED),
    Adapter("codex", ("codex", "--version"), codex_command, codex_parse),
    Adapter("pi", ("pi", "--version"), pi_command, pi_parse),
    Adapter("omp", ("omp", "--version"), omp_command, pi_parse),
    Adapter("opencode", ("opencode", "--version"), opencode_command, opencode_parse),
    Adapter("droid", ("droid", "--version"), droid_command, unparsed),
    Adapter("hermes", ("hermes", "--version"), hermes_command, hermes_parse),
)}


def get(adapter_id):
    if adapter_id not in ADAPTERS:
        raise ValueError(f"unknown adapter: {adapter_id} (known: {', '.join(ADAPTERS)})")
    return ADAPTERS[adapter_id]
