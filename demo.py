"""End-to-end demo: generate -> sanity alphas -> agreement ->
adjudication -> golden export -> leakage -> check -> serve.

SYNTHETIC DATA ONLY (fictional Lumen Desk support agent, fictional
raters). Runs fully offline; the serve round-trip is loopback only
on an ephemeral port. Every stage asserts.

The demo leads with the sanity sets, because that is the point of
the kit: an agreement statistic you cannot trust on data where the
answer is known (perfect agreement must be exactly 1, seeded random
labels must land near 0) cannot be trusted on real labels either.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import EXIT_FAIL, EXIT_OK, main as cli_main, make_server, reset_state  # noqa: E402
from adjudication import adjudicate_dataset  # noqa: E402
from agreement import krippendorff_alpha, units_from_cases  # noqa: E402
from generator import generate_dataset, generate_heldout, generate_sanity, write_json  # noqa: E402
from golden import build_export  # noqa: E402

ORDINAL_DOMAIN = [1, 2, 3, 4, 5]


def _request(port: int, path: str, payload=None, method: str = "GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def main() -> None:
    print("== 1. generate the seeded ratings dataset (seed=42) ==")
    dataset = generate_dataset()
    assert dataset == generate_dataset(), "generator must be deterministic"
    missing = sum(1 for c in dataset["cases"]
                  for v in c["nominal"].values() if v is None)
    print(f"   {len(dataset['cases'])} cases x {len(dataset['raters'])} "
          f"raters, {missing} missing ratings (planted), deterministic")

    print("\n== 2. sanity sets: the statistic on known answers ==")
    perfect = generate_sanity("perfect")
    chance = generate_sanity("chance")
    p_nom = krippendorff_alpha(units_from_cases(perfect["cases"], "nominal"),
                               "nominal")
    p_ord = krippendorff_alpha(units_from_cases(perfect["cases"], "ordinal"),
                               "ordinal", domain=ORDINAL_DOMAIN)
    c_nom = krippendorff_alpha(units_from_cases(chance["cases"], "nominal"),
                               "nominal")
    c_ord = krippendorff_alpha(units_from_cases(chance["cases"], "ordinal"),
                               "ordinal", domain=ORDINAL_DOMAIN)
    print(f"   perfect agreement: alpha nominal {p_nom}, ordinal {p_ord}")
    print(f"   chance labels:     alpha nominal {c_nom:.4f}, "
          f"ordinal {c_ord:.4f}")
    assert p_nom == 1.0 and p_ord == 1.0
    assert abs(c_nom) < 0.15 and abs(c_ord) < 0.15

    print("\n== 3. agreement on the main dataset (human vs human) ==")
    report = adjudicate_dataset(dataset)
    print(f"   Krippendorff alpha nominal {report['alpha_nominal']} "
          f"(floor {report['alpha_floor']}), ordinal "
          f"{report['alpha_ordinal']}, escalated={report['escalated']}")
    assert not report["escalated"]
    assert report["alpha_ordinal"] > report["alpha_nominal"]

    print("\n== 4. adjudication: disagreements get a recorded decision ==")
    print(f"   counts: {report['counts']}")
    assert report["counts"]["INCOMPLETE"] == 0
    assert report["counts"]["ADJUDICATED"] > 0
    for rec in report["records"]:
        if rec["status"] == "ADJUDICATED":
            assert rec["rationale"] and rec["adjudicator"]

    print("\n== 5. golden export + audit trail ==")
    export = build_export(dataset, generate_heldout(clean=True))
    print(f"   golden cases: {len(export['golden_set'])}, audit trail "
          f"entries: {len(export['audit_trail'])}, internal duplicates: "
          f"{len(export['internal_duplicates'])}")
    assert len(export["golden_set"]) == len(dataset["cases"])
    assert len(export["audit_trail"]) == len(dataset["cases"])
    assert export["internal_duplicates"] == []

    print("\n== 6. leakage: the seeded pool is contaminated, by design ==")
    contaminated = build_export(dataset, generate_heldout())
    for flag in contaminated["leakage"]:
        print(f"   - golden {flag['golden_case_id']} ~ held-out "
              f"{flag['heldout_case_id']} (Jaccard {flag['jaccard']})")
    pairs = {(f["golden_case_id"], f["heldout_case_id"])
             for f in contaminated["leakage"]}
    assert pairs == {("C003", "H009"), ("C012", "H010")}
    assert export["leakage"] == [], "clean pool must flag nothing"

    print("\n== 7. CLI check gate (1 on contaminated pool BY DESIGN, "
          "0 on clean, 2 on missing) ==")
    tmp = tempfile.mkdtemp(prefix="golden-demo-")
    ratings_path = os.path.join(tmp, "ratings.json")
    bad_pool = os.path.join(tmp, "heldout.json")
    good_pool = os.path.join(tmp, "heldout_clean.json")
    write_json(dataset, ratings_path)
    write_json(generate_heldout(), bad_pool)
    write_json(generate_heldout(clean=True), good_pool)
    code_bad = cli_main(["check", "--input", ratings_path,
                         "--heldout", bad_pool])
    code_good = cli_main(["check", "--input", ratings_path,
                          "--heldout", good_pool])
    code_err = cli_main(["check", "--input", "/tmp/no-such-ratings-xyz.json"])
    print(f"   contaminated={code_bad} clean={code_good} "
          f"missing-file={code_err}")
    assert code_bad == EXIT_FAIL and code_good == EXIT_OK and code_err == 2

    print("\n== 8. live localhost serve round-trip ==")
    reset_state(dataset, generate_heldout(clean=True))
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, health = _request(port, "/health")
        assert status == 200 and health == {"status": "ok"}
        status, served_alpha = _request(port, "/alpha", payload={},
                                        method="POST")
        assert status == 200 \
            and served_alpha["alpha_nominal"] == report["alpha_nominal"]
        status, served_report = _request(port, "/report")
        assert status == 200 and served_report == export
        print("   POST /alpha and GET /report match local computation")
    finally:
        server.shutdown()
        server.server_close()
        reset_state()

    print("\nDemo OK: sanity alphas, agreement, adjudication, golden "
          "export, leakage, check and serve verified.")


if __name__ == "__main__":
    main()
