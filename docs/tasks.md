# Tasks

Nine tasks in two tracks are in the pilot suite. Two more are kept in the repository only as fixtures: a smoke task for testing the pipeline, and `sunset-sail`, a 2D visual task that was dropped from the suite and still serves the tests and the demo pages. All are small enough for a cheap model to attempt in a few minutes and need no dependencies.

## Core track: graded by hidden checks

| Task | Kind | What the agent must do | Checks | What it is designed to catch |
|---|---|---|---:|---|
| `md-preview` | build from a spec | Write a Markdown-subset renderer and a preview page to an exact specification | 18 | skipping details of a written spec: escaping, unsafe links, blank lines inside code blocks, unmatched markers |
| `kanban-undo` | bug fix | Fix two reported undo/redo faults in a small kanban board | 14 | fixing the symptom instead of the cause, and breaking working behaviour while fixing |
| `expenses-csv` | feature | Add CSV export and import to an expense tracker | 17 | careless money arithmetic (`19.99` must be 1999 cents), quoting rules, error line numbers, a true round trip |
| `checkout-refactor` | refactor | Split one long pricing function into four modules without changing any result | 12 | behaviour drift during a refactor: 163 frozen orders must price identically |
| `bookmarks-tags` | feature across modules | Add tags through validation, storage (with a migration), store, search, import/export and view | 20 | forgetting a layer, most often the migration of old saved data |
| `todo-app` | interactive page, built from a spec | Build a to-do list page: add, complete, edit, delete, filter, clear, persist | 22 | behaviour that only shows when the page is used: Escape cancelling an edit, focus, state after a reload |
| `tabs-keyboard` | accessibility fix | Make an existing tabs widget work with the keyboard and screen readers, including a widget nested in another | 19 | partial keyboard support, and code that reaches into a nested widget |
| `log-report` | feature in a Python command-line tool | Add bad-line handling, a time window, percentiles and JSON output to a log summariser | 16 | time zones compared as text instead of instants, floating-point rank errors, exit codes |

The five JavaScript logic tasks and the Python task are graded by calling their code on inputs the agent never sees. `todo-app` and `tabs-keyboard` are graded by using the page in a headless browser: a hidden script types, clicks, double-clicks, presses keys and reloads with real input events, and the checks read what the page showed after each step.

Every hidden check tests behaviour stated in the prompt or the seed's README.

## Visual track: automatic checks, then people

| Task | What the agent must build | Automatic checks | Then judged on |
|---|---|---:|---|
| `pirate-ship-3d` | One `index.html`: a real-time WebGL scene of a detailed pirate ship on a moving ocean at sunset, any library inlined | 10 | detail of the ship, water and wake, lighting, motion, polish |

The automatic checks cover what a machine can decide: a single file, no requests to anything else, no console errors, a canvas filling the window, a picture that is not blank and that changes between frames (and, for the 3D task, WebGL and no text on the page). Looks are decided by blind side-by-side picks; see [visual-track.md](visual-track.md).

`pirate-ship-3d` follows the brief of a widely shared one-prompt demo (a cinematic pirate ship at sunset), rewritten for this benchmark so that it can be captured offline and checked automatically.

## Calibration

Before any harness was measured, each task was attempted blind: a fresh Claude subagent was given only the prompt and the seed, with no access to the checks or the reference, and its result was graded by the hidden checks. One attempt per cell, run in this project's development session on 2026-10-05.

**These are not benchmark results.** They were not run through the sandbox or a harness under test, and one attempt says little about a model. They answer two questions about the tasks: can they be solved from the prompt alone, and are they hard enough to tell attempts apart?

| Task | Smaller model (Claude Haiku) | Larger model (Claude Sonnet) | What the failures were |
|---|---|---|---|
| `md-preview` | 15/18, fail | 18/18, pass | split a fenced code block at its blank line; turned an unmatched `**` into empty emphasis; left a trailing space with Windows line endings |
| `kanban-undo` | 12/14, fail | 14/14, pass | fixed both reported bugs, but its rewrite lost cards moved within one column |
| `expenses-csv` | 16/17, fail | 17/17, pass | normalised line endings before parsing, which changed a note containing `\r\n` and broke the round trip |
| `checkout-refactor` | 12/12, pass | not attempted | none |
| `bookmarks-tags` | 20/20, pass | not attempted | none |
| `todo-app` | 21/22, fail | 22/22, pass | pressing Escape saved the edit instead of cancelling it |
| `tabs-keyboard` | 9/19, fail | 19/19, pass | the outer widget took over the tabs of the widget nested inside it, so neither worked properly |
| `log-report` | 13/16, fail | 16/16, pass | a floating-point rank error in the percentile; an empty time accepted; `since` not converted to UTC in the JSON |

One prompt was tightened afterwards. A review judged that `log-report` asked for an exact percentile rank without saying that floating point gets it wrong, so the prompt now says so; the smaller model's other two failures on that task do not depend on it. The same review led to one unstated expectation (the order of keys in the JSON output) being dropped.

Visual tasks, automatic checks only (looks are judged separately):

| Task | Claude Haiku | Claude Sonnet | Claude Opus |
|---|---|---|---|
| `sunset-sail` | 10/10, pass | 10/10, pass | not attempted |
| `pirate-ship-3d` | 10/10, pass, although no ship is visible | 10/10, pass | 10/10, pass |

The visual attempts were made under a handicap the real task does not have: the solvers could not open a browser or download a library, so each wrote its own rendering code and never saw the result.

What this shows:

- **Every core task is solvable from its prompt.** Each was passed by a solver that never saw the checks. The solvers were also asked what they found ambiguous; nothing they listed is tested. With the one exception noted above, no failure traced back to something the prompt did not state.
- **Calibration also found a fault in a reference solution.** A blind solver pointed out that `ceil(p / 100 * n)` computed in floating point gives the wrong rank for some whole-number cases. The `log-report` reference had that bug; it was fixed and a check added. This is what the blind attempts are for.
- **Six of eight core tasks separate a smaller model from a larger one**, each on a real defect rather than a formatting quibble. `checkout-refactor` and `bookmarks-tags` were passed by the smaller model and may sit near the ceiling; they stay in as checks on carefulness, and their per-check counts still give partial credit.
- **The visual tasks cannot be separated by their automatic checks, and are not meant to be.** Every attempt passed them, including a 3D attempt whose camera sits inside the geometry so that no ship can be seen. Side by side the attempts differ enormously: see the stored samples in each task's `variants/` folder and the worked ranking in [demo/ranking.md](demo/ranking.md). On a visual task the automatic checks are a floor, not a score.

## Adding a task

1. Create `tasks/<id>/` with `task.json`, `prompt.md`, `seed/`, `evaluator/` and `reference/` (see the README for the layout, and `tasks/kanban-undo` for a complete example).
2. Write the prompt first, then the checks, and make every check traceable to a sentence in the prompt or the seed's README.
3. `python3 -m harness_bench validate-tasks --suite <a suite listing it> --sandbox local` must report the seed failing and the reference passing.
4. Have someone (or a model) who has not seen the checks attempt it from the prompt. If they fail on something the prompt does not say, fix the prompt or drop the check.
5. Prefer several checks that each test one stated behaviour over one large check, so a failure says what went wrong.
6. If a blind attempt fails for a good reason, keep it: store the files that differ from the seed in `variants/known-defect/` with an `expected.json` naming the checks it must fail. The test suite then guards those checks.

For a task whose result is a page, add `capture` settings to `task.json` and read `$HB_CAPTURE/capture.json` in the evaluator. To grade behaviour, name a `script` of interaction steps kept in `evaluator/` (see `tasks/todo-app/evaluator/steps.json`): each `eval` step's value is recorded, a step that cannot be carried out is listed in `interaction_problems`, and the rest still run. Optional `variants/` hold deliberately weaker solutions: they let the fake agent produce different-looking entries for testing the judging flow, and they double as negative controls for the checks.
