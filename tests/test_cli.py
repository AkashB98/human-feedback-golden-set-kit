"""CLI behaviour: check exit codes, alpha/export output, serve."""
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main as cli_main  # noqa: E402
from cli import make_server, reset_state  # noqa: E402
from generator import (  # noqa: E402
    generate_dataset, generate_heldout, generate_sanity, write_json,
)
from helpers import heldout_pool, main_dataset  # noqa: E402


def _run(argv):
    with redirect_stdout(io.StringIO()) as out, \
            redirect_stderr(io.StringIO()):
        code = cli_main(argv)
    return code, out.getvalue()


class _Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="golden-cli-")
        self.ratings = os.path.join(self.tmp, "ratings.json")
        self.bad_pool = os.path.join(self.tmp, "heldout.json")
        self.good_pool = os.path.join(self.tmp, "heldout_clean.json")
        self.chance = os.path.join(self.tmp, "chance.json")
        write_json(generate_dataset(), self.ratings)
        write_json(generate_heldout(), self.bad_pool)
        write_json(generate_heldout(clean=True), self.good_pool)
        write_json(generate_sanity("chance"), self.chance)


class TestCheck(_Files):
    def test_check_clean_pool_passes(self):
        code, _ = _run(["check", "--input", self.ratings,
                        "--heldout", self.good_pool])
        self.assertEqual(code, EXIT_OK)

    def test_check_planted_pool_fails_by_design(self):
        code, out = _run(["check", "--input", self.ratings,
                          "--heldout", self.bad_pool])
        self.assertEqual(code, EXIT_FAIL)
        self.assertIn("near-duplicate", out)

    def test_check_without_pool_passes(self):
        code, _ = _run(["check", "--input", self.ratings])
        self.assertEqual(code, EXIT_OK)

    def test_check_chance_dataset_fails(self):
        # Seeded random labels: alpha near 0 -> escalated, and the
        # disagreements carry no adjudicator -> incomplete.
        code, _ = _run(["check", "--input", self.chance])
        self.assertEqual(code, EXIT_FAIL)

    def test_check_missing_file_is_error(self):
        code, _ = _run(["check", "--input",
                        "/tmp/no-such-ratings-xyz.json"])
        self.assertEqual(code, EXIT_ERROR)


class TestCommands(_Files):
    def test_alpha_command_pinned(self):
        code, out = _run(["alpha", "--input", self.ratings])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["alpha_nominal"], 0.685802)
        self.assertEqual(payload["alpha_ordinal"], 0.895938)
        self.assertEqual(payload["n_cases"], 36)
        self.assertFalse(payload["escalated"])

    def test_adjudicate_command_counts(self):
        code, out = _run(["adjudicate", "--input", self.ratings])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["counts"],
                         {"AGREED": 25, "ADJUDICATED": 11, "INCOMPLETE": 0})
        self.assertEqual(len(payload["records"]), 36)

    def test_export_command_golden_count(self):
        code, out = _run(["export", "--input", self.ratings,
                          "--heldout", self.good_pool])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(len(payload["golden_set"]), 36)
        self.assertEqual(len(payload["audit_trail"]), 36)
        self.assertEqual(payload["leakage"], [])

    def test_leakage_command(self):
        code, out = _run(["leakage", "--input", self.ratings,
                          "--heldout", self.bad_pool])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(len(payload["leakage"]), 2)

    def test_generate_command_writes_dataset(self):
        out_path = os.path.join(self.tmp, "gen.json")
        code, _ = _run(["generate", "--out", out_path])
        self.assertEqual(code, EXIT_OK)
        with open(out_path, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(len(payload["cases"]), 36)


class TestServe(unittest.TestCase):
    def test_serve_round_trip(self):
        reset_state(main_dataset(), heldout_pool(clean=True))
        server = make_server(0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=10) as resp:
                self.assertEqual(json.loads(resp.read()),
                                 {"status": "ok"})
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/alpha", data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read())
            self.assertEqual(payload["alpha_nominal"], 0.685802)
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/report", timeout=10) as resp:
                report = json.loads(resp.read())
            self.assertEqual(len(report["golden_set"]), 36)
        finally:
            server.shutdown()
            server.server_close()
            reset_state()


if __name__ == "__main__":
    unittest.main()
