"""Read what a Codex desktop session did in a folder, from Codex's own session logs.

    python3 scripts/codex_app_usage.py ~/hb-work/codex-app/<task folder>

Prints the model and effort it really used, how long it worked, its tokens and tool calls, and any
helper sessions the app started for it (such as its command reviewer), as JSON. Nothing is guessed:
a figure the log does not hold is null. Message contents are never printed.
"""

import glob
import json
import os
from pathlib import Path
import sys

# Chats live in sessions/ and move to archived_sessions/ when archived in the app.
STORES = [Path.home() / ".codex" / "sessions", Path.home() / ".codex" / "archived_sessions"]
TOOLS = ("function_call", "local_shell_call", "custom_tool_call", "web_search_call")


def read(path):
    session = {"file": Path(path).name, "id": None, "parent": None, "cwd": None, "helper": False, "version": None,
               "models": [], "efforts": [], "tasks": [], "user_messages": 0, "tool_calls": 0, "usage": None, "aborted": 0}
    for line in open(path, errors="replace"):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind, payload = event.get("type"), event.get("payload") or {}
        inner = payload.get("type")
        if kind == "session_meta":
            session.update(id=payload.get("id"), parent=payload.get("parent_thread_id"), cwd=payload.get("cwd"),
                           version=f"{payload.get('originator')} {payload.get('cli_version')}",
                           helper=isinstance(payload.get("source"), dict) and "subagent" in payload["source"])
        elif kind == "turn_context":
            for key, store in (("model", "models"), ("effort", "efforts")):
                if payload.get(key) and payload[key] not in session[store]:
                    session[store].append(payload[key])
        elif kind == "event_msg" and inner == "task_complete":
            session["tasks"].append(payload.get("duration_ms"))
        elif kind == "event_msg" and inner == "turn_aborted":
            session["aborted"] += 1
        elif kind == "event_msg" and inner == "user_message":
            session["user_messages"] += 1
        elif kind == "event_msg" and inner == "token_count":
            session["usage"] = (payload.get("info") or {}).get("total_token_usage") or session["usage"]
        elif kind == "response_item" and inner in TOOLS:
            session["tool_calls"] += 1
    return session


def tokens(usage):
    if not usage:
        return {"input_tokens": None, "cached_input_tokens": None, "cache_write_tokens": None, "output_tokens": None}
    cached = usage.get("cached_input_tokens") or 0
    return {"input_tokens": usage.get("input_tokens", 0) - cached, "cached_input_tokens": cached,
            "cache_write_tokens": usage.get("cache_write_input_tokens"), "output_tokens": usage.get("output_tokens")}


def main(folder):
    folder = str(Path(folder).expanduser().resolve())
    logs = [path for store in STORES for path in glob.glob(str(store / "**" / "*.jsonl"), recursive=True)]
    sessions = [read(path) for path in logs
                if os.path.getsize(path) and folder in open(path, errors="replace").readline()]
    sessions = [s for s in sessions if s["cwd"] and str(Path(s["cwd"]).resolve()) == folder]
    chats = [s for s in sessions if not s["helper"]]
    helpers = [s for s in sessions if s["helper"]]
    report = {"folder": folder, "chats_in_this_folder": len(chats), "helper_sessions": len(helpers)}
    for index, chat in enumerate(chats, 1):
        known = [ms for ms in chat["tasks"] if ms is not None]
        report[f"chat_{index}"] = {
            "app": chat["version"], "models": chat["models"], "efforts": chat["efforts"],
            "messages_you_sent": len(chat["tasks"]) + chat["aborted"], "turns_finished": len(chat["tasks"]), "turns_stopped": chat["aborted"],
            "seconds_worked": round(sum(known) / 1000, 1) if known else None,
            "tool_calls": chat["tool_calls"], **tokens(chat["usage"])}
    if helpers:
        total = {"input_tokens": 0, "cached_input_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0}
        for helper in helpers:
            for key, value in tokens(helper["usage"]).items():
                total[key] += value or 0
        report["helpers"] = {"models": sorted({m for h in helpers for m in h["models"]}), **total}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else print(__doc__) or 2)
