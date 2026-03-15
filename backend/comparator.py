"""Contract comparison utilities.

This module provides a deterministic clause comparison that can run without an
LLM dependency. It scores each contract on common risk and fairness dimensions
and returns a structured side-by-side summary.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List


@dataclass(frozen=True)
class CompareDimension:
    key: str
    label: str
    positive_terms: List[str]
    negative_terms: List[str]
    weight: int


DIMENSIONS: List[CompareDimension] = [
    CompareDimension(
        key="liability",
        label="Liability Terms",
        positive_terms=[
            "limited liability",
            "liability cap",
            "cap on liability",
            "maximum liability",
        ],
        negative_terms=[
            "unlimited liability",
            "without limitation",
            "all damages",
            "indemnify for all losses",
        ],
        weight=3,
    ),
    CompareDimension(
        key="termination",
        label="Termination Flexibility",
        positive_terms=[
            "terminate with notice",
            "termination for convenience",
            "written notice",
            "right to terminate",
        ],
        negative_terms=[
            "early termination fee",
            "termination penalty",
            "liquidated damages",
            "cancellation charge",
        ],
        weight=3,
    ),
    CompareDimension(
        key="payment",
        label="Payment Clarity",
        positive_terms=[
            "payment schedule",
            "net 30",
            "invoice due",
            "paid within",
            "monthly payment",
        ],
        negative_terms=[
            "sole discretion",
            "subject to approval",
            "delayed payment",
            "as determined by",
        ],
        weight=2,
    ),
    CompareDimension(
        key="renewal",
        label="Renewal Control",
        positive_terms=[
            "renewal requires consent",
            "opt-in renewal",
            "written renewal",
        ],
        negative_terms=[
            "auto renewal",
            "automatically renew",
            "renews automatically",
        ],
        weight=2,
    ),
    CompareDimension(
        key="dispute_resolution",
        label="Dispute Resolution Fairness",
        positive_terms=[
            "mutual arbitration",
            "mutual jurisdiction",
            "good faith negotiation",
        ],
        negative_terms=[
            "exclusive jurisdiction",
            "waive right to",
            "non-appealable",
        ],
        weight=1,
    ),
]


def _split_clauses(text: str) -> List[str]:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if not collapsed:
        return []
    parts = re.split(r"(?<=[\.;:!?])\s+", collapsed)
    return [part.strip() for part in parts if len(part.strip()) >= 20]


def _find_first_match(clauses: List[str], terms: List[str]) -> str:
    for clause in clauses:
        hay = clause.lower()
        if any(term in hay for term in terms):
            return clause
    return ""


def _score_dimension(clauses: List[str], dimension: CompareDimension) -> Dict[str, object]:
    positive_hit = _find_first_match(clauses, dimension.positive_terms)
    negative_hit = _find_first_match(clauses, dimension.negative_terms)

    if positive_hit and not negative_hit:
        score = dimension.weight
        verdict = "favorable"
    elif negative_hit and not positive_hit:
        score = -dimension.weight
        verdict = "unfavorable"
    elif positive_hit and negative_hit:
        score = 0
        verdict = "mixed"
    else:
        score = 0
        verdict = "not_found"

    return {
        "key": dimension.key,
        "label": dimension.label,
        "score": score,
        "verdict": verdict,
        "positive_evidence": positive_hit,
        "negative_evidence": negative_hit,
    }


def _compare_dimension(
    dim_a: Dict[str, object],
    dim_b: Dict[str, object],
) -> Dict[str, object]:
    score_a = int(dim_a["score"])
    score_b = int(dim_b["score"])

    if score_a > score_b:
        better = "A"
    elif score_b > score_a:
        better = "B"
    else:
        better = "Tie"

    return {
        "key": dim_a["key"],
        "label": dim_a["label"],
        "contract_a_score": score_a,
        "contract_b_score": score_b,
        "better_contract": better,
        "contract_a_verdict": dim_a["verdict"],
        "contract_b_verdict": dim_b["verdict"],
        "contract_a_evidence": dim_a.get("negative_evidence") or dim_a.get("positive_evidence") or "",
        "contract_b_evidence": dim_b.get("negative_evidence") or dim_b.get("positive_evidence") or "",
    }


def _winner_label(score_a: int, score_b: int) -> str:
    if score_a > score_b:
        return "Contract A"
    if score_b > score_a:
        return "Contract B"
    return "Tie"


def _build_summary(score_a: int, score_b: int, winner: str) -> str:
    if winner == "Tie":
        return (
            "Both contracts appear broadly similar on the compared clauses. "
            f"Scores -> A: {score_a}, B: {score_b}."
        )

    safer = "A" if winner == "Contract A" else "B"
    other = "B" if safer == "A" else "A"
    return (
        f"Contract {safer} appears more favorable based on liability, termination, "
        f"payment, renewal, and dispute-resolution signals. Scores -> "
        f"A: {score_a}, B: {score_b}. Contract {other} shows relatively weaker terms "
        "in one or more dimensions."
    )


def compare_contracts(text_a: str, text_b: str) -> dict:
    """Compare two contracts and return structured risk/fairness differences."""
    clauses_a = _split_clauses(text_a)
    clauses_b = _split_clauses(text_b)

    if not clauses_a or not clauses_b:
        return {
            "summary": "Comparison requires non-empty text for both contracts.",
            "contract_a_score": 0,
            "contract_b_score": 0,
            "winner": "Tie",
            "category_comparison": [],
            "key_differences": [],
        }

    scored_a = [_score_dimension(clauses_a, dimension) for dimension in DIMENSIONS]
    scored_b = [_score_dimension(clauses_b, dimension) for dimension in DIMENSIONS]

    category_comparison = [
        _compare_dimension(dim_a, dim_b) for dim_a, dim_b in zip(scored_a, scored_b)
    ]

    total_a = sum(int(item["score"]) for item in scored_a)
    total_b = sum(int(item["score"]) for item in scored_b)
    winner = _winner_label(total_a, total_b)

    key_differences = [
        {
            "dimension": item["label"],
            "better_contract": item["better_contract"],
            "contract_a_evidence": item["contract_a_evidence"],
            "contract_b_evidence": item["contract_b_evidence"],
        }
        for item in category_comparison
        if item["better_contract"] != "Tie"
    ]

    return {
        "summary": _build_summary(total_a, total_b, winner),
        "contract_a_score": total_a,
        "contract_b_score": total_b,
        "winner": winner,
        "category_comparison": category_comparison,
        "key_differences": key_differences,
    }
