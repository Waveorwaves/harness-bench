# Sample solutions

Alternative solutions to this task, of deliberately different quality. The fake agent can replay any of them (`mock_agent.py variant <name>`), which gives the capture and judging steps real, different-looking entries to work on. They also serve as controls for the automatic checks.

| Folder | What it is | Automatic checks |
|---|---|---|
| `plain` | written by hand to meet the requirements and nothing more | 10/10 |
| `broken` | written by hand to break them: a small fixed canvas, a still picture, a script error | 5/10 |
| `small-model` | one attempt by a smaller model (Claude Haiku) from the prompt alone | 10/10 |
| `mid-model` | one attempt by a mid-sized model (Claude Sonnet) from the prompt alone | 10/10 |

The two model attempts were made on 2026-10-05 by subagents in this project's development session, given only `prompt.md` and the seed, told not to open a browser or download anything, and are stored unmodified. One attempt each: they illustrate the range of results the task produces and say nothing reliable about the models.
