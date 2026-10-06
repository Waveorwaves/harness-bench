# Task: Resume an Interrupted Ingestion Job

Implement a small ingestion worker in a supplied seed repository with a persistent checkpoint and an explicitly defined idempotency key.

Acceptance behavior: after a crash, resume incomplete work; retrying a completed item does not duplicate visible documents or notifications; failures remain visible; bounded retries terminate; checkpoints cannot skip uncommitted work. Define and test the transaction boundary rather than promising general exactly-once execution.

Evidence: injected crashes before and after commit, independent acceptance output, persisted state and resulting artifact counts. Use local fixtures, not real notifications or external APIs.

Status: specification only. Seed, reviewed reference implementation and frozen evaluator still need to be created.

