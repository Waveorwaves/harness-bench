# Sample solutions

`known-defect` is a real attempt at this task that looks finished and is not: it normalises line endings before parsing, so a note containing `\r\n` does not survive a round trip.

It is kept as a control for the hidden checks. `expected.json` lists the 1 check it must fail, and the test suite confirms that it fails exactly those and passes the rest, so a later edit to the checks cannot quietly stop catching these defects. The fake agent can replay it with `mock_agent.py variant known-defect`.

It was written on 2026-10-05 by a smaller model (Claude Haiku) working from the prompt alone, and is stored as the files that differ from the seed, unmodified.
