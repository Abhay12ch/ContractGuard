"""Hybrid contract risk analysis: Gemini LLM + keyword fallback.

Scoring Methodology (based on ISO 31000 / NIST 800-30):
- Risk Score (0-100):  Accumulated risk exposure from detected clauses.
        Computed as: Σ(impact × severity_weight) normalised to 0-100.
        Higher = more dangerous.
- Safety Score (0-100): Complement of risk_score = 100 - risk_score.
        Higher = safer.
- Risk Level:  Derived from safety_score thresholds:
        ≥80 Low Risk, ≥60 Moderate Risk, ≥40 High Risk, <40 Very High Risk.

Severity weights:
  High   = 1.0   (maximum damage potential)
  Medium = 0.6   (moderate damage potential)
  Low    = 0.25  (minor / informational)

When Gemini is available, the LLM returns risk clauses with per-clause
impact values (5-25). Scores are *always* derived deterministically from
the clauses using _compute_scores(), never taken verbatim from the LLM.

When Gemini is unavailable the deterministic keyword scanner runs as a
reliable fallback so the API never breaks.
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
        "source": "Indian Contract Act 1872, §73-74 — Compensation for breach must be reasonable and foreseeable; penalty clauses beyond reasonable compensation are void under §74. Also: UCC §2-719 (US).",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/2187",
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
        "source": "Indian Contract Act 1872, §74 — Stipulated penalty or liquidated damages: only reasonable compensation is recoverable, courts can reduce excessive amounts. Also: Restatement (Second) of Contracts §356 (US).",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/2187",
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
        "source": "Consumer Protection Act 2019, §2(46) — Unfair contract terms including auto-renewal without clear consent can be declared void. Also: FTC Negative Option Rule, 16 CFR §425 (US).",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/15256",
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
        "source": "Indian Contract Act 1872, §27 — Every agreement in restraint of trade is void (except sale of goodwill). Non-compete clauses in employment are generally unenforceable in India. Also: Competition Act 2002, §3.",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/2187",
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
        "source": "Indian Contract Act 1872, §29 — Agreements void for uncertainty; vague payment terms may render the contract unenforceable. Also: UCC §2-305 (US).",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/2187",
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
        "source": "Indian Contract Act 1872, §37 — Obligation to perform promises; clear payment schedules establish enforceable obligations. Also: UCC §2-310 (US).",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/2187",
    },
}


def _split_candidate_clauses(text: str) -> List[str]:
    collapsed = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[\\.;:!?])\s+|\n+", collapsed)
    return [part.strip() for part in parts if len(part.strip()) >= 20]


# ── Severity weights (ISO 31000 aligned) ─────────────────────────────

SEVERITY_WEIGHT = {
    "High": 1.0,
    "Medium": 0.6,
    "Low": 0.25,
}


def _risk_level_from_safety(safety_score: int) -> str:
    """Map safety_score to a human-readable risk level."""
    if safety_score >= 80:
        return "Low Risk"
    if safety_score >= 60:
        return "Moderate Risk"
    if safety_score >= 40:
        return "High Risk"
    return "Very High Risk"


def _compute_scores(findings: List[dict]) -> dict:
    """Compute risk_score and safety_score from a list of findings.

    Risk Score formula (weighted deduction model):
      raw = Σ (impact_i × severity_weight_i)
      risk_score = min(100, raw)       # cap at 100
      safety_score = 100 - risk_score   # complement

    This produces two *distinct and independently meaningful* numbers:
      - risk_score  tells you HOW MUCH risk was detected
      - safety_score tells you HOW SAFE the contract is overall
    """
    raw_risk = 0.0
    for f in findings:
        base_impact = abs(int(f.get("impact", 10)))
        sev = f.get("severity", "Medium")
        weight = SEVERITY_WEIGHT.get(sev, 0.6)
        raw_risk += base_impact * weight

    risk_score = min(100, round(raw_risk))
    safety_score = 100 - risk_score
    return {
        "risk_score": risk_score,
        "safety_score": safety_score,
        "risk_level": _risk_level_from_safety(safety_score),
    }


def _keyword_analyze(text: str) -> dict:
    """Deterministic keyword-based analysis with weighted scoring."""
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
                    "source": rule.get("source", ""),
                    "source_url": rule.get("source_url", ""),
                }
            )
            break

    scores = _compute_scores(findings)
    return {
        **scores,
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
- impact: an integer from 5-25 representing the base point deduction for this risk (High severity risks 18-25, Medium 8-15, Low 3-7)
- evidence: the EXACT sentence or phrase from the contract that demonstrates the risk
- explanation: 1-2 sentences explaining why this is risky for the signing party
- source: the specific legal statute, regulation, or legal principle that makes this clause risky. PRIORITIZE Indian law first (e.g. "Indian Contract Act 1872, §27", "Consumer Protection Act 2019, §2(46)", "Competition Act 2002, §3"), then cite the equivalent US/international law if applicable (e.g. "Also: UCC §2-719 (US)").
- source_url: a direct URL to the legal text. Prefer https://www.indiacode.nic.in for Indian statutes, https://www.law.cornell.edu for US UCC/statutes, https://www.ftc.gov for FTC rules. If no exact URL is available, use the closest relevant page.

Scoring methodology (YOU MUST FOLLOW THIS):
- Each clause has an "impact" (5-25 base points) and a "severity" (High/Medium/Low).
- I will compute the risk_score myself using: sum(impact × severity_weight) where High=1.0, Medium=0.6, Low=0.25.
- risk_score is capped at 100. safety_score = 100 - risk_score.
- Do NOT return safety_score or risk_score — I will derive them from the clauses you provide.
- Be calibrated: most commercial contracts have 3-8 risks and land at risk_score 25-60.

Return ONLY valid JSON in this exact format (no markdown, no commentary):
{{
  "risks": [
    {{
      "clause_type": "<snake_case>",
      "title": "<string>",
      "severity": "<High|Medium|Low>",
      "impact": <int 5-25>,
      "evidence": "<exact quote from contract>",
      "explanation": "<why this is risky>",
      "source": "<legal statute — Indian law first, then US/international>",
      "source_url": "<URL to the legal text>"
    }}
  ]
}}

Rules:
- Only identify risks that are ACTUALLY present in the text.
- Do NOT invent or hallucinate clauses.
- If the contract is genuinely safe, return an empty risks array.
- For source, ALWAYS cite Indian law first (Indian Contract Act 1872, Consumer Protection Act 2019, Competition Act 2002, Information Technology Act 2000, etc.), then add the US equivalent as secondary.
- For source_url, prefer https://www.indiacode.nic.in for Indian law. Use https://www.law.cornell.edu for US law.

--- CONTRACT TEXT ---
{contract_text}
--- END ---
"""


def _parse_llm_analysis(raw_json: str) -> dict | None:
    """Parse the LLM JSON response, then *derive* scores deterministically.

    The LLM now only returns the risks array; we compute risk_score and
    safety_score ourselves using _compute_scores() to ensure they are
    always consistent and auditable.
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    risks_raw = data.get("risks", [])
    if not isinstance(risks_raw, list):
        return None

    risks: List[dict] = []
    for item in risks_raw:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "Medium"))
        # Use LLM-provided impact if valid (5-25), else derive from severity
        raw_impact = item.get("impact")
        try:
            impact_val = int(raw_impact)
            if not (3 <= impact_val <= 25):
                raise ValueError
        except (TypeError, ValueError):
            impact_val = {"High": 20, "Medium": 10, "Low": 5}.get(severity, 10)

        risks.append(
            {
                "clause_type": str(item.get("clause_type", "unknown")),
                "title": str(item.get("title", "Unnamed Risk")),
                "severity": severity,
                "keyword": str(item.get("clause_type", "llm_detected")),
                "impact": impact_val,
                "evidence": str(item.get("evidence", "")),
                "explanation": str(item.get("explanation", "")),
                "source": str(item.get("source", "")),
                "source_url": str(item.get("source_url", "")),
            }
        )

    # Derive scores deterministically from the risks list
    scores = _compute_scores(risks)

    return {
        **scores,
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
