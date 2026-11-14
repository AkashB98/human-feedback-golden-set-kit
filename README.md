# human-feedback-golden-set-kit

**Before any judge exists, the humans have to agree: a golden-set pipeline that measures human-vs-human agreement with Krippendorff's alpha (nominal 0.686, ordinal 0.896 on the seeded data), routes every disagreed case to a recorded adjudication, exports the survivors as a provenanced golden set, and catches the held-out pool quietly containing copies of it (2 planted near-duplicates flagged at Jaccard 0.80, clean pool flags nothing).**

Every eval program starts with people labelling examples — and most teams never check whether those people agree with each other. If two trained raters looking at the same agent response cannot produce the same label, the "golden set" built from their labels is noise with a confident name, and every judge or model scored against it inherits the noise. This kit builds the pre-judge stage end to end on synthetic data: multiple human raters label agent responses, **Krippendorff's alpha** — a chance-corrected agreement statistic built for 3+ raters with missing labels — measures whether the labels are reproducible, disagreed cases go to **adjudication** — a senior reviewer's recorded decision, with rationale — and only cases with a final label are exported as the **golden set**, which is then checked for **leakage** — near-duplicate contamination — against the held-out pool it will be compared with. The build was motivated by Applied AI / evaluation roles (Mercor, Figma, 2026-11) whose job descriptions centre on rubrics, representative datasets, and human-feedback quality as the deliverable.

> **Not the judge-calibration repo.** The sibling `llm-judge-calibration` measures a *machine judge against human grades* (quadratic-weighted kappa, calibration error) — it assumes trustworthy human labels and grades the grader. This kit is the stage *before* that: **human vs human**, no judge anywhere, and deliberately **no Cohen's kappa** — kappa handles exactly two raters and no missing data, which is not the shape of real annotation. Krippendorff's alpha is the statistic that fits this stage.

> **Synthetic data only.** Every case, rater, and label is fabricated by a seeded generator about a fictional product (**Lumen Desk**) and its fictional support agent. No real person, customer, or company is used anywhere. The adjudicator decisions are planted by the generator (see Honest limits).

Stdlib-only Python — deliberately. Agreement statistics and audit trails are trust artifacts: anyone should be able to read every line, re-run offline, and get byte-identical outputs. Zero network, zero API keys, zero external dependencies.

## The seeded dataset at a glance (seed 42)

36 cases × 4 raters. Each rater gives a nominal pass/fail and an ordinal quality score (1–5). Planted patterns: clear cases, borderline cases, a tone case only the strict rater (R4) fails, a missed-instruction case only the lenient rater (R3) passes, lenient/strict ordinal drift, a seeded scatter of missing ratings plus a planted block (R4 absent for C029–C031) — 10 missing ratings in total.

| Measure | Value | Reading |
|---|---|---|
| Krippendorff alpha, nominal | **0.685802** | Above the 0.667 floor, inside Krippendorff's *tentative* band (0.667–0.800) — usable with adjudication, not yet "reliable" |
| Krippendorff alpha, ordinal | **0.895938** | In the reliable band (≥ 0.800): raters rank quality consistently even when their pass/fail thresholds differ |
| Adjudication | 25 AGREED / 11 ADJUDICATED / 0 INCOMPLETE | Every disagreement carries a recorded adjudicator decision + rationale |
| Sanity: perfect-agreement set | alpha exactly **1.0** (both metrics) | The statistic on a known answer |
| Sanity: seeded random labels | alpha **0.055937** nominal / **0.028164** ordinal | Chance-level lands near 0, as it must |

The nominal/ordinal gap is itself the finding: the raters largely agree about *how good* a response is (ordinal 0.896) and disagree more about *where the pass line sits* (nominal 0.686) — which is why the pass/fail labels are the ones that need adjudication.

## Quickstart

```bash
# 1. Generate the seeded ratings dataset (or heldout / perfect / chance)
python3 cli.py generate --out ratings.json
python3 cli.py generate --what heldout --out heldout.json          # plants 2 near-dupes
python3 cli.py generate --what heldout --clean --out heldout_clean.json

# 2. Agreement: Krippendorff alpha, nominal + ordinal
python3 cli.py alpha --input ratings.json

# 3. Adjudication report (records, counts, escalation state)
python3 cli.py adjudicate --input ratings.json

# 4. Golden set + audit trail + leakage vs a held-out pool
python3 cli.py export --input ratings.json --heldout heldout.json
python3 cli.py leakage --input ratings.json --heldout heldout.json

# 5. CI gate: exit 0 = pass, 1 = FAIL (EXPECTED with the seeded pool —
#    it plants the near-duplicates), 2 = IO / usage error
python3 cli.py check --input ratings.json --heldout heldout.json
python3 cli.py check --input ratings.json --heldout heldout_clean.json   # exit 0

# 6. One-command end-to-end demo (sanity sets lead)
python3 demo.py

# 7. Tiny localhost API: POST /alpha /adjudicate /report,
#    GET /report, GET /health on 127.0.0.1
python3 cli.py serve --port 8765
```

## How it works

**Agreement (`agreement.py`).** Alpha = 1 − Do/De from the coincidence matrix: for each case, every ordered pair of ratings contributes, normalised by (m − 1) where m is the number of ratings on that case. Cases with fewer than two ratings form no pairs and are excluded — missing ratings shrink the evidence, they are never imputed. The nominal metric charges 1 for any label mismatch; the ordinal metric charges Krippendorff's squared rank distance built from the marginal counts, so a 1-vs-2 near miss costs far less than a 1-vs-5 far miss. The implementation is verified against cases computed by hand from the definition before it existed (nominal 0.25 on a 5-unit binary set; 0.6 with three raters; ordinal 0.79 vs nominal 2/3 on the same near-miss data — the test file shows the arithmetic).

**Adjudication (`adjudication.py`).** Deterministic rules: no ratings → INCOMPLETE; unanimous nominal labels with ordinal spread ≤ 1 → AGREED (final quality = lower median); anything else must carry an adjudicator decision — final label, final quality, rationale, adjudicator id — or it is INCOMPLETE and the pipeline refuses to invent a label. Majority vote is recorded on every disagreed case as a diagnostic, including whether the adjudicator followed it; it never decides by itself. **Escalation:** when nominal alpha falls below the floor (0.667, Krippendorff's tentative-conclusion threshold), the run is stamped escalated and thin agreements — exactly two raters, ordinal spread exactly 1 — are re-routed to adjudication too, because at that agreement level a two-rater "agreement" is not evidence.

**Golden export (`golden.py`).** Every case with a final label, sorted, each carrying provenance: source dataset, the raw rater labels, AGREED/ADJUDICATED status, adjudicator and rationale where applicable. The generator's planted truth is *not* exported. INCOMPLETE cases are excluded from the golden set but stay in the audit trail (the adjudication records, one per case, in order) and are listed by id — the gap is visible, never silent.

**Leakage (`leakage.py`).** Word 3-gram Jaccard similarity between each golden case (prompt + response) and each held-out item; pairs at or above 0.5 are flagged, and the same check runs inside the golden set itself. On the seeded data the separation is measured, not asserted: the two planted near-duplicates score **0.803571** and **0.804348**, the most similar *distinct* golden pair scores **0.481752**, and the clean pool flags nothing. The check reports pairs; a human decides whether a flagged item is contamination or a legitimately similar case.

**Feedback-loop closure** is a human process, not a feature: `fixtures/README.md` contains exactly one planted worked example of the closure record (per-failure-class v1 disagreement counts — which match this fixture's real adjudication counts — plus a fictional v2 rubric revision and re-check). Nothing in the code computes it.

## Architecture

| Module | Job |
|---|---|
| `agreement.py` | Krippendorff's alpha (nominal + ordinal) via coincidence matrices, with Do/De/marginals exposed; missing-rating handling; sanity conventions (no pairable ratings → error, De = 0 → 1.0) |
| `adjudication.py` | Adjudication rules (agreed / adjudicated / incomplete), majority-vote diagnostic, alpha-floor escalation with thin-agreement re-routing |
| `leakage.py` | Word n-gram Jaccard near-duplicate check (golden vs held-out, and within-set), deterministic flag ordering |
| `generator.py` | Deterministic synthetic data: main ratings dataset (planted splits, lenient/strict raters, missing ratings incl. the R4 block, planted adjudicator decisions), held-out pool (fresh items + 2 planted near-duplicates, plus a clean flavour), perfect/chance sanity sets |
| `golden.py` | Golden-set export with provenance, audit trail, incomplete listing, export bundle assembly |
| `cli.py` | `generate` / `alpha` / `adjudicate` / `export` / `leakage` / `report` / `check` (CI exit 0/1/2) / `demo` / `serve` (stdlib `http.server` on 127.0.0.1) |
| `demo.py` | End-to-end narrative with asserts, led by the sanity sets: determinism, perfect = 1.0, chance ≈ 0, main alphas, adjudication completeness, golden export, exactly the 2 planted leakage flags, check exit codes, live serve round-trip |
| `fixtures/` | The seeded datasets (`ratings.json` 36 cases, `heldout_pool.json` 10 items, both sanity sets) with pinned hashes, plus the one planted v2 closure table in `fixtures/README.md` |

## Evals

`python3 evals/run_evals.py` → **15/15 golden evals**, report committed at `evals/eval_report.json` (md5 `25f789b271e911cd1e54ec8c7c4fd4f6`, byte-identical across 3 verified runs):

- **E1** generator determinism — ratings JSON md5 pinned (`b872a57c…`)
- **E2** shape pinned (36 cases × 4 raters, 10 missing ratings, held-out 10 / clean 8 items)
- **E3** sanity alphas pinned (perfect 1.0/1.0; chance 0.055937 / 0.028164)
- **E4** hand-computed alphas (nominal 0.25; three-rater 0.6; ordinal 0.79; same-data nominal 2/3)
- **E5** main alphas pinned (nominal 0.685802 above the 0.667 floor; ordinal 0.895938; not escalated)
- **E6** adjudication counts pinned (25 AGREED / 11 ADJUDICATED / 0 INCOMPLETE)
- **E7** golden export pinned (36 cases, sorted, provenance complete, no planted truth leaked)
- **E8** incomplete handling (adjudicator stripped from C010 → excluded, golden 35, audit trail still 36)
- **E9** leakage pinned (exactly C003~H009 at 0.803571 and C012~H010 at 0.804348)
- **E10** separation pinned (clean pool 0 flags; internal duplicates 0; max distinct-pair similarity 0.481752 < 0.5)
- **E11** escalation pinned (low-alpha run escalates and re-routes the thin case to INCOMPLETE; calm run does neither)
- **E12** missing-data invariance (singleton/empty units leave alpha unchanged)
- **E13** CLI `check` exit codes 1 / 0 / 2 (the seeded 1 is the planted leakage, by design)
- **E14** serve round-trip matches local export + alpha exactly
- **E15** bundled fixtures pinned (files equal the seeded generator output)

Unit tests: `python3 -m unittest discover -s tests` → **81 hermetic tests**, including a no-network enforcement test (sockets stubbed), the hand-computed alpha cases with the arithmetic in comments, coincidence-matrix pinning, permutation/relabel/domain invariances, escalation re-routing, leakage thresholds, CLI exit codes, and serve round-trips.

## Development loop — what the checks actually caught

1. **The first rater model made pass/fail a threshold on the quality score** (pass ⟺ perceived quality ≥ 3), which made every quality-3 case a coin flip and dragged nominal alpha to **0.454** — below the floor, on data designed to be ratable. The model was wrong, not the statistic: real raters judge task success separately from fluency (a fluent reply that missed an instruction is quality 3 *and* a fail). Nominal labels are now their own judgment with the planted lenient/strict deviations; nominal alpha landed at 0.686, in the tentative band — reported as such, not tuned into the reliable band.
2. **The leakage check flagged the dataset against itself.** Templated variants of one archetype differ only in name/ref/amount slots, so distinct cases scored Jaccard 0.51–0.63 — above the 0.5 threshold, 54 internal pairs. Two fixes: each case now carries detail sentences assembled from fragment slots (same substance, different surface; max distinct pair now 0.481752), and the planted near-duplicates swap in names/refs from *outside* the variant slot cycles, after the first dupe turned out to share its replacement name with a sibling variant and flagged against the wrong case at 0.554.
3. **A test pointed at the wrong case after the archetype reorder.** When a tenth archetype was added (which also brought the planted split count from 8 to 6), the leniency cases moved from C009 to C010/C020/C030 and the incomplete-handling test's fixture case silently stopped being an adjudicated case. The helper now asserts its precondition, so a future reorder fails at the helper, not mysteriously downstream.

## Scope and honest limits

- **The adjudicator is planted, not simulated intelligence.** The generator attaches a senior reviewer's decision to each disagreed case so the *record* — routing, rationale, audit trail, majority diagnostic — can be built and tested. This kit does not decide hard cases; in a real program a person does, and this is the paperwork that makes their decision traceable.
- **Nominal alpha 0.686 is tentative, not reliable.** Krippendorff's own reading: 0.667–0.800 supports tentative conclusions only. The seeded dataset sits there deliberately (planted splits are the point), and the README reports the band instead of rounding the story up. The escalation rule exists precisely for datasets that fall below it.
- **Ordinal alpha is a rank statistic.** Its distances come from the data's marginal distribution (cumulative counts), not from assuming the 1–5 scale is evenly spaced. Two datasets with identical raw score gaps can therefore get different ordinal alphas — that is Krippendorff's definition, and it is documented in `agreement.py` rather than smoothed over.
- **The leakage check sees surface, not meaning.** Word 3-gram Jaccard catches re-entered or lightly edited text (the planted failure mode). A paraphrased duplicate is invisible to it. The distinct-pair margin is also thin — 0.481752 against a 0.5 threshold — and is pinned by eval E10 so any generator change that erodes it fails loudly instead of silently.
- **Synthetic rater behaviour is a caricature.** One lenient rater, one strict rater, and planted pattern splits are a test fixture, not a model of real annotation teams; real disagreement is messier and usually less legible.
- **The API is a demo surface.** It binds 127.0.0.1 only, holds its dataset in memory, and resets on restart.

## Why this project

It takes the least glamorous, most load-bearing step of evaluation work — proving the human labels deserve to be called "gold" — and rebuilds it as an engineering artifact: an agreement statistic verified against hand-computed cases and known-answer sanity sets, an adjudication record that refuses to invent labels, a golden export whose provenance survives inspection, and a leakage check with measured separation between "similar case" and "same case wearing a new ticket number". Measure the humans first; only then grade the graders.
