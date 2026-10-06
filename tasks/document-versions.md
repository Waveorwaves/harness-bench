# Task: Immutable Document Versions

Implement source ingestion in a supplied small seed repository. Exact source identifiers are provided; URL canonicalization is out of scope.

Acceptance behavior: ingesting identical source bytes twice creates one version; changed bytes create a new version without overwriting old bytes; identical bytes from different sources retain both source associations; citations to old versions still resolve; failed ingestion does not mark a source updated; reruns are idempotent. Preserve first observation time separately from source publication time.

Evidence: independent acceptance results, preserved old/new content, and a before/after regression demonstration. Include out-of-order updates and simulated failures. No live network needed.

Status: specification only. Seed, reviewed reference implementation and frozen evaluator still need to be created.

