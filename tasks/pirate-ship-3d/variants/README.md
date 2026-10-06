# Sample solutions

Alternative solutions to this task. The fake agent can replay any of them (`mock_agent.py variant <name>`), which gives the capture and judging steps real, different-looking entries to work on.

| Folder | What it is | Automatic checks |
|---|---|---|
| `small-model` | one attempt by a smaller model (Claude Haiku) from the prompt alone | 10/10, although no ship is visible: the camera ends up inside the geometry |
| `mid-model` | one attempt by a mid-sized model (Claude Sonnet) from the prompt alone | 10/10 |
| `large-model` | one attempt by a larger model (Claude Opus) from the prompt alone | 10/10 |

All were made on 2026-10-05 by subagents in this project's development session, given only `prompt.md` and the seed, told not to open a browser or download anything (so each wrote its own WebGL code and never saw its result), and are stored unmodified. One attempt each: they illustrate the range of results the task produces and say nothing reliable about the models.

`small-model` is the instructive one. It satisfies every automatic check, a page that loads, draws with WebGL, fills the window, is not blank and moves, and yet fails the brief completely. That is why this track is judged by eye.
