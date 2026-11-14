"""Near-duplicate leakage check: golden set vs held-out pool.

A golden set only measures anything if the held-out pool it will be
compared against (tuning / practice / future eval items) does not
quietly contain copies of it. This module flags near-duplicates
between golden cases and held-out items with word n-gram Jaccard
similarity — deliberately simple and auditable:

  text -> lowercase alphanumeric tokens -> set of word n-grams
  (n = 3; texts shorter than n tokens fall back to one shingle
  holding the whole token tuple) -> Jaccard = |A n B| / |A u B|.

A pair at or above the threshold (default 0.5) is flagged. The
check reports pairs; it never silently drops anything — a human
decides whether a flagged held-out item is contamination or a
legitimately similar case.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

_TOKEN = re.compile(r"[a-z0-9]+")

DEFAULT_NGRAM = 3
DEFAULT_THRESHOLD = 0.5


def tokenize(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


def shingles(text: str, n: int = DEFAULT_NGRAM) -> frozenset:
    tokens = tokenize(text)
    if not tokens:
        return frozenset()
    if len(tokens) < n:
        return frozenset([tuple(tokens)])
    return frozenset(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def text_similarity(text_a: str, text_b: str, n: int = DEFAULT_NGRAM) -> float:
    return jaccard(shingles(text_a, n), shingles(text_b, n))


def case_text(case: Dict) -> str:
    """The text a case is compared on: prompt + response."""
    return f"{case.get('prompt', '')} {case.get('response', '')}".strip()


def find_leakage(golden_cases: Sequence[Dict], heldout_items: Sequence[Dict],
                 threshold: float = DEFAULT_THRESHOLD,
                 n: int = DEFAULT_NGRAM) -> List[Dict]:
    """All (golden, held-out) pairs with similarity >= threshold.

    Sorted by descending similarity, then ids, so the output is
    deterministic. Similarities are rounded to 6 decimals.
    """
    golden_shingles = [(c["case_id"], shingles(case_text(c), n))
                       for c in golden_cases]
    held_shingles = [(h["case_id"], shingles(case_text(h), n))
                     for h in heldout_items]
    flags: List[Dict] = []
    for gid, gs in golden_shingles:
        for hid, hs in held_shingles:
            sim = jaccard(gs, hs)
            if sim >= threshold:
                flags.append({
                    "golden_case_id": gid,
                    "heldout_case_id": hid,
                    "jaccard": round(sim, 6),
                })
    flags.sort(key=lambda f: (-f["jaccard"], f["golden_case_id"],
                              f["heldout_case_id"]))
    return flags


def internal_duplicates(cases: Sequence[Dict],
                        threshold: float = DEFAULT_THRESHOLD,
                        n: int = DEFAULT_NGRAM) -> List[Dict]:
    """Near-duplicate pairs WITHIN one set (e.g. inside the golden
    set itself, where a dupe would double-count one behaviour)."""
    shingled = [(c["case_id"], shingles(case_text(c), n)) for c in cases]
    flags: List[Dict] = []
    for i in range(len(shingled)):
        for j in range(i + 1, len(shingled)):
            sim = jaccard(shingled[i][1], shingled[j][1])
            if sim >= threshold:
                flags.append({
                    "case_id_a": shingled[i][0],
                    "case_id_b": shingled[j][0],
                    "jaccard": round(sim, 6),
                })
    flags.sort(key=lambda f: (-f["jaccard"], f["case_id_a"], f["case_id_b"]))
    return flags
