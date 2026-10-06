"""Hidden acceptance checks for the automatic part of the task. Looks are judged separately.

Reads index.html from the workspace copy and capture.json from $HB_CAPTURE.
"""

import json
import os
from pathlib import Path

checks = []


def check(name, passed, detail=""):
    checks.append({"name": name, "passed": bool(passed), "detail": str(detail)[:300]})


page = Path("index.html")
source = page.read_text(encoding="utf-8", errors="replace") if page.is_file() else ""
capture_file = Path(os.environ.get("HB_CAPTURE", "")) / "capture.json"
capture = json.loads(capture_file.read_text()) if capture_file.is_file() else {}
frames = capture.get("frames") or []
probe = capture.get("probe") or {}

check("index.html exists", bool(source))

# Judged by what the page actually requested while it ran, not by what its source mentions.
outside = capture.get("external_requests") or []
others = capture.get("local_requests") or []
check("everything is inside index.html", capture.get("ok") and not outside and not others,
      f"external={outside[:3]} other files={others[:3]}")

check("the page loads and can be screenshotted", capture.get("ok") and capture.get("loaded") and len(frames) >= 2,
      capture.get("error") or "")

check("the console shows no errors", capture.get("ok") and not capture.get("console_errors"),
      "; ".join(capture.get("console_errors") or []))

check("the scene is drawn on one canvas", probe.get("canvases") == 1, f"canvases={probe.get('canvases')}")

fills = (probe.get("widest", 0) >= 0.98 * probe.get("innerWidth", 1e9)
         and probe.get("tallest", 0) >= 0.98 * probe.get("innerHeight", 1e9))
check("the canvas fills the window", fills, json.dumps(probe))

no_scroll = (probe.get("scrollWidth", 1e9) <= probe.get("innerWidth", 0) + 1
             and probe.get("scrollHeight", 1e9) <= probe.get("innerHeight", 0) + 1)
check("there are no scrollbars", bool(probe) and no_scroll, json.dumps(probe))

# Blank means almost one flat colour. Flat-shaded art is fine; how good it looks is for the judges.
first = frames[0] if frames else {}
check("the first frame is not blank", first.get("distinct_colors", 0) >= 5 and first.get("dominant_share", 1) < 0.9,
      f"colours={first.get('distinct_colors')} dominant={first.get('dominant_share')}")

check("the scene moves between frames", (capture.get("changed_fraction") or 0) >= 0.01,
      f"changed={capture.get('changed_fraction')}")

check("the animation uses requestAnimationFrame", "requestAnimationFrame" in source)

Path(os.environ["HB_OUT"], "result.json").write_text(json.dumps({"checks": checks}, indent=2))
