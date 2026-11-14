"""Krippendorff's alpha for HUMAN-vs-HUMAN agreement.

This module measures whether independent human raters agree with
EACH OTHER when they label the same agent responses. It is the
pre-judge stage of an evaluation pipeline: before any automated
judge exists, the human labels themselves have to be shown to be
reproducible, or the "gold" labels built on them are fiction.

That is deliberately a different question from the one answered by
the sibling repo ``llm-judge-calibration``, which measures a
machine judge against human grades (quadratic-weighted kappa and
calibration error). Here there is no judge and no kappa: only
humans, compared pairwise through Krippendorff's alpha, which
handles 3+ raters and missing ratings natively.

Definition (Krippendorff, 2004): alpha = 1 - Do / De, where Do is
the observed disagreement and De the disagreement expected by
chance given the marginal distribution of values. Both are built
from the coincidence matrix o_ck: for each unit, every ordered pair
of pairable values contributes to o_ck, normalised by (m_u - 1)
where m_u is the number of ratings on that unit. Units with fewer
than two ratings form no pairs and are excluded — that is how
missing ratings are handled: they shrink the evidence, they are
never imputed.

Metrics:
  nominal — disagreement is 0 for equal values, 1 otherwise.
  ordinal — disagreement is the squared Krippendorff ordinal
    distance, which uses the marginal counts: for values c < k,
    delta_ck = ( sum_{g=c..k} n_g - (n_c + n_k) / 2 ) ** 2.
    Near misses (1 vs 2) therefore cost less than far misses
    (1 vs 5), by an amount set by the data's own marginals.

Conventions:
  - If there are no pairable ratings at all, ValueError.
  - If De == 0 (every pairable value identical, so chance
    disagreement is impossible), alpha is defined as 1.0.
  - Alpha is NOT rounded here; callers round for display.
"""

from __future__ import annotations

from typing import Dict, Hashable, List, Optional, Sequence

NOMINAL = "nominal"
ORDINAL = "ordinal"
METRICS = (NOMINAL, ORDINAL)


def _domain_of(units: Sequence[Sequence[Optional[Hashable]]],
               domain: Optional[Sequence[Hashable]]) -> List[Hashable]:
    if domain is not None:
        return list(domain)
    seen = set()
    for unit in units:
        for v in unit:
            if v is not None:
                seen.add(v)
    try:
        return sorted(seen)
    except TypeError:
        return sorted(seen, key=repr)


def coincidence_matrix(units, domain=None):
    """Return (matrix, domain): o_ck as a list of lists of floats.

    ``units`` is a sequence of units; each unit is a sequence of
    ratings with None for a missing rating.
    """
    dom = _domain_of(units, domain)
    idx = {v: i for i, v in enumerate(dom)}
    k = len(dom)
    o = [[0.0] * k for _ in range(k)]
    for unit in units:
        vals = [v for v in unit if v is not None]
        m = len(vals)
        if m < 2:
            continue
        counts = [0] * k
        for v in vals:
            if v not in idx:
                raise ValueError(f"value {v!r} not in domain {dom!r}")
            counts[idx[v]] += 1
        for c in range(k):
            if counts[c] == 0:
                continue
            for j in range(k):
                if counts[j] == 0:
                    continue
                if c == j:
                    o[c][j] += counts[c] * (counts[c] - 1) / (m - 1)
                else:
                    o[c][j] += counts[c] * counts[j] / (m - 1)
    return o, dom


def _delta_matrix(marginals: List[float], metric: str) -> List[List[float]]:
    k = len(marginals)
    d = [[0.0] * k for _ in range(k)]
    for c in range(k):
        for j in range(k):
            if c == j:
                continue
            if metric == NOMINAL:
                d[c][j] = 1.0
            else:  # ORDINAL: c and j are rank positions in the domain
                lo, hi = (c, j) if c < j else (j, c)
                span = sum(marginals[lo:hi + 1])
                d[c][j] = (span - (marginals[c] + marginals[j]) / 2.0) ** 2
    return d


def alpha_components(units, metric: str = NOMINAL, domain=None) -> Dict:
    """Full alpha computation with every intermediate exposed.

    Returns a dict with the coincidence matrix, marginals, total
    pairable values n, observed disagreement Do, expected
    disagreement De (both as unnormalised sums over the coincidence
    / expectation matrices — their ratio is what matters), and
    alpha itself.
    """
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; expected one of {METRICS}")
    o, dom = coincidence_matrix(units, domain)
    marginals = [sum(row) for row in o]
    n = sum(marginals)
    if n == 0:
        raise ValueError("no pairable ratings: every unit has < 2 ratings")
    k = len(dom)
    # Expected coincidences under chance, same total mass n.
    e = [[0.0] * k for _ in range(k)]
    for c in range(k):
        for j in range(k):
            if c == j:
                e[c][j] = marginals[c] * (marginals[c] - 1) / (n - 1) if n > 1 else 0.0
            else:
                e[c][j] = marginals[c] * marginals[j] / (n - 1) if n > 1 else 0.0
    delta = _delta_matrix(marginals, metric)
    do = sum(o[c][j] * delta[c][j] for c in range(k) for j in range(k))
    de = sum(e[c][j] * delta[c][j] for c in range(k) for j in range(k))
    alpha = 1.0 if de == 0 else 1.0 - do / de
    return {
        "metric": metric,
        "domain": dom,
        "coincidence": o,
        "marginals": marginals,
        "n_pairable_values": int(round(n)),
        "observed_disagreement": do,
        "expected_disagreement": de,
        "alpha": alpha,
    }


def krippendorff_alpha(units, metric: str = NOMINAL, domain=None) -> float:
    """Krippendorff's alpha for ``units`` under ``metric``."""
    return alpha_components(units, metric=metric, domain=domain)["alpha"]


def units_from_cases(cases, field: str) -> List[List]:
    """Extract per-case rating lists from dataset case dicts.

    ``field`` is "nominal" or "ordinal"; each case stores ratings as
    a {rater: value-or-None} mapping. Rater order is the sorted
    rater ids, so the extraction is deterministic.
    """
    units = []
    for case in cases:
        ratings = case[field]
        units.append([ratings[r] for r in sorted(ratings)])
    return units
