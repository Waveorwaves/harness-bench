# Pilot Protocol

## Research question
For bounded research-software engineering tasks, which harness/configuration produces accepted work with the least human intervention and acceptable elapsed time and usage?

## Stage A — controlled pilot
Codex vs Pi, same exact model identifier and reasoning effort if both support them. Verify access with a small authorized probe before scheduling live runs. If one cannot match, report incompatibility rather than silently switching models. Three tasks, three independent repetitions each, 18 planned runs. This is exploratory and cannot establish broad superiority.

Control task instructions, seed code, dependency versions, machine/container resources, tools, network policy, timeout and retry allowance. Record harness version and effective settings, not only requested settings. Run sequentially initially to avoid resource/rate-limit interference. Randomize harness order within each task/repetition block with a recorded seed. Start each trial in a fresh workspace with no prior agent session or learned skills. Record cache conditions and inaccessible provider defaults as limitations.

## Stage B — native configurations
Use each harness's recommended model/team configuration. Report configuration-level performance separately from Stage A. Add Devin, Capy and Hermes. Remote hardware, hidden prompts and unavailable effort controls may prevent causal attribution to the harness alone.

## Evaluation
Task specs define acceptance behavior. Frozen evaluators contain unseen inputs, not undisclosed requirements. Keep evaluators inaccessible to candidate workspaces. Validate evaluators against an independently reviewed reference implementation and deliberate failures before collecting runs. Candidate-provided tests and claims are not acceptance evidence.

Measure acceptance, regressions, wall time, recorded token/credit usage, measured billed cost where available, human interventions and minutes, retries, timeouts and blocked runs. Missing telemetry remains missing. Never equate subscription included usage with zero cost, or convert tokens into subscription dollars without an applicable billing basis.

Primary outcome: accepted work and operator burden. Report per task and per configuration with all outcomes; no unqualified winner from this pilot. Expand repetitions and task diversity before stronger claims. Keep harness evaluation separate from the product's research/claim-quality evaluation.

## Next concrete step
The image is built, `check` passes for the pilot suite, and the fake agent runs cleanly through Docker. Next: one probe per real harness (`run --limit 1 --harness <id>`) to confirm login and that its usage output parses, then fill in the price table and run the full plan. See [methodology](methodology.md) for what the results will and will not support.
