"""Hidden acceptance checks. The page was used with real clicks and key presses (steps.json);
this reads what was observed after each step. Every expectation is in the seed's README."""

import json
import os
from pathlib import Path

checks = []
capture_file = Path(os.environ.get("HB_CAPTURE", "")) / "capture.json"
capture = json.loads(capture_file.read_text()) if capture_file.is_file() else {}
seen = capture.get("interaction") or {}
BLANK = {key: None for key in ("listRole", "tabRoles", "selected", "tabindex", "active", "controls", "panelRoles",
                               "labelledby", "panelTabindex", "hidden", "open", "shown")}


def at(name):
    state = seen.get(name) or {}
    return {"settings": {**BLANK, **(state.get("settings") or {})}, "period": {**BLANK, **(state.get("period") or {})},
            "focus": state.get("focus")}


def check(name, *conditions):
    failed = next((label for label, ok in conditions if not ok), None)
    checks.append({"name": name, "passed": failed is None, "detail": failed or ""})


def only(index, size, yes="true", no="false"):
    return [yes if position == index else no for position in range(size)]


def chosen(widget, index, size):
    """Every sign of selection agrees that tab `index` is the selected one."""
    return [
        (f"aria-selected {widget['selected']}", widget["selected"] == only(index, size)),
        (f"tabindex {widget['tabindex']}", widget["tabindex"] == only(index, size, "0", "-1")),
        (f"active classes {widget['active']}", widget["active"] == only(index, size, True, False)),
        (f"hidden attributes {widget['hidden']}", widget["hidden"] == only(index, size, False, True)),
        (f"open classes {widget['open']}", widget["open"] == only(index, size, True, False)),
    ]


start = at("start")
main, inner = start["settings"], start["period"]
check("the page loads and its controls are found",
      (capture.get("error") or "the page did not load", capture.get("ok") and capture.get("loaded")),
      ("; ".join(capture.get("interaction_problems") or []), "interaction" in capture and not capture.get("interaction_problems")))
check("tab lists, tabs and panels have their roles",
      (f"tab list role {main['listRole']!r}, {inner['listRole']!r}", main["listRole"] == "tablist" and inner["listRole"] == "tablist"),
      (f"tab roles {main['tabRoles']}", main["tabRoles"] == ["tab"] * 4 and inner["tabRoles"] == ["tab"] * 2),
      (f"panel roles {main['panelRoles']}", main["panelRoles"] == ["tabpanel"] * 4 and inner["panelRoles"] == ["tabpanel"] * 2))
check("tabs and panels point at each other",
      (f"aria-controls correct: {main['controls']}", main["controls"] == [True] * 4 and inner["controls"] == [True] * 2),
      (f"aria-labelledby correct: {main['labelledby']}", main["labelledby"] == [True] * 4 and inner["labelledby"] == [True] * 2))
check("panels can take focus", (f"panel tabindex {main['panelTabindex']}", main["panelTabindex"] == ["0"] * 4 and inner["panelTabindex"] == ["0"] * 2))
check("on load the first tab of each widget is selected, in every respect", *chosen(main, 0, 4), *chosen(inner, 0, 2))
check("only the selected panel can be seen",
      (f"visible at start {main['shown']}", main["shown"] == [True, False, False, False]),
      (f"visible after End {at('end')['settings']['shown']}", at("end")["settings"]["shown"] == [False, False, False, True]))
check("clicking a tab selects it", *chosen(at("clicked")["settings"], 1, 4))
check("Right arrow selects and focuses the next tab", *chosen(at("right")["settings"], 2, 4),
      (f"focus is on {at('right')['focus']!r}", at("right")["focus"] == "tab-billing"))
check("Right arrow from the last tab wraps to the first", *chosen(at("right_again")["settings"], 3, 4),
      *chosen(at("wrapped")["settings"], 0, 4), (f"focus is on {at('wrapped')['focus']!r}", at("wrapped")["focus"] == "tab-profile"))
check("Left arrow from the first tab wraps to the last", *chosen(at("wrapped_back")["settings"], 3, 4),
      (f"focus is on {at('wrapped_back')['focus']!r}", at("wrapped_back")["focus"] == "tab-security"))
check("Home selects the first tab", *chosen(at("home")["settings"], 0, 4),
      (f"focus is on {at('home')['focus']!r}", at("home")["focus"] == "tab-profile"))
check("End selects the last tab", *chosen(at("end")["settings"], 3, 4),
      (f"focus is on {at('end')['focus']!r}", at("end")["focus"] == "tab-security"))
check("Left arrow selects and focuses the previous tab", *chosen(at("billing")["settings"], 2, 4),
      (f"focus is on {at('billing')['focus']!r}", at("billing")["focus"] == "tab-billing"))
check("Tab moves from the tab list to the selected panel, and Shift+Tab comes back",
      (f"after Tab, focus is on {at('into_panel')['focus']!r}", at("into_panel")["focus"] == "panel-billing"),
      (f"after Shift+Tab, focus is on {at('back_to_tab')['focus']!r}", at("back_to_tab")["focus"] == "tab-billing"))
check("the inner widget works on its own", *chosen(at("inner_clicked")["period"], 1, 2),
      *chosen(at("inner_wrapped")["period"], 0, 2), (f"focus is on {at('inner_wrapped')['focus']!r}", at("inner_wrapped")["focus"] == "tab-monthly"),
      *chosen(at("inner_end")["period"], 1, 2))
check("using the outer widget never changes the inner one",
      *[(f"inner widget changed at step '{name}': {at(name)['period']['selected']}", at(name)["period"]["selected"] == ["true", "false"])
        for name in ("clicked", "right", "wrapped", "home", "end", "billing")])
check("using the inner widget never changes the outer one",
      *[condition for name in ("inner_clicked", "inner_wrapped", "inner_end") for condition in chosen(at(name)["settings"], 2, 4)])
check("clicking still works after keyboard use", *chosen(at("mouse_again")["settings"], 0, 4))
errors = (capture.get("console_errors") or []) + (capture.get("console_errors_after_use") or [])
check("the console shows no errors, before or during use", ("; ".join(dict.fromkeys(errors)), "interaction" in capture and not errors))

Path(os.environ["HB_OUT"], "result.json").write_text(json.dumps({"checks": checks}, indent=2))
