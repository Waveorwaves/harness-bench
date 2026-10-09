"""Make benchmark-only copies of harness sign-ins that hold just the ChatGPT/Codex login.

A run copies a harness's login file into a container, where the agent can read it. The files the
harnesses keep usually hold more than that one sign-in (other providers, API keys), and one harness
keeps its sign-ins in a database that cannot be copied safely while half-written. This writes
trimmed, single-file copies to ~/.harness-bench/logins/ for a suite's `credentials` to point at.

    python3 scripts/snapshot_logins.py              # every harness
    python3 scripts/snapshot_logins.py dsh hermes   # only these

Rerun it after signing in again. Name the harness when only one changed: a copy that a run renews in place
(Pi's) is newer than the original, and copying over it again would put the older sign-in back. Nothing secret
is printed.
"""

import json
import os
from pathlib import Path
import sqlite3
import sys
import time

HOME = Path.home()
TARGET = HOME / ".harness-bench" / "logins"


def write_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def expiry(entry):
    """When the sign-in's current token runs out, if the harness records it."""
    try:
        seconds = float(entry["expires"])
    except (KeyError, TypeError, ValueError):
        return None
    return seconds / 1000 if seconds > 1e11 else seconds


def json_login(source, providers, target):
    """Keep one sign-in from a harness's JSON login file: the first of `providers` that is a sign-in, not an API key."""
    data = json.loads(source.read_text(encoding="utf-8"))
    for provider in providers:
        entry = data.get(provider)
        if isinstance(entry, dict) and entry.get("type") == "oauth":
            write_private(target, json.dumps({provider: entry}).encode())
            return expiry(entry), None
    return None, f"not signed in to {' or '.join(providers)}"


def hermes_login(source, target):
    data = json.loads(source.read_text(encoding="utf-8"))
    provider = "openai-codex"
    if provider not in data.get("providers", {}) and provider not in data.get("credential_pool", {}):
        return None, f"not signed in to {provider}"
    for section in ("providers", "credential_pool"):
        data[section] = {name: value for name, value in data.get(section, {}).items() if name == provider}
    write_private(target, json.dumps(data).encode())
    return None, None


def omp_login(source, target):
    """Copy the database through SQLite (so pending writes are included), then drop every other sign-in."""
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.unlink(missing_ok=True)
    write_private(target, b"")
    original = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        original.backup(copy)
        copy.execute("delete from auth_credentials where provider != 'openai-codex' or disabled_cause is not null")
        copy.commit()
        rows = copy.execute("select data from auth_credentials").fetchall()
        copy.execute("pragma journal_mode = delete")
        copy.execute("vacuum")  # so the removed sign-ins are not left recoverable in the file
    finally:
        copy.close()
        original.close()
    if not rows:
        target.unlink()
        return None, "not signed in to openai-codex (or that sign-in is marked as ended)"
    return expiry(json.loads(rows[0][0])), None


def dsh_login(source, target):
    """DeepSeek Harness keeps every grant in one YAML file, two spaces per level. Keep the Codex sign-in only:
    not its DeepSeek account token, nor the secret its own browser window uses."""
    wanted, kept, inside = "  llm-pi-ai/openai-codex:", [], False
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("  ") and not line.startswith("   "):
            inside = line.rstrip() == wanted
        elif not line.startswith(" "):
            inside = False
        if inside:
            kept.append(line)
    if not any("type:" in line and "oauth" in line for line in kept):
        return None, "not signed in to openai-codex"
    write_private(target, ("version: 1\nrecords:\n" + "\n".join(kept) + "\n").encode())
    expires = next((line.split(":", 1)[1].strip().strip('"') for line in kept if line.strip().startswith("expires:")), None)
    return expiry({"expires": expires}), None


LOGINS = {
    # Pi has two ChatGPT sign-ins: "openai" (Sign in with ChatGPT; one-hour tokens) and the older "openai-codex".
    "pi": lambda: json_login(HOME / ".pi/agent/auth.json", ("openai", "openai-codex"), TARGET / "pi/auth.json"),
    "opencode": lambda: json_login(HOME / ".local/share/opencode/auth.json", ("openai",), TARGET / "opencode/auth.json"),
    "omp": lambda: omp_login(HOME / ".omp/agent/agent.db", TARGET / "omp/agent.db"),
    "hermes": lambda: hermes_login(HOME / ".hermes/auth.json", TARGET / "hermes/auth.json"),
    "dsh": lambda: dsh_login(HOME / ".dsh/.credentials.yaml", TARGET / "dsh/credentials.yaml"),
}


def main():
    TARGET.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(TARGET, 0o700)
    names = sys.argv[1:] or list(LOGINS)
    unknown = [name for name in names if name not in LOGINS]
    if unknown:
        print(f"unknown harness: {', '.join(unknown)} (known: {', '.join(LOGINS)})", file=sys.stderr)
        return 2
    for name in names:
        snapshot = LOGINS[name]
        try:
            expires, problem = snapshot()
        except (OSError, ValueError, sqlite3.Error) as error:
            expires, problem = None, f"could not be read ({type(error).__name__})"
        if problem:
            print(f"{name}: skipped, {problem}")
        elif expires is None:
            print(f"{name}: written")
        elif expires < time.time():
            print(f"{name}: written; its token ran out on {time.strftime('%Y-%m-%d %H:%M', time.localtime(expires))} and must be "
                  "renewed on first use, which only works if the sign-in itself is still valid")
        else:
            print(f"{name}: written; token good until {time.strftime('%Y-%m-%d %H:%M', time.localtime(expires))}")
    print(f"Copies are in {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
