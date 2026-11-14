# Fixtures

All fixtures are synthetic, generated deterministically by
`generator.py` (seed 42) and pinned by the golden evals. No real
person, customer, or company appears in any of them.

| File | Contents |
|---|---|
| `ratings.json` | The main dataset: 36 fictional Lumen Desk support cases, each rated by 4 fictional raters (pass/fail nominal + 1–5 quality ordinal), with planted disagreement patterns, 10 planted missing ratings, and a planted adjudicator decision on every disagreed case. |
| `heldout_pool.json` | A 10-item held-out pool: 8 fresh items plus 2 planted near-duplicates of golden cases C003 and C012 (same text, new customer name and ticket ref). |
| `perfect_agreement.json` | Sanity set: 12 cases, all raters identical. Krippendorff's alpha must be exactly 1.0 under both metrics. |
| `chance_agreement.json` | Sanity set: 40 cases with seeded random labels. Alpha must land near 0 (pinned: nominal 0.055937, ordinal 0.028164). |

Regenerate any of them with `python3 cli.py generate --what
<ratings|heldout|perfect|chance>`.

## Feedback-loop closure — one planted worked example (v2)

A golden set is not finished when it is exported; it is finished
when the disagreements it surfaced have changed the labeling
guidelines and the change has been re-checked. That loop is a
human process, not a feature of this kit — so instead of code for
it, here is exactly one worked example of the closure record a
team would keep for the dataset above. The v1 column is real — it
counts this fixture's adjudicated cases by failure class. The
rubric changes and the entire v2 re-check column are planted: no
v2 round was ever run. In the story, the v1 round's disagreements
were grouped by failure class, the rubric was revised once (v2),
and a fresh sample of each class was re-rated:

| Failure class | v1 disagreed cases | v2 rubric change | v2 re-check |
|---|---|---|---|
| tone_mismatch | 3 | Added an explicit empathy bar: a correct-but-curt reply to a frustrated customer is a pass on task, quality capped at 3 | Fixed — new sample unanimous |
| missed_instruction | 3 | Added a checklist rule: count the customer's explicit instructions and verify each one before scoring | Fixed — new sample unanimous |
| factual_error | 3 | Added a verify-the-fact step naming the account record as the source of truth | Still open — 1 of 6 re-check cases split again; escalated to a third adjudicator |
| incomplete | 1 | Added a required-steps list for password-reset cases | Fixed — new sample unanimous |
| none (clear cases) | 1 | No change — the split traced to one rater's misread, handled in rater feedback | Regressed in re-check — 1 new split appeared; under watch, no rubric change |

"Fixed" means the re-check sample for that class reached unanimous
labels; "regressed" means a class that was quiet in v1 produced a
new disagreement in the v2 re-check. This table is an example
record only — nothing in the code computes it, and the v2 column
is planted, not measured.
