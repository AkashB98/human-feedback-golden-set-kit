"""Deterministic synthetic rating datasets.

SYNTHETIC DATA ONLY. Every prompt, response, rater and label here
is fabricated by a seeded generator about a fictional support
product (Lumen Desk) and its fictional support agent. No real
person, customer, or company appears anywhere.

The main dataset plants the patterns a golden-set pipeline exists
to survive:

  * clear cases most raters agree on;
  * borderline cases (planted quality 3) where honest raters split;
  * two archetypes with planted rater-behaviour splits — a tone
    case only the strict rater fails, and a missed-instruction
    case only the lenient rater passes;
  * a lenient rater (R3) and a strict rater (R4) whose ordinal
    scores drift in opposite directions on mid-quality work;
  * missing ratings: a seeded ~7% scatter plus a planted block
    (R4 absent for three consecutive cases).

Disagreed cases get a planted adjudicator decision (final label +
rationale) attached by the generator, so the adjudication stage
always has the senior reviewer's call to record — the kit's job is
the record and the audit trail, not simulating the reviewer.

Two sanity datasets ship alongside: perfect agreement (alpha must
be exactly 1) and seeded chance-level labels (alpha near 0).
"""

from __future__ import annotations

import json
import random
from typing import Dict, List, Optional

RATERS = ["R1", "R2", "R3", "R4"]
DEFAULT_SEED = 42

_NAMES = ["Maya", "Jonas", "Priya", "Tomas", "Elena", "Marcus",
          "Ingrid", "Diego", "Sofia", "Henrik", "Amara", "Felix"]
_PRODUCTS = ["Lumen Desk Pro", "Lumen Desk Teams", "Lumen Desk Lite",
             "Lumen Desk Mobile"]

# Each archetype: prompt/response templates with {name} {ref}
# {product} {amount} {days} slots, the planted failure class, the
# planted true quality (1-5) and the planted true nominal label.
_ARCHETYPES = [
    {
        "failure_class": "none", "quality": 5, "nominal": "pass",
        "pattern": "clear",
        "prompt": "Hi, I am {name}. My refund for {product} was approved "
                  "last week, ticket {ref}. When will the money arrive?",
        "response": "Hello {name}, your refund of {amount} for {product} "
                    "was approved and sent to your original payment method "
                    "on Monday. Banks usually post it within {days} business "
                    "days, so it should appear by Friday at the latest. Your "
                    "ticket {ref} stays open until you confirm receipt.",
    },
    {
        "failure_class": "factual_error", "quality": 2, "nominal": "fail",
        "pattern": "clear",
        "prompt": "Hello, I am {name}. Ticket {ref}: how much was my "
                  "refund for {product}?",
        "response": "Hi {name}, I can confirm your refund for {product} "
                    "was {amount} plus a goodwill credit, so the total "
                    "return is double that amount. It was processed "
                    "instantly and cannot be delayed by your bank.",
    },
    {
        "failure_class": "none", "quality": "4", "nominal": "pass",
        "pattern": "clear",
        "prompt": "I am {name} and I forgot my password for {product}. "
                  "Ticket {ref}. How do I get back in?",
        "response": "No problem, {name}. Open {product}, choose Forgot "
                    "password on the sign-in screen, and we will email a "
                    "reset link that stays valid for one hour. After the "
                    "reset, sign in again and re-enable two-factor "
                    "authentication under Settings, Security. Ticket {ref} "
                    "covers this request if the link expires.",
    },
    {
        "failure_class": "incomplete", "quality": 2, "nominal": "fail",
        "pattern": "clear",
        "prompt": "I am {name}, ticket {ref}. I cannot reset my password "
                  "for {product}; the email never arrives.",
        "response": "Hi {name}, please use the Forgot password link on "
                    "the sign-in page of {product}. A reset email will be "
                    "sent to your address. Let us know if anything else "
                    "comes up.",
    },
    {
        "failure_class": "none", "quality": 5, "nominal": "pass",
        "pattern": "clear",
        "prompt": "Hi, {name} here, ticket {ref}. Why did my {product} "
                  "invoice go up this month?",
        "response": "Hello {name}, your {product} invoice rose because "
                    "the annual plan discount from last year ended in "
                    "March, so this month bills at the standard rate of "
                    "{amount}. Nothing else on the invoice changed, and "
                    "ticket {ref} includes a line-by-line copy for your "
                    "records.",
    },
    {
        "failure_class": "none", "quality": 4, "nominal": "pass",
        "pattern": "clear",
        "prompt": "Hi, {name}, ticket {ref}. My {product} order shipped "
                  "late. Where is it now?",
        "response": "Hello {name}, sorry for the delay. Your {product} "
                    "parcel left our depot yesterday and the carrier "
                    "expects delivery within {days} business days. The "
                    "tracking page under ticket {ref} updates each "
                    "evening, and we will message you if the date slips.",
    },
    {
        "failure_class": "tone_mismatch", "quality": 3, "nominal": "pass",
        "pattern": "tone_split",
        "prompt": "I am {name}. Ticket {ref}: my export from {product} "
                  "failed twice today and I am frustrated.",
        "response": "Exports fail when the date range covers more than "
                    "ninety days. Narrow the range and run it again. "
                    "Ticket {ref} noted.",
    },
    {
        "failure_class": "factual_error", "quality": 2, "nominal": "fail",
        "pattern": "clear",
        "prompt": "Hello, {name} here. Ticket {ref}: when does my "
                  "{product} trial end?",
        "response": "Hi {name}, your {product} trial never expires, so "
                    "you can keep using every feature free of charge "
                    "forever. There is no need to add a payment method "
                    "at any point.",
    },
    {
        "failure_class": "none", "quality": 4, "nominal": "pass",
        "pattern": "clear",
        "prompt": "Hi, I am {name}, ticket {ref}. I moved house last "
                  "month; please update the billing address for "
                  "{product}.",
        "response": "Hello {name}, I have updated the billing address "
                    "on your {product} account, and the change applies "
                    "from the next invoice onward. A confirmation email "
                    "is on its way, and ticket {ref} records the old "
                    "address as replaced rather than copied.",
    },
    {
        "failure_class": "missed_instruction", "quality": 3, "nominal": "fail",
        "pattern": "leniency_split",
        "prompt": "I am {name}, ticket {ref}. Please cancel my {product} "
                  "renewal AND export all my data before it closes.",
        "response": "Hello {name}, your {product} renewal is cancelled "
                    "and will not bill again. A confirmation email is on "
                    "its way, and ticket {ref} is now closed. Thank you "
                    "for using {product}.",
    },
]

_RATIONALES = {
    "none": "Adjudicator confirmed the response against the rubric: the "
            "labels that disagreed were scoring style, not substance; "
            "the response meets every rubric point.",
    "factual_error": "Adjudicator checked the response against account "
                     "facts: it states something untrue, so the fail "
                     "stands regardless of tone or fluency.",
    "incomplete": "Adjudicator compared the response with the customer's "
                  "actual problem: a required diagnostic step is missing, "
                  "so the fail stands.",
    "tone_mismatch": "Adjudicator ruled the content correct but the tone "
                      "below the empathy bar for a frustrated customer; "
                      "recorded as a pass on task completion with the "
                      "quality score carrying the tone penalty.",
    "missed_instruction": "Adjudicator re-read the original request: one "
                          "of the two explicit instructions was never "
                          "done, so the fail stands even though the reply "
                          "reads fluently.",
}


def _slots(i: int) -> Dict[str, str]:
    return {
        "name": _NAMES[i % len(_NAMES)],
        "ref": f"LD-{4100 + i * 7}",
        "product": _PRODUCTS[(i // 3) % len(_PRODUCTS)],
        "amount": f"${18 + (i * 13) % 90}.00",
        "days": str(2 + i % 4),
    }


# Per-case detail sentences. Templated archetypes alone would make
# every variant of an archetype a near-duplicate of its siblings
# (measured Jaccard 0.51-0.63 between distinct cases — the leakage
# check would flag the dataset against itself). Each case therefore
# carries one customer-detail sentence and one agent-note sentence
# assembled from fragment slots with coprime strides, so distinct
# cases share the archetype's substance but not its surface.
_WHEN = ["last Tuesday", "two days ago", "on Monday morning",
         "right after the latest update", "when my plan renewed",
         "during a work trip", "just after the holidays",
         "late last week"]
_ACTION = ["changed my contact email", "updated the mobile app",
           "moved to a new office", "added two teammates",
           "switched my payment card", "returned from leave",
           "merged two projects", "enabled single sign-on"]
_PREF = ["prefer updates by email rather than in the app",
         "mostly use the mobile app during the day",
         "share this account with two colleagues",
         "keep a paper trail for every change",
         "are on the annual billing cycle",
         "recently switched from a competitor",
         "need exports for a monthly audit",
         "work across two time zones"]
_PREF2 = ["check the account every morning",
          "forward summaries to a shared inbox",
          "keep two admins on the account",
          "review invoices before paying them",
          "use keyboard shortcuts heavily",
          "archive anything older than a year",
          "escalate anything urgent by phone",
          "test new features before rolling them out"]


def _details(i: int):
    when = _WHEN[i % len(_WHEN)]
    action = _ACTION[(i * 3 + 1) % len(_ACTION)]
    pref = _PREF[(i * 5 + 2) % len(_PREF)]
    pref2 = _PREF2[(i * 7 + 3) % len(_PREF2)]
    prompt_detail = f" This started {when}, shortly after I {action}."
    response_detail = f" I have also noted that you {pref} and {pref2}."
    return prompt_detail, response_detail


def _perceived(rng: random.Random, rater: str, quality: int) -> int:
    """One rater's perceived quality: truth + planted rater drift."""
    draw = rng.random()
    if rater == "R3" and quality in (2, 3):       # lenient on weak work
        delta = 1 if draw < 0.45 else 0
    elif rater == "R4" and quality in (3, 4):     # strict on mid work
        delta = -1 if draw < 0.35 else 0
    elif draw < 0.03:
        delta = -1
    elif draw < 0.06:
        delta = 1
    else:
        delta = 0
    return max(1, min(5, quality + delta))


def _nominal_label(rng: random.Random, rater: str, arch: Dict,
                   true_nominal: str) -> str:
    """One rater's pass/fail: a TASK-success judgment, modelled
    separately from the ordinal quality score — a fluent response
    that missed an instruction is quality 3 but still a fail, and
    raters mostly see that. Deviations are the planted behaviours:
    R4 fails tone alone (his strictness otherwise lives in the
    ordinal scores), R3 passes the missed-instruction case and is
    occasionally lenient on other fails, and the two unremarkable
    raters flip rarely."""
    if arch["pattern"] == "tone_split" and rater == "R4":
        return "fail"           # strict rater fails tone alone
    if arch["pattern"] == "leniency_split" and rater == "R3":
        return "pass"           # lenient rater misses the missed step
    draw = rng.random()
    if rater == "R3" and true_nominal == "fail":
        return "pass" if draw < 0.12 else "fail"
    if rater in ("R1", "R2") and draw < 0.02:
        return "fail" if true_nominal == "pass" else "pass"
    return true_nominal


def _rate_case(rng: random.Random, arch: Dict, quality: int,
               true_nominal: str):
    nominal: Dict[str, Optional[str]] = {}
    ordinal: Dict[str, Optional[int]] = {}
    for rater in RATERS:
        ordinal[rater] = _perceived(rng, rater, quality)
        nominal[rater] = _nominal_label(rng, rater, arch, true_nominal)
    return nominal, ordinal


def _is_disagreed(nominal: Dict, ordinal: Dict) -> bool:
    labels = [v for v in nominal.values() if v is not None]
    scores = [v for v in ordinal.values() if v is not None]
    if len(set(labels)) > 1:
        return True
    return bool(scores) and (max(scores) - min(scores)) >= 2


def generate_dataset(seed: int = DEFAULT_SEED, n_cases: int = 36) -> Dict:
    rng = random.Random(seed)
    cases: List[Dict] = []
    for i in range(n_cases):
        arch = _ARCHETYPES[i % len(_ARCHETYPES)]
        quality = int(arch["quality"])
        slots = _slots(i)
        nominal, ordinal = _rate_case(rng, arch, quality, arch["nominal"])
        # Missing ratings: seeded scatter, then a planted R4 block.
        for rater in RATERS:
            if rng.random() < 0.07:
                nominal[rater] = None
                ordinal[rater] = None
        if i in (28, 29, 30):
            nominal["R4"] = None
            ordinal["R4"] = None
        # Keep every case pairable: at least two raters present.
        present = [r for r in RATERS if nominal[r] is not None]
        if len(present) < 2:
            nominal["R1"] = "pass" if quality >= 3 else "fail"
            ordinal["R1"] = quality
            nominal["R2"] = nominal["R1"]
            ordinal["R2"] = quality
        adjudicator = None
        if _is_disagreed(nominal, ordinal):
            adjudicator = {
                "label": arch["nominal"],
                "quality": quality,
                "rationale": _RATIONALES[arch["failure_class"]],
                "adjudicator": "senior-reviewer-1",
            }
        prompt_detail, response_detail = _details(i)
        cases.append({
            "case_id": f"C{i + 1:03d}",
            "prompt": arch["prompt"].format(**slots) + prompt_detail,
            "response": arch["response"].format(**slots) + response_detail,
            "failure_class": arch["failure_class"],
            "pattern": arch["pattern"],
            "planted_truth": {"nominal": arch["nominal"], "quality": quality},
            "nominal": nominal,
            "ordinal": ordinal,
            "adjudicator": adjudicator,
        })
    return {
        "dataset_id": f"synthetic-ratings-seed{seed}",
        "seed": seed,
        "description": "Synthetic human ratings of fictional Lumen Desk "
                       "support-agent responses (fictional data only).",
        "raters": list(RATERS),
        "cases": cases,
    }


def generate_heldout(seed: int = DEFAULT_SEED, clean: bool = False) -> Dict:
    """Held-out pool: fresh items, plus (unless clean) two planted
    near-duplicates of golden cases C003 and C012 — same text with a
    name and a ticket ref changed, the classic quiet contamination."""
    items: List[Dict] = []
    topics = [
        ("Hi, I am {name}. Ticket {ref}: can I pause my {product} plan "
         "for two months instead of cancelling?",
         "Hello {name}, yes — {product} plans can pause for up to three "
         "months from the billing page, and your data stays intact. The "
         "pause under ticket {ref} starts at the next cycle."),
        ("I am {name}, ticket {ref}. The {product} app logs me out every "
         "morning. Is that a known problem?",
         "Hi {name}, that logout loop was a session bug in last week's "
         "{product} release and a fix shipped yesterday. Update the app "
         "and ticket {ref} should stay resolved."),
        ("Hello, {name} here, ticket {ref}. I need the {product} invoice "
         "sent to our finance address instead of mine.",
         "Certainly, {name}. I have added the finance address to your "
         "{product} billing profile, so future invoices go there "
         "directly. Ticket {ref} confirms the change."),
        ("I am {name}. Ticket {ref}: does {product} work offline on a "
         "plane?",
         "Hi {name}, {product} keeps a local copy of your recent boards "
         "for offline viewing, and edits sync when you reconnect. Full "
         "search needs a connection, as ticket {ref} explains."),
        ("Hi, {name}, ticket {ref}. Two of my {product} seats are unused. "
         "Can I drop them mid-cycle?",
         "Hello {name}, unused {product} seats can be removed at any "
         "time; the credit of {amount} applies to your next invoice "
         "automatically. Ticket {ref} lists the seats removed."),
        ("I am {name}, ticket {ref}. My {product} notification emails go "
         "to spam since Tuesday.",
         "Hi {name}, our sending domain changed on Tuesday, which can "
         "trip strict spam filters. Allowlisting the new domain fixes "
         "it; ticket {ref} has the exact address to allow."),
        ("Hello, I am {name}. Ticket {ref}: I exported {product} data "
         "but the file is empty.",
         "Hello {name}, an empty export usually means the date filter "
         "excluded every row. Clear the filter and export again; ticket "
         "{ref} stays open until the file downloads correctly."),
        ("I am {name}, ticket {ref}. Can {product} import contacts from "
         "a spreadsheet?",
         "Yes, {name} — {product} imports spreadsheets with name and "
         "email columns, and it flags duplicate rows before saving. "
         "Ticket {ref} links the import guide."),
    ]
    for j, (prompt_t, resp_t) in enumerate(topics):
        slots = _slots(50 + j)
        prompt_detail, response_detail = _details(100 + j)
        items.append({
            "case_id": f"H{j + 1:03d}",
            "prompt": prompt_t.format(**slots) + prompt_detail,
            "response": resp_t.format(**slots) + response_detail,
            "origin": "fresh",
        })
    if not clean:
        main = generate_dataset(seed=seed)
        for k, src_id in enumerate(("C003", "C012")):
            src = next(c for c in main["cases"] if c["case_id"] == src_id)
            src_slots = _slots(int(src_id[1:]) - 1)
            # Fresh name/ref outside the variant slot cycles, so the
            # dupe resembles its source only — never a sibling variant.
            new_slots = {"name": ("Kavya", "Rohan")[k],
                         "ref": f"LD-900{k + 1}"}
            # Near-duplicate: the source text verbatim with only the
            # customer name and ticket ref swapped — the same response
            # quietly re-entering the pool under a new ticket.
            prompt = src["prompt"].replace(src_slots["name"],
                                            new_slots["name"])
            prompt = prompt.replace(src_slots["ref"], new_slots["ref"])
            response = src["response"].replace(src_slots["name"],
                                               new_slots["name"])
            response = response.replace(src_slots["ref"], new_slots["ref"])
            items.append({
                "case_id": f"H{len(items) + 1:03d}",
                "prompt": prompt,
                "response": response,
                "origin": f"near_duplicate_of:{src_id}",
            })
    return {
        "pool_id": f"synthetic-heldout-seed{seed}" + ("-clean" if clean else ""),
        "seed": seed,
        "items": items,
    }


def generate_sanity(kind: str, seed: int = DEFAULT_SEED) -> Dict:
    """Sanity datasets: 'perfect' (alpha exactly 1) or 'chance'
    (seeded random labels, alpha near 0)."""
    rng = random.Random(seed + (7 if kind == "perfect" else 13))
    cases: List[Dict] = []
    n = 12 if kind == "perfect" else 40
    for i in range(n):
        if kind == "perfect":
            label = "pass" if i % 2 == 0 else "fail"
            score = 5 if label == "pass" else 1
            nominal = {r: label for r in RATERS}
            ordinal = {r: score for r in RATERS}
        else:
            nominal = {r: rng.choice(["pass", "fail"]) for r in RATERS}
            ordinal = {r: rng.randint(1, 5) for r in RATERS}
        cases.append({
            "case_id": f"S{i + 1:03d}",
            "prompt": f"Sanity probe item {i + 1} for the {kind} set.",
            "response": f"Synthetic sanity response {i + 1} ({kind}).",
            "failure_class": "sanity",
            "pattern": kind,
            "planted_truth": None,
            "nominal": nominal,
            "ordinal": ordinal,
            "adjudicator": None,
        })
    return {
        "dataset_id": f"synthetic-sanity-{kind}-seed{seed}",
        "seed": seed,
        "description": f"Synthetic {kind}-agreement sanity dataset.",
        "raters": list(RATERS),
        "cases": cases,
    }


def dataset_to_json(dataset: Dict) -> str:
    return json.dumps(dataset, sort_keys=True, indent=2) + "\n"


def write_json(payload: Dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dataset_to_json(payload))


def load_json(path: str) -> Dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data
