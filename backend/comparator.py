"""Contract comparison utilities.

This module provides a deterministic clause comparison that can run without an
LLM dependency. It scores each contract on common risk and fairness dimensions
and returns a structured side-by-side summary.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List

from .analyzer import analyze_contract


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


def _build_summary(
    score_a: int,
    score_b: int,
    winner: str,
    safety_a: int,
    safety_b: int,
    safer_contract: str,
) -> str:
    if winner == "Tie":
        return (
            "Both contracts appear broadly similar on the compared clauses. "
            f"Dimension scores -> A: {score_a}, B: {score_b}. "
            f"Safety scores -> A: {safety_a}/100, B: {safety_b}/100."
        )

    safer = "A" if winner == "Contract A" else "B"
    other = "B" if safer == "A" else "A"
    risk_part = (
        f" Risk scoring indicates {safer_contract} is safer "
        f"(A: {safety_a}/100, B: {safety_b}/100)."
        if safer_contract != "Tie"
        else f" Risk scoring is tied at A: {safety_a}/100 and B: {safety_b}/100."
    )
    return (
        f"Contract {safer} appears more favorable based on liability, termination, "
        f"payment, renewal, and dispute-resolution signals. Scores -> "
        f"A: {score_a}, B: {score_b}. Contract {other} shows relatively weaker terms "
        f"in one or more dimensions.{risk_part}"
    )


def _risk_snapshot(text: str) -> Dict[str, object]:
    analysis = analyze_contract(text)
    safety_score = int(analysis.get("safety_score", analysis.get("risk_score", 0)))
    safety_score = max(0, min(100, safety_score))
    return {
        "safety_score": safety_score,
        "risk_score": 100 - safety_score,
        "risk_level": str(analysis.get("risk_level", "Unknown")),
        "detected_clause_count": int(analysis.get("detected_clause_count", 0)),
    }


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
            "risk_comparison": {
                "contract_a_safety_score": 0,
                "contract_b_safety_score": 0,
                "contract_a_risk_score": 100,
                "contract_b_risk_score": 100,
                "contract_a_risk_level": "Unknown",
                "contract_b_risk_level": "Unknown",
                "contract_a_detected_clause_count": 0,
                "contract_b_detected_clause_count": 0,
                "safer_contract": "Tie",
                "safety_score_gap": 0,
            },
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

    risk_a = _risk_snapshot(text_a)
    risk_b = _risk_snapshot(text_b)
    safety_a = int(risk_a["safety_score"])
    safety_b = int(risk_b["safety_score"])
    if safety_a > safety_b:
        safer_contract = "Contract A"
    elif safety_b > safety_a:
        safer_contract = "Contract B"
    else:
        safer_contract = "Tie"

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
        "summary": _build_summary(total_a, total_b, winner, safety_a, safety_b, safer_contract),
        "contract_a_score": total_a,
        "contract_b_score": total_b,
        "winner": winner,
        "risk_comparison": {
            "contract_a_safety_score": safety_a,
            "contract_b_safety_score": safety_b,
            "contract_a_risk_score": int(risk_a["risk_score"]),
            "contract_b_risk_score": int(risk_b["risk_score"]),
            "contract_a_risk_level": str(risk_a["risk_level"]),
            "contract_b_risk_level": str(risk_b["risk_level"]),
            "contract_a_detected_clause_count": int(risk_a["detected_clause_count"]),
            "contract_b_detected_clause_count": int(risk_b["detected_clause_count"]),
            "safer_contract": safer_contract,
            "safety_score_gap": abs(safety_a - safety_b),
        },
        "category_comparison": category_comparison,
        "key_differences": key_differences,
    }
