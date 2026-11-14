"""No-network enforcement: with sockets blocked, generating,
scoring agreement, adjudicating, exporting and leakage-checking
must all still work. (``serve`` is the only intentional exception —
it binds loopback on demand, and is not used here.)"""
import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Blocker:
    def __init__(self, *a, **k):
        raise RuntimeError("network access blocked in hermetic test")


class TestNoNetwork(unittest.TestCase):
    def setUp(self):
        self._real_socket = socket.socket
        socket.socket = _Blocker
        import urllib.request as urlreq
        self._real_urlopen = urlreq.urlopen
        urlreq.urlopen = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("network access blocked in hermetic test"))

    def tearDown(self):
        socket.socket = self._real_socket
        import urllib.request as urlreq
        urlreq.urlopen = self._real_urlopen

    def test_full_pipeline_offline(self):
        from adjudication import adjudicate_dataset
        from generator import generate_dataset, generate_heldout
        from golden import build_export
        ds = generate_dataset()
        report = adjudicate_dataset(ds)
        self.assertEqual(report["counts"]["INCOMPLETE"], 0)
        export = build_export(ds, generate_heldout())
        self.assertEqual(len(export["leakage"]), 2)
        clean = build_export(ds, generate_heldout(clean=True))
        self.assertEqual(clean["leakage"], [])

    def test_no_module_opens_sockets_at_import(self):
        for mod in ("agreement", "adjudication", "leakage", "generator",
                    "golden", "cli", "demo"):
            sys.modules.pop(mod, None)
        import adjudication, agreement, cli, demo  # noqa: F401
        import generator, golden, leakage  # noqa: F401
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
