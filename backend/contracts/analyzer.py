"""Keyword-based contract risk analysis."""

from __future__ import annotations

from typing import Dict, List
import re


RISK_RULES: Dict[str, dict] = {
    "unlimited_liability": {
        "label": "Unlimited Liability",
        "severity": "High",
        "score_impact": 22,
        "keywords": [
            "unlimited liability",
            "liable for all damages",
            "indemnify",
            "all losses",
            "without limitation",
        ],
    },
    "termination_penalty": {
        "label": "Termination Penalty",
        "severity": "High",
        "score_impact": 18,
        "keywords": [
            "termination fee",
            "early termination fee",
            "penalty",
            "liquidated damages",
            "cancellation charge",
        ],
    },
    "auto_renewal": {
        "label": "Auto Renewal",
        "severity": "Medium",
        "score_impact": 10,
        "keywords": [
            "auto renewal",
            "automatically renew",
            "renews automatically",
            "renewal term",
        ],
    },
    "non_compete": {
        "label": "Non-Compete Restriction",
        "severity": "Medium",
        "score_impact": 9,
        "keywords": [
            "non-compete",
            "non compete",
            "restrictive covenant",
            "cannot work with competitors",
        ],
    },
    "unclear_payment": {
        "label": "Unclear Payment Terms",
        "severity": "Medium",
        "score_impact": 8,
        "keywords": [
            "payment at sole discretion",
            "subject to approval",
            "as determined by",
            "delayed payment",
        ],
    },
    "clear_payment": {
        "label": "Clear Payment Terms",
        "severity": "Low",
        "score_impact": -5,
        "keywords": [
            "payment schedule",
            "net 30",
            "invoice due",
            "paid within",
            "monthly payment",
        ],
    },
}

__all__ = ["analyze_contract"]


def _split_candidate_clauses(text: str) -> List[str]:
    """Split document into sentence-like candidate clauses for scanning."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[\.;:!?])\s+|\n+", collapsed)
    return [part.strip() for part in parts if len(part.strip()) >= 20]


def _risk_level_from_score(safety_score: int) -> str:
    if safety_score >= 80:
        return "Low Risk"
    if safety_score >= 60:
        return "Moderate Risk"
    if safety_score >= 40:
        return "High Risk"
    return "Very High Risk"


def analyze_contract(text: str) -> dict:
    """Detect risky clauses and calculate a contract safety score (0-100).

    Safety score starts at 100 and is adjusted by detected clause impacts.
    Higher score means safer contract.
    """
    if not text or not text.strip():
        return {
            "safety_score": 0,
            "risk_score": 0,
            "risk_level": "Unknown",
            "detected_clause_count": 0,
            "risks": [],
        }

    clauses = _split_candidate_clauses(text)
    findings: List[dict] = []

    for rule_id, rule in RISK_RULES.items():
        matched = False
        for clause in clauses:
            hay = clause.lower()
            hit = next((kw for kw in rule["keywords"] if kw in hay), None)
            if not hit:
                continue

            findings.append(
                {
                    "clause_type": rule_id,
                    "title": rule["label"],
                    "severity": rule["severity"],
                    "keyword": hit,
                    "impact": rule["score_impact"],
                    "evidence": clause,
                }
            )
            matched = True
            break

        # Keep one representative hit per rule to avoid over-penalizing duplicates.
        if matched:
            continue

    score = 100
    for finding in findings:
        score -= int(finding["impact"])

    safety_score = max(0, min(100, score))
    risk_level = _risk_level_from_score(safety_score)

    return {
        "safety_score": safety_score,
        # Keep risk_score for backward compatibility with existing clients.
        "risk_score": safety_score,
        "risk_level": risk_level,
        "detected_clause_count": len(findings),
        "risks": findings,
    }
