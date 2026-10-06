# Worked example: ranking the sample solutions

This page shows the visual track's judging and ranking working end to end. **It is not a harness comparison.**

- **The entries** are the stored sample solutions in each task's `variants/` folder plus the reference solution, replayed through the real capture pipeline by the fake agent (`suites/demo-showcase.json`). `sample-small-model`, `sample-mid-model` and `sample-large-model` are single blind attempts by Claude Haiku, Sonnet and Opus; `sample-plain` and `sample-faulty` were written by hand. One attempt each says nothing reliable about the models.
- **The judges** are two models, Claude Haiku and Claude Sonnet, run with `judge-model`. Each saw every pair twice with the sides swapped, in an empty folder holding only the two screenshots. No person has judged these pairs yet, so there is no human reference to validate the model judges against.
- **Produced on** 2026-10-05 with `python3 -m harness_bench rank`.

What to notice:

- On `pirate-ship-3d`, **all four entries passed all ten automatic checks**, including `sample-small-model`, in which no ship is visible. Both judges put it last. The automatic checks could not see the difference; the side-by-side picks did.
- The two judges agree on the bottom two of the 3D task and split on the top two. Their intervals overlap there, which is the ranking saying "not settled", correctly: six pairs cannot separate two strong entries.
- On `sunset-sail` the entries are further apart and the judges agree on every pair.
- Neither judge changed its answer when the sides were swapped. On closer contests that number is the first thing to check.

## `pirate-ship-3d`

6 pairs from 4 captured attempts across 4 configurations.

### Judge: claude-haiku (6 picks)

| Rank | Harness / model / mode | Rating | 95% interval | Share of picks won | Pairs |
|---:|---|---:|---|---:|---:|
| 1 | sample-mid-model / none / single | 1803 | 1566 to 1848 | 100% | 3 |
| 2 | sample-large-model / none / single | 1591 | 1386 to 1781 | 67% | 3 |
| 3 | sample-reference / none / single | 1409 | 1235 to 1623 | 33% | 3 |
| 4 | sample-small-model / none / single | 1197 | 1141 to 1407 | 0% | 3 |

### Judge: claude-sonnet (6 picks)

| Rank | Harness / model / mode | Rating | 95% interval | Share of picks won | Pairs |
|---:|---|---:|---|---:|---:|
| 1 | sample-large-model / none / single | 1803 | 1567 to 1846 | 100% | 3 |
| 2 | sample-mid-model / none / single | 1591 | 1386 to 1780 | 67% | 3 |
| 3 | sample-reference / none / single | 1409 | 1221 to 1623 | 33% | 3 |
| 4 | sample-small-model / none / single | 1197 | 1139 to 1432 | 0% | 3 |

### All judges pooled

| Rank | Harness / model / mode | Rating | 95% interval | Share of picks won | Pairs |
|---:|---|---:|---|---:|---:|
| 1 | sample-large-model / none / single | 1749 | 1571 to 1934 | 83% | 6 |
| 2 | sample-mid-model / none / single | 1749 | 1550 to 1929 | 83% | 6 |
| 3 | sample-reference / none / single | 1398 | 1219 to 1531 | 33% | 6 |
| 4 | sample-small-model / none / single | 1105 | 1031 to 1298 | 0% | 6 |

claude-haiku: gave a different answer when the sides were swapped on 0 of 6 pairs (recorded as ties); 0 had no readable answer.
claude-sonnet: gave a different answer when the sides were swapped on 0 of 6 pairs (recorded as ties); 0 had no readable answer.

### Agreement between judges

| Judges | Shared pairs | Same answer | Cohen's kappa |
|---|---:|---:|---:|
| claude-haiku and claude-sonnet | 6 | 83% | 0.67 |

## `sunset-sail`

10 pairs from 5 captured attempts across 5 configurations.

### Judge: claude-haiku (10 picks)

| Rank | Harness / model / mode | Rating | 95% interval | Share of picks won | Pairs |
|---:|---|---:|---|---:|---:|
| 1 | sample-mid-model / none / single | 1872 | 1590 to 1938 | 100% | 4 |
| 2 | sample-reference / none / single | 1665 | 1450 to 1860 | 75% | 4 |
| 3 | sample-small-model / none / single | 1500 | 1309 to 1717 | 50% | 4 |
| 4 | sample-plain / none / single | 1335 | 1151 to 1555 | 25% | 4 |
| 5 | sample-faulty / none / single | 1128 | 1053 to 1392 | 0% | 4 |

### Judge: claude-sonnet (10 picks)

| Rank | Harness / model / mode | Rating | 95% interval | Share of picks won | Pairs |
|---:|---|---:|---|---:|---:|
| 1 | sample-mid-model / none / single | 1872 | 1590 to 1938 | 100% | 4 |
| 2 | sample-reference / none / single | 1665 | 1450 to 1860 | 75% | 4 |
| 3 | sample-small-model / none / single | 1500 | 1309 to 1717 | 50% | 4 |
| 4 | sample-plain / none / single | 1335 | 1151 to 1555 | 25% | 4 |
| 5 | sample-faulty / none / single | 1128 | 1053 to 1392 | 0% | 4 |

### All judges pooled

| Rank | Harness / model / mode | Rating | 95% interval | Share of picks won | Pairs |
|---:|---|---:|---|---:|---:|
| 1 | sample-mid-model / none / single | 2013 | 1806 to 2074 | 100% | 8 |
| 2 | sample-reference / none / single | 1724 | 1564 to 1909 | 75% | 8 |
| 3 | sample-small-model / none / single | 1500 | 1343 to 1659 | 50% | 8 |
| 4 | sample-plain / none / single | 1276 | 1101 to 1443 | 25% | 8 |
| 5 | sample-faulty / none / single | 987 | 907 to 1219 | 0% | 8 |

claude-haiku: gave a different answer when the sides were swapped on 0 of 10 pairs (recorded as ties); 0 had no readable answer.
claude-sonnet: gave a different answer when the sides were swapped on 0 of 10 pairs (recorded as ties); 0 had no readable answer.

### Agreement between judges

| Judges | Shared pairs | Same answer | Cohen's kappa |
|---|---:|---:|---:|
| claude-haiku and claude-sonnet | 10 | 100% | 1.00 |

## Reading the numbers

Ratings are Bradley-Terry strengths on an Elo-style scale: 1500 is average, and a 400-point gap means ten-to-one odds of being picked. Intervals come from resampling the picks. Overlapping intervals mean the order is not settled.
Kappa is agreement beyond chance: 0 is chance level and 1 is perfect. It is undefined when both judges gave one and the same answer every time. A model judge is only worth trusting on a task where it agrees well with people.
