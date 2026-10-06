"""Hidden acceptance checks. Inputs are unseen; the behaviour is all stated in the prompt."""

import json
import os
from pathlib import Path
import sys

CASES = [
    ("plain words", "Hello World", "hello-world"),
    ("punctuation and extra spaces", "  Hello,   World!  ", "hello-world"),
    ("underscores and hyphens", "snake_case and-kebab", "snake-case-and-kebab"),
    ("accented letters", "Crème Brûlée", "creme-brulee"),
    ("edge hyphens", "--Already--Slugged--", "already-slugged"),
    ("digits and dots", "Version 2.0 Released", "version-20-released"),
    ("nothing left", "!!!", "untitled"),
]

sys.path.insert(0, os.getcwd())
checks = []
try:
    from slugify import slugify
except Exception as error:  # the candidate may have broken the module entirely
    checks = [{"name": name, "passed": False, "detail": f"import failed: {error}"} for name, _, _ in CASES]
else:
    for name, text, expected in CASES:
        try:
            actual = slugify(text)
        except Exception as error:
            actual = f"raised {type(error).__name__}"
        checks.append({"name": name, "passed": actual == expected, "detail": f"{text!r} -> {actual!r}"})

Path(os.environ["HB_OUT"], "result.json").write_text(json.dumps({"checks": checks}, indent=2))
