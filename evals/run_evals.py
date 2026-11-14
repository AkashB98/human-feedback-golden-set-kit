"""Golden evals for human-feedback-golden-set-kit.

SYNTHETIC DATA ONLY (fictional Lumen Desk support agent, fictional
raters). Every eval is deterministic: run_evals.py writes
eval_report.json and the file must be byte-identical across runs.
No timestamps, ports, or temp paths enter the report — only names,
booleans, pinned counts and hashes.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import threading
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))

from adjudication import adjudicate_dataset  # noqa: E402
from agreement import krippendorff_alpha, units_from_cases  # noqa: E402
from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main as cli_main  # noqa: E402
from cli import make_server, reset_state  # noqa: E402
from generator import (  # noqa: E402
    dataset_to_json, generate_dataset, generate_heldout, generate_sanity,
    load_json,
)
from golden import build_export, build_golden_set  # noqa: E402
from helpers import (  # noqa: E402
    calm_dataset_with_thin, dataset_without_adjudicator,
    low_alpha_dataset,
)
from leakage import case_text, find_leakage, text_similarity  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = []
ORDINAL_DOMAIN = [1, 2, 3, 4, 5]


def check(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    return passed


def _run_cli(argv):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return cli_main(argv)


def main():
    print("== golden evals: human-feedback-golden-set-kit ==")
    dataset = generate_dataset()
    heldout = generate_heldout()
    clean_pool = generate_heldout(clean=True)

    # E1: generator determinism (ratings bytes pinned)
    md5 = hashlib.md5(dataset_to_json(dataset).encode()).hexdigest()
    check("E1 generator determinism (seed=42 ratings md5 pinned)",
          dataset_to_json(generate_dataset()) == dataset_to_json(dataset)
          and md5 == "b872a57c3bea6cdc08bef229ee808a17",
          f"md5={md5}")

    # E2: shape + planted missing ratings pinned
    missing = sum(1 for c in dataset["cases"]
                  for v in c["nominal"].values() if v is None)
    check("E2 shape pinned (36 cases x 4 raters, 10 missing ratings, "
          "heldout 10 items / clean 8)",
          len(dataset["cases"]) == 36 and missing == 10
          and len(heldout["items"]) == 10
          and len(clean_pool["items"]) == 8)

    # E3: sanity alphas — perfect exactly 1, chance pinned near 0
    perfect = generate_sanity("perfect")
    chance = generate_sanity("chance")
    p_nom = krippendorff_alpha(units_from_cases(perfect["cases"], "nominal"),
                               "nominal")
    p_ord = krippendorff_alpha(units_from_cases(perfect["cases"], "ordinal"),
                               "ordinal", domain=ORDINAL_DOMAIN)
    c_nom = round(krippendorff_alpha(
        units_from_cases(chance["cases"], "nominal"), "nominal"), 6)
    c_ord = round(krippendorff_alpha(
        units_from_cases(chance["cases"], "ordinal"), "ordinal",
        domain=ORDINAL_DOMAIN), 6)
    check("E3 sanity alphas pinned (perfect 1.0/1.0; chance "
          "0.055937/0.028164)",
          p_nom == 1.0 and p_ord == 1.0
          and c_nom == 0.055937 and c_ord == 0.028164,
          f"chance_nominal={c_nom} chance_ordinal={c_ord}")

    # E4: hand-computed alpha cases
    hand_nom = krippendorff_alpha([[1, 1], [1, 1], [2, 2], [2, 1], [1, 2]],
                                  "nominal")
    hand_3 = krippendorff_alpha([[1, 1, 1], [2, 2, 1], [2, 2, 2]], "nominal")
    hand_ord = krippendorff_alpha([[1, 1], [2, 2], [3, 3], [1, 2]],
                                  "ordinal", domain=[1, 2, 3])
    hand_pair_nom = krippendorff_alpha([[1, 1], [2, 2], [3, 3], [1, 2]],
                                       "nominal")
    check("E4 hand-computed alphas (nominal 0.25; 3-rater 0.6; ordinal "
          "0.79; same-data nominal 2/3)",
          abs(hand_nom - 0.25) < 1e-12 and abs(hand_3 - 0.6) < 1e-12
          and abs(hand_ord - 0.79) < 1e-12
          and abs(hand_pair_nom - 2 / 3) < 1e-12)

    # E5: main-dataset alphas pinned
    report = adjudicate_dataset(dataset)
    check("E5 main alphas pinned (nominal 0.685802 above floor 0.667; "
          "ordinal 0.895938; not escalated)",
          report["alpha_nominal"] == 0.685802
          and report["alpha_ordinal"] == 0.895938
          and report["escalated"] is False)

    # E6: adjudication counts pinned
    check("E6 adjudication counts pinned (AGREED 25, ADJUDICATED 11, "
          "INCOMPLETE 0)",
          report["counts"] == {"AGREED": 25, "ADJUDICATED": 11,
                               "INCOMPLETE": 0})

    # E7: golden export pinned
    golden = build_golden_set(dataset)
    check("E7 golden export pinned (36 cases, sorted, provenance "
          "complete, no planted_truth leaked)",
          len(golden) == 36
          and [g["case_id"] for g in golden]
          == sorted(g["case_id"] for g in golden)
          and all("planted_truth" not in g for g in golden)
          and all(g["provenance"]["rationale"] for g in golden))

    # E8: incomplete handling — a disagreed case stripped of its
    # adjudicator is excluded from the golden set and listed.
    export_gap = build_export(dataset_without_adjudicator("C010"))
    check("E8 incomplete handling pinned (C010 excluded, golden 35, "
          "audit trail still complete)",
          export_gap["incomplete_case_ids"] == ["C010"]
          and len(export_gap["golden_set"]) == 35
          and len(export_gap["audit_trail"]) == 36)

    # E9: leakage on the planted pool — exactly the two planted pairs
    flags = find_leakage(golden, heldout["items"])
    by_pair = {(f["golden_case_id"], f["heldout_case_id"]): f["jaccard"]
               for f in flags}
    check("E9 leakage pinned (C003~H009 0.803571; C012~H010 0.804348; "
          "nothing else)",
          by_pair == {("C003", "H009"): 0.803571,
                      ("C012", "H010"): 0.804348},
          f"flags={by_pair}")

    # E10: clean pool + internal duplicates + separation margin
    export_clean = build_export(dataset, clean_pool)
    max_distinct = 0.0
    for a in range(len(golden)):
        for b in range(a + 1, len(golden)):
            sim = text_similarity(case_text(golden[a]),
                                  case_text(golden[b]))
            max_distinct = max(max_distinct, sim)
    check("E10 separation pinned (clean pool 0 flags; internal dupes 0; "
          "max distinct-pair similarity 0.481752 < 0.5 threshold)",
          export_clean["leakage"] == []
          and export_clean["internal_duplicates"] == []
          and round(max_distinct, 6) == 0.481752,
          f"max_distinct={round(max_distinct, 6)}")

    # E11: escalation behaviour pinned on helper datasets
    low = adjudicate_dataset(low_alpha_dataset())
    calm = adjudicate_dataset(calm_dataset_with_thin())
    thin_low = next(r for r in low["records"] if r["case_id"] == "L006")
    thin_calm = next(r for r in calm["records"] if r["case_id"] == "K011")
    check("E11 escalation pinned (low-alpha run escalates, thin case "
          "INCOMPLETE; calm run does not, thin case AGREED)",
          low["escalated"] is True and thin_low["status"] == "INCOMPLETE"
          and calm["escalated"] is False
          and thin_calm["status"] == "AGREED")

    # E12: missing-data invariance — singleton units change nothing
    base = [[1, 1], [1, 1], [2, 2], [2, 1], [1, 2]]
    extended = base + [[1], [None, None], [2], []]
    check("E12 missing-data invariance (singletons/empty units leave "
          "alpha at 0.25)",
          abs(krippendorff_alpha(extended, "nominal") - 0.25) < 1e-12)

    # E13: CLI check exit codes 1 / 0 / 2
    import tempfile
    tmp = tempfile.mkdtemp(prefix="golden-evals-")
    ratings_path = os.path.join(tmp, "ratings.json")
    bad_path = os.path.join(tmp, "heldout.json")
    good_path = os.path.join(tmp, "heldout_clean.json")
    from generator import write_json
    write_json(dataset, ratings_path)
    write_json(heldout, bad_path)
    write_json(clean_pool, good_path)
    codes = (_run_cli(["check", "--input", ratings_path,
                       "--heldout", bad_path]),
             _run_cli(["check", "--input", ratings_path,
                       "--heldout", good_path]),
             _run_cli(["check", "--input", "/tmp/no-such-ratings-xyz.json"]))
    check("E13 CLI check exit codes 1/0/2 (planted-pool refusal is by "
          "design)", codes == (EXIT_FAIL, EXIT_OK, EXIT_ERROR),
          f"codes={codes}")

    # E14: serve round-trip matches local computation
    reset_state(dataset, clean_pool)
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/alpha", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            served_alpha = json.loads(resp.read())
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/report",
                                    timeout=10) as resp:
            served_report = json.loads(resp.read())
        serve_ok = (served_alpha["alpha_nominal"] == 0.685802
                    and served_report == export_clean)
    finally:
        server.shutdown()
        server.server_close()
        reset_state()
    check("E14 serve round-trip matches local export + alpha", serve_ok)

    # E15: bundled fixtures pinned
    fx_ratings = load_json(os.path.join(ROOT, "fixtures", "ratings.json"))
    fx_pool = load_json(os.path.join(ROOT, "fixtures", "heldout_pool.json"))
    fx_perfect = load_json(os.path.join(ROOT, "fixtures",
                                        "perfect_agreement.json"))
    fx_chance = load_json(os.path.join(ROOT, "fixtures",
                                       "chance_agreement.json"))
    check("E15 fixtures pinned (files equal the seeded generator output)",
          fx_ratings == dataset and fx_pool == heldout
          and fx_perfect == perfect and fx_chance == chance)

    passed = sum(1 for r in RESULTS if r["passed"])
    total_n = len(RESULTS)
    summary_doc = {"passed": passed, "total": total_n,
                   "all_passed": passed == total_n, "evals": RESULTS}
    with open(os.path.join(HERE, "eval_report.json"), "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(summary_doc, sort_keys=True) + "\n")
    print(f"\n{passed}/{total_n} evals passed -> evals/eval_report.json")
    return 0 if passed == total_n else 1


if __name__ == "__main__":
    sys.exit(main())
