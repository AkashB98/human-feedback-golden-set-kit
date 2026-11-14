"""CLI: generate | alpha | adjudicate | export | leakage | report
| check | demo | serve.

SYNTHETIC DATA ONLY — every dataset handled here is fabricated
sample data about a fictional product (Lumen Desk).

Exit codes:
  check : 0 = pass (adjudication complete, alpha at/above floor,
          no leakage flags when a held-out pool is given),
          1 = FAIL (incomplete adjudication, escalated run, or
          leakage — EXPECTED with the seeded held-out pool, by
          design: it plants two near-duplicates of golden cases),
          2 = usage / IO / data error
  others: 0 = success, 2 = usage / IO error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adjudication import adjudicate_dataset  # noqa: E402
from generator import (  # noqa: E402
    generate_dataset, generate_heldout, generate_sanity, load_json,
    write_json,
)
from golden import build_export  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True)


def _load_or_error(path: str) -> Optional[Dict]:
    try:
        return load_json(path)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
    except (ValueError, OSError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
    return None


def _write_out(args, text: str, summary: str) -> int:
    if getattr(args, "out", None):
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(summary)
    else:
        print(text, end="")
    return EXIT_OK


def cmd_generate(args) -> int:
    if args.what == "ratings":
        payload = generate_dataset(seed=args.seed)
        kind = "ratings dataset"
    elif args.what == "heldout":
        payload = generate_heldout(seed=args.seed, clean=args.clean)
        kind = "clean held-out pool" if args.clean else \
            "held-out pool (2 planted near-duplicates)"
    else:
        payload = generate_sanity(args.what, seed=args.seed)
        kind = f"{args.what} sanity dataset"
    if args.out:
        try:
            write_json(payload, args.out)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        n = len(payload.get("cases", payload.get("items", [])))
        print(f"generated synthetic {kind} ({n} items, seed={args.seed}) "
              f"-> {args.out}")
        return EXIT_OK
    from generator import dataset_to_json
    print(dataset_to_json(payload), end="")
    return EXIT_OK


def _alpha_payload(dataset: Dict) -> Dict:
    report = adjudicate_dataset(dataset)
    return {
        "dataset_id": dataset["dataset_id"],
        "n_cases": len(dataset["cases"]),
        "alpha_nominal": report["alpha_nominal"],
        "alpha_ordinal": report["alpha_ordinal"],
        "alpha_floor": report["alpha_floor"],
        "escalated": report["escalated"],
    }


def cmd_alpha(args) -> int:
    dataset = _load_or_error(args.input)
    if dataset is None:
        return EXIT_ERROR
    try:
        payload = _alpha_payload(dataset)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return _write_out(args, canonical(payload) + "\n", f"alpha -> {args.out}")


def cmd_adjudicate(args) -> int:
    dataset = _load_or_error(args.input)
    if dataset is None:
        return EXIT_ERROR
    try:
        payload = adjudicate_dataset(dataset)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return _write_out(args, canonical(payload) + "\n",
                      f"adjudicate -> {args.out}")


def _export_or_error(args) -> Optional[Dict]:
    dataset = _load_or_error(args.input)
    if dataset is None:
        return None
    heldout = None
    if getattr(args, "heldout", None):
        heldout = _load_or_error(args.heldout)
        if heldout is None:
            return None
    try:
        return build_export(dataset, heldout)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def cmd_export(args) -> int:
    export = _export_or_error(args)
    if export is None:
        return EXIT_ERROR
    return _write_out(args, canonical(export) + "\n", f"export -> {args.out}")


def cmd_leakage(args) -> int:
    export = _export_or_error(args)
    if export is None:
        return EXIT_ERROR
    payload = {"leakage": export["leakage"],
               "internal_duplicates": export["internal_duplicates"]}
    return _write_out(args, canonical(payload) + "\n",
                      f"leakage -> {args.out}")


def cmd_report(args) -> int:
    return cmd_export(args)


def check_failures(export: Dict) -> list:
    failures = []
    if export["incomplete_case_ids"]:
        failures.append(
            f"{len(export['incomplete_case_ids'])} case(s) lack a final "
            f"label: {', '.join(export['incomplete_case_ids'])}")
    if export["escalated"]:
        failures.append(
            f"nominal alpha {export['alpha_nominal']} below floor "
            f"{export['alpha_floor']} — run escalated, thin agreements "
            f"require adjudication")
    if export["internal_duplicates"]:
        failures.append(
            f"{len(export['internal_duplicates'])} near-duplicate pair(s) "
            f"inside the golden set")
    if export["leakage"]:
        failures.append(
            f"{len(export['leakage'])} near-duplicate pair(s) between the "
            f"golden set and the held-out pool")
    return failures


def cmd_check(args) -> int:
    export = _export_or_error(args)
    if export is None:
        return EXIT_ERROR
    failures = check_failures(export)
    if not failures:
        print(f"check PASS: alpha nominal {export['alpha_nominal']} / "
              f"ordinal {export['alpha_ordinal']}, adjudication complete "
              f"({export['counts']}), no leakage")
        return EXIT_OK
    for failure in failures:
        print(f"check: {failure}")
    print(f"check FAIL: {len(failures)} problem(s) — see above")
    return EXIT_FAIL


def cmd_demo(args) -> int:
    import demo as demo_mod
    try:
        demo_mod.main()
    except AssertionError as exc:
        print(f"demo FAILED: {exc}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


# ------------------------------------------------------------------- serve

class _State:
    def __init__(self):
        self.dataset: Dict = generate_dataset()
        self.heldout: Dict = generate_heldout(clean=True)


_STATE = _State()


def get_state() -> _State:
    return _STATE


def reset_state(dataset: Optional[Dict] = None,
                heldout: Optional[Dict] = None) -> None:
    _STATE.dataset = dataset if dataset is not None else generate_dataset()
    _STATE.heldout = heldout if heldout is not None else generate_heldout(clean=True)


class _Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: Any) -> None:
        body = (canonical(payload) + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw) if raw.strip() else {}
        if not isinstance(body, dict):
            raise ValueError("expected a JSON object")
        return body

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._send_json(200, {"status": "ok"})
        if self.path == "/report":
            return self._send_json(
                200, build_export(_STATE.dataset, _STATE.heldout))
        return self._send_json(404, {"error": "unknown endpoint"})

    def do_POST(self):  # noqa: N802
        try:
            body = self._body()
            dataset = body.get("dataset", _STATE.dataset)
            heldout = body.get("heldout", _STATE.heldout)
            if self.path == "/alpha":
                return self._send_json(200, _alpha_payload(dataset))
            if self.path == "/adjudicate":
                return self._send_json(200, adjudicate_dataset(dataset))
            if self.path == "/report":
                return self._send_json(200, build_export(dataset, heldout))
            return self._send_json(404, {"error": "unknown endpoint"})
        except (ValueError, TypeError, KeyError) as exc:
            return self._send_json(400, {"error": f"bad request: {exc}"})

    def log_message(self, *a: Any) -> None:
        pass


def make_server(port: int) -> HTTPServer:
    return HTTPServer(("127.0.0.1", port), _Handler)


def cmd_serve(args) -> int:
    if args.input:
        dataset = _load_or_error(args.input)
        if dataset is None:
            return EXIT_ERROR
        reset_state(dataset)
    server = make_server(args.port)
    print(f"serving on http://127.0.0.1:{args.port}  "
          f"(POST /alpha, /adjudicate, /report; GET /report, /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="human-feedback-golden-set-kit",
        description="Human-feedback golden set kit: Krippendorff alpha "
                    "(human-vs-human), adjudication records, golden-case "
                    "export, near-duplicate leakage check (synthetic "
                    "Lumen Desk sample data).")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate a synthetic dataset/pool")
    g.add_argument("--what", choices=["ratings", "heldout", "perfect",
                                      "chance"], default="ratings")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--clean", action="store_true",
                   help="heldout only: omit the planted near-duplicates")
    g.add_argument("--out", default=None)
    g.set_defaults(func=cmd_generate)

    for name, fn, helptext in (
            ("alpha", cmd_alpha, "Krippendorff alpha (nominal + ordinal)"),
            ("adjudicate", cmd_adjudicate, "adjudication report + records"),
            ("export", cmd_export, "golden set + audit trail + leakage"),
            ("report", cmd_report, "same bundle as export")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--input", required=True)
        s.add_argument("--heldout", default=None)
        s.add_argument("--out", default=None)
        s.set_defaults(func=fn)

    lk = sub.add_parser("leakage", help="leakage check only")
    lk.add_argument("--input", required=True)
    lk.add_argument("--heldout", required=True)
    lk.add_argument("--out", default=None)
    lk.set_defaults(func=cmd_leakage)

    c = sub.add_parser("check", help="CI gate: exit 0 pass / 1 fail / 2 error")
    c.add_argument("--input", required=True)
    c.add_argument("--heldout", default=None)
    c.set_defaults(func=cmd_check)

    sub.add_parser("demo", help="run the end-to-end demo").set_defaults(func=cmd_demo)

    s = sub.add_parser("serve", help="localhost JSON API")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--input", default=None)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
