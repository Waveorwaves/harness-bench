# Task: Preserve Financial Metric Meaning

Implement comparison of structured observations in a supplied seed repository. Inputs provide entity, metric definition, unit/currency, period, fiscal/calendar basis, actual/guidance status, cash/lease basis, observation date, publication date and evidence reference.

Acceptance behavior: compare only like-for-like metrics; do not merge guidance with actuals, cash capex with lease-inclusive capex, different periods/currencies, or total spending with AI-only spending. Preserve unknown fields and mark incomparable cases. Given an as-of cutoff, exclude observations not available by that cutoff. Revised guidance must not overwrite earlier evidence.

Evidence: independent acceptance results plus examples of valid comparison and rejected comparisons. No currency conversion, investing recommendation or LLM call is required.

Status: specification only. Seed, reviewed reference implementation and frozen evaluator still need to be created.

