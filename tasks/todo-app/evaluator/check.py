"""Hidden acceptance checks. The page was used with real clicks, typing and key presses
(steps.json); this reads what was observed after each step. Every expectation is in the prompt."""

import json
import os
from pathlib import Path

checks = []
capture_file = Path(os.environ.get("HB_CAPTURE", "")) / "capture.json"
capture = json.loads(capture_file.read_text()) if capture_file.is_file() else {}
seen = capture.get("interaction") or {}
EMPTY = {"titles": None, "spans": [], "done": None, "checked": None, "labels": None, "ordered": [], "count": None,
         "pressed": None, "clearDisabled": None, "input": None, "inputFocused": None, "editing": "?", "editFocused": None,
         "markup": None}


def at(name):
    return {**EMPTY, **(seen.get(name) or {})}


def check(name, *conditions):
    """A check passes only if every (label, condition) holds; the first that does not is reported."""
    failed = next((label for label, ok in conditions if not ok), None)
    checks.append({"name": name, "passed": failed is None, "detail": failed or ""})


ALL, ACTIVE, DONE = ["true", "false", "false"], ["false", "true", "false"], ["false", "false", "true"]
start, one, three, ticked = at("start"), at("one"), at("three"), at("ticked")
three_titles = ["Buy milk", "Walk the dog", "<b>bold</b>"]

check("the page loads without asking for anything from the network",
      (capture.get("error") or "the page did not load", capture.get("ok") and capture.get("loaded")),
      (f"requested {capture.get('external_requests')}", not capture.get("external_requests")))
check("it starts empty, on the All filter, with nothing to clear",
      (f"list {start['titles']}", start["titles"] == []), (f"counter {start['count']!r}", start["count"] == "0 left"),
      (f"aria-pressed {start['pressed']}", start["pressed"] == ALL),
      ("clear-done is not disabled", start["clearDisabled"] is True))
check("Enter adds a to-do, empties the input and keeps it focused",
      (f"list {one['titles']}", one["titles"] == ["Buy milk"]), (f"counter {one['count']!r}", one["count"] == "1 left"),
      (f"input still holds {one['input']!r}", one["input"] == ""), ("the input lost focus", one["inputFocused"] is True))
check("each to-do has a checkbox, a title span and a labelled delete button, in that order",
      ("no to-do was added", bool(three["titles"])),
      ("the title is not a span.title", three["spans"] and all(three["spans"])),
      ("wrong order of parts", three["ordered"] and all(three["ordered"])),
      (f"aria-labels {three['labels']}", three["labels"] == ["Delete Buy milk", "Delete Walk the dog", "Delete <b>bold</b>"]))
check("titles are trimmed, empty ones add nothing, and new ones go to the end",
      (f"list {three['titles']}", three["titles"] == three_titles), (f"counter {three['count']!r}", three["count"] == "3 left"))
check("a title is shown as text, not as markup",
      (f"list {three['titles']}", (three["titles"] or [None])[-1] == "<b>bold</b>"),
      ("the title was turned into an element", three["markup"] == 0))
check("ticking a checkbox marks the to-do done and updates the counter",
      (f"done classes {ticked['done']}", ticked["done"] == [False, True, False]),
      (f"checkboxes {ticked['checked']}", ticked["checked"] == [False, True, False]),
      (f"counter {ticked['count']!r}", ticked["count"] == "2 left"))
check("unticking removes the done mark",
      (f"done classes {at('unticked')['done']}", at("unticked")["done"] == [False, False]),
      (f"counter {at('unticked')['count']!r}", at("unticked")["count"] == "2 left"))
check("clear-done is enabled once something is done", ("still disabled", ticked["clearDisabled"] is False))
check("the Active filter shows only to-dos that are not done",
      (f"list {at('active')['titles']}", at("active")["titles"] == ["Buy milk", "<b>bold</b>"]),
      (f"aria-pressed {at('active')['pressed']}", at("active")["pressed"] == ACTIVE))
check("the Done filter shows only done to-dos",
      (f"list {at('done')['titles']}", at("done")["titles"] == ["Walk the dog"]),
      (f"aria-pressed {at('done')['pressed']}", at("done")["pressed"] == DONE))
check("the All filter shows everything again",
      (f"list {at('all')['titles']}", at("all")["titles"] == three_titles),
      (f"aria-pressed {at('all')['pressed']}", at("all")["pressed"] == ALL))
check("double-clicking a title opens a focused edit box holding it",
      (f"edit box holds {at('editing')['editing']!r}", at("editing")["editing"] == "Buy milk"),
      ("the edit box is not focused", at("editing")["editFocused"] is True))
check("Enter saves the edited title, trimmed",
      (f"list {at('edited')['titles']}", at("edited")["titles"] == ["Buy oat milk", "Walk the dog", "<b>bold</b>"]),
      ("the edit box is still open", at("edited")["editing"] is None),
      (f"aria-labels {at('edited')['labels']}", (at("edited")["labels"] or [None])[0] == "Delete Buy oat milk"))
check("Escape cancels an edit",
      (f"list {at('cancelled')['titles']}", at("cancelled")["titles"] == ["Buy oat milk", "Walk the dog", "<b>bold</b>"]),
      ("the edit box is still open", at("cancelled")["editing"] is None))
check("saving an empty title deletes the to-do",
      (f"list {at('emptied')['titles']}", at("emptied")["titles"] == ["Buy oat milk", "Walk the dog"]),
      (f"counter {at('emptied')['count']!r}", at("emptied")["count"] == "1 left"))
reloaded = at("reloaded")
check("to-dos, their done state and their order survive a reload",
      (f"list {reloaded['titles']}", reloaded["titles"] == ["Buy oat milk", "Walk the dog"]),
      (f"done classes {reloaded['done']}", reloaded["done"] == [False, True]),
      (f"checkboxes {reloaded['checked']}", reloaded["checked"] == [False, True]),
      (f"counter {reloaded['count']!r}", reloaded["count"] == "1 left"))
check("the filter goes back to All after a reload", (f"aria-pressed {reloaded['pressed']}", reloaded["pressed"] == ALL),
      (f"list {reloaded['titles']}", reloaded["titles"] is not None and len(reloaded["titles"]) == 2))
check("the delete button removes its to-do",
      (f"list {at('deleted')['titles']}", at("deleted")["titles"] == ["Walk the dog"]),
      (f"counter {at('deleted')['count']!r}", at("deleted")["count"] == "0 left"))
check("clear-done removes done to-dos and then disables itself",
      (f"list {at('cleared')['titles']}", at("cleared")["titles"] == []),
      ("clear-done is not disabled", at("cleared")["clearDisabled"] is True))
check("removed to-dos stay removed after a reload",
      (f"list {at('reloaded_empty')['titles']}", at("reloaded_empty")["titles"] == []),
      (f"counter {at('reloaded_empty')['count']!r}", at("reloaded_empty")["count"] == "0 left"))
errors = (capture.get("console_errors") or []) + (capture.get("console_errors_after_use") or [])
check("the console shows no errors, before or during use",
      ("the page was never used", "interaction" in capture), ("; ".join(dict.fromkeys(errors)), not errors))

Path(os.environ["HB_OUT"], "result.json").write_text(json.dumps({"checks": checks}, indent=2))
