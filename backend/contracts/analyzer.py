"""Hybrid contract risk analysis: Gemini LLM + keyword fallback.

When Gemini is available, the contract text is sent to the LLM with a
structured-output prompt that returns JSON with detected risky clauses,
severity ratings, and a safety score 0-100.

When Gemini is unavailable the original deterministic keyword scanner
runs as a reliable fallback so the API never breaks.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List

from .gemini_client import gemini_available, generate_json

logger = logging.getLogger("contractguard.analyzer")

# ── Deterministic keyword fallback ──────────────────────────────────

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


def _split_candidate_clauses(text: str) -> List[str]:
    collapsed = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[\\.;:!?])\s+|\n+", collapsed)
    return [part.strip() for part in parts if len(part.strip()) >= 20]


def _risk_level_from_score(safety_score: int) -> str:
    if safety_score >= 80:
        return "Low Risk"
    if safety_score >= 60:
        return "Moderate Risk"
    if safety_score >= 40:
        return "High Risk"
    return "Very High Risk"


def _keyword_analyze(text: str) -> dict:
    """Original deterministic keyword-based analysis."""
    clauses = _split_candidate_clauses(text)
    findings: List[dict] = []

    for rule_id, rule in RISK_RULES.items():
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
            break

    score = 100
    for finding in findings:
        score -= int(finding["impact"])

    safety_score = max(0, min(100, score))
    return {
        "safety_score": safety_score,
        "risk_score": safety_score,
        "risk_level": _risk_level_from_score(safety_score),
        "detected_clause_count": len(findings),
        "risks": findings,
    }


# ── LLM-powered analysis ───────────────────────────────────────────

_ANALYSIS_PROMPT = """\
You are a senior contract risk analyst. Analyse the following contract text and identify ALL risky or noteworthy clauses.

For each risky clause you find, provide:
- clause_type: a snake_case identifier (e.g. "unlimited_liability", "auto_renewal", "ip_assignment", "confidentiality_breach", "governing_law_unfavorable")
- title: a short human-readable title
- severity: one of "High", "Medium", or "Low"
- evidence: the EXACT sentence or phrase from the contract that demonstrates the risk
- explanation: 1-2 sentences explaining why this is risky for the signing party

After identifying all clauses, assign an overall safety_score from 0 to 100:
- 100 = perfectly safe contract with no risky terms
- 0 = extremely dangerous contract with many severe risks
- Be realistic: most contracts score between 40-85

Return ONLY valid JSON in this exact format (no markdown, no commentary):
{{
  "safety_score": <int 0-100>,
  "risk_level": "<Low Risk|Moderate Risk|High Risk|Very High Risk>",
  "risks": [
    {{
      "clause_type": "<snake_case>",
      "title": "<string>",
      "severity": "<High|Medium|Low>",
      "evidence": "<exact quote from contract>",
      "explanation": "<why this is risky>"
    }}
  ]
}}

Rules:
- Only identify risks that are ACTUALLY present in the text.
- Do NOT invent or hallucinate clauses.
- If the contract is genuinely safe, return an empty risks array and a high safety_score.

--- CONTRACT TEXT ---
{contract_text}
--- END ---
"""


def _parse_llm_analysis(raw_json: str) -> dict | None:
    """Parse and validate the LLM JSON response into the expected dict format."""
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    safety_score = int(data.get("safety_score", -1))
    if not (0 <= safety_score <= 100):
        return None

    risks_raw = data.get("risks", [])
    if not isinstance(risks_raw, list):
        return None

    risks: List[dict] = []
    for item in risks_raw:
        if not isinstance(item, dict):
            continue
        risks.append(
            {
                "clause_type": str(item.get("clause_type", "unknown")),
                "title": str(item.get("title", "Unnamed Risk")),
                "severity": str(item.get("severity", "Medium")),
                "keyword": str(item.get("clause_type", "llm_detected")),
                "impact": {"High": 20, "Medium": 10, "Low": 5}.get(
                    str(item.get("severity", "Medium")), 10
                ),
                "evidence": str(item.get("evidence", "")),
                "explanation": str(item.get("explanation", "")),
            }
        )

    risk_level = str(data.get("risk_level", _risk_level_from_score(safety_score)))

    return {
        "safety_score": safety_score,
        "risk_score": safety_score,
        "risk_level": risk_level,
        "detected_clause_count": len(risks),
        "risks": risks,
    }


def _llm_analyze(text: str) -> dict | None:
    """Run LLM-powered risk analysis. Returns None on failure."""
    truncated = text[:30_000]
    prompt = _ANALYSIS_PROMPT.format(contract_text=truncated)
    raw = generate_json(prompt)
    if not raw:
        return None
    return _parse_llm_analysis(raw)


# ── Public API ──────────────────────────────────────────────────────

def analyze_contract(text: str) -> dict:
    """Detect risky clauses and calculate a contract safety score (0-100).

    Uses Gemini LLM when available for deep semantic analysis.
    Falls back to deterministic keyword scanning otherwise.
    """
    if not text or not text.strip():
        return {
            "safety_score": 0,
            "risk_score": 0,
            "risk_level": "Unknown",
            "detected_clause_count": 0,
            "risks": [],
        }

    if gemini_available():
        llm_result = _llm_analyze(text)
        if llm_result is not None:
            logger.info(
                "LLM analysis complete: safety_score=%d, risks=%d",
                llm_result["safety_score"],
                llm_result["detected_clause_count"],
            )
            return llm_result
        logger.warning("LLM analysis failed — falling back to keyword scanner.")

    return _keyword_analyze(text)


__all__ = ["analyze_contract"]
