"""Contract comparison: Gemini LLM + deterministic fallback.

When Gemini is available, both contract texts are sent to the LLM for an
intelligent side-by-side comparison that identifies which contract is
more favorable across multiple legal dimensions.

When Gemini is unavailable, the original deterministic keyword-scoring
engine runs as a reliable offline fallback.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List

from .analyzer import analyze_contract
from .gemini_client import gemini_available, generate_json

logger = logging.getLogger("contractguard.comparator")

# ── Deterministic fallback (original keyword engine) ────────────────

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
        positive_terms=["limited liability", "liability cap", "cap on liability", "maximum liability"],
        negative_terms=["unlimited liability", "without limitation", "all damages", "indemnify for all losses"],
        weight=3,
    ),
    CompareDimension(
        key="termination",
        label="Termination Flexibility",
        positive_terms=["terminate with notice", "termination for convenience", "written notice", "right to terminate"],
        negative_terms=["early termination fee", "termination penalty", "liquidated damages", "cancellation charge"],
        weight=3,
    ),
    CompareDimension(
        key="payment",
        label="Payment Clarity",
        positive_terms=["payment schedule", "net 30", "invoice due", "paid within", "monthly payment"],
        negative_terms=["sole discretion", "subject to approval", "delayed payment", "as determined by"],
        weight=2,
    ),
    CompareDimension(
        key="renewal",
        label="Renewal Control",
        positive_terms=["renewal requires consent", "opt-in renewal", "written renewal"],
        negative_terms=["auto renewal", "automatically renew", "renews automatically"],
        weight=2,
    ),
    CompareDimension(
        key="dispute_resolution",
        label="Dispute Resolution Fairness",
        positive_terms=["mutual arbitration", "mutual jurisdiction", "good faith negotiation"],
        negative_terms=["exclusive jurisdiction", "waive right to", "non-appealable"],
        weight=1,
    ),
]

CONTRACT_A_LABEL = "Contract A"
CONTRACT_B_LABEL = "Contract B"
TIE_LABEL = "Tie"


def _split_clauses(text: str) -> List[str]:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if not collapsed:
        return []
    parts = re.split(r"(?<=[\\.;:!?])\s+", collapsed)
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
        score, verdict = dimension.weight, "favorable"
    elif negative_hit and not positive_hit:
        score, verdict = -dimension.weight, "unfavorable"
    elif positive_hit and negative_hit:
        score, verdict = 0, "mixed"
    else:
        score, verdict = 0, "not_found"
    return {
        "key": dimension.key, "label": dimension.label,
        "score": score, "verdict": verdict,
        "positive_evidence": positive_hit, "negative_evidence": negative_hit,
    }


def _compare_dimension(dim_a: Dict[str, object], dim_b: Dict[str, object]) -> Dict[str, object]:
    score_a, score_b = int(dim_a["score"]), int(dim_b["score"])
    better = "A" if score_a > score_b else ("B" if score_b > score_a else "Tie")
    return {
        "key": dim_a["key"], "label": dim_a["label"],
        "contract_a_score": score_a, "contract_b_score": score_b,
        "better_contract": better,
        "contract_a_verdict": dim_a["verdict"], "contract_b_verdict": dim_b["verdict"],
        "contract_a_evidence": dim_a.get("negative_evidence") or dim_a.get("positive_evidence") or "",
        "contract_b_evidence": dim_b.get("negative_evidence") or dim_b.get("positive_evidence") or "",
    }


def _winner_label(score_a: int, score_b: int) -> str:
    if score_a > score_b:
        return CONTRACT_A_LABEL
    if score_b > score_a:
        return CONTRACT_B_LABEL
    return TIE_LABEL


def _risk_snapshot(text: str) -> Dict[str, object]:
    analysis = analyze_contract(text)
    safety_score = max(0, min(100, int(analysis.get("safety_score", analysis.get("risk_score", 0)))))
    return {
        "safety_score": safety_score,
        "risk_score": 100 - safety_score,
        "risk_level": str(analysis.get("risk_level", "Unknown")),
        "detected_clause_count": int(analysis.get("detected_clause_count", 0)),
    }


def _deterministic_compare(text_a: str, text_b: str) -> dict:
    """Original keyword-based comparison engine."""
    clauses_a = _split_clauses(text_a)
    clauses_b = _split_clauses(text_b)

    if not clauses_a or not clauses_b:
        return _empty_comparison()

    scored_a = [_score_dimension(clauses_a, d) for d in DIMENSIONS]
    scored_b = [_score_dimension(clauses_b, d) for d in DIMENSIONS]
    category_comparison = [_compare_dimension(a, b) for a, b in zip(scored_a, scored_b)]

    total_a = sum(int(i["score"]) for i in scored_a)
    total_b = sum(int(i["score"]) for i in scored_b)
    winner = _winner_label(total_a, total_b)

    risk_a = _risk_snapshot(text_a)
    risk_b = _risk_snapshot(text_b)
    safety_a, safety_b = int(risk_a["safety_score"]), int(risk_b["safety_score"])
    safer_contract = CONTRACT_A_LABEL if safety_a > safety_b else (CONTRACT_B_LABEL if safety_b > safety_a else TIE_LABEL)

    key_differences = [
        {"dimension": i["label"], "better_contract": i["better_contract"],
         "contract_a_evidence": i["contract_a_evidence"], "contract_b_evidence": i["contract_b_evidence"]}
        for i in category_comparison if i["better_contract"] != TIE_LABEL
    ]

    summary_text = (
        f"{'Contract A' if winner == CONTRACT_A_LABEL else 'Contract B' if winner == CONTRACT_B_LABEL else 'Both contracts'} "
        f"{'appears more favorable' if winner != TIE_LABEL else 'appear broadly similar'} "
        f"based on clause analysis. "
        f"Risk scores → A: {safety_a}/100, B: {safety_b}/100."
    )

    return {
        "summary": summary_text,
        "contract_a_score": total_a, "contract_b_score": total_b,
        "winner": winner,
        "risk_comparison": {
            "contract_a_safety_score": safety_a, "contract_b_safety_score": safety_b,
            "contract_a_risk_score": int(risk_a["risk_score"]), "contract_b_risk_score": int(risk_b["risk_score"]),
            "contract_a_risk_level": str(risk_a["risk_level"]), "contract_b_risk_level": str(risk_b["risk_level"]),
            "contract_a_detected_clause_count": int(risk_a["detected_clause_count"]),
            "contract_b_detected_clause_count": int(risk_b["detected_clause_count"]),
            "safer_contract": safer_contract, "safety_score_gap": abs(safety_a - safety_b),
        },
        "category_comparison": category_comparison,
        "key_differences": key_differences,
    }


def _empty_comparison() -> dict:
    return {
        "summary": "Comparison requires non-empty text for both contracts.",
        "contract_a_score": 0, "contract_b_score": 0, "winner": "Tie",
        "risk_comparison": {
            "contract_a_safety_score": 0, "contract_b_safety_score": 0,
            "contract_a_risk_score": 100, "contract_b_risk_score": 100,
            "contract_a_risk_level": "Unknown", "contract_b_risk_level": "Unknown",
            "contract_a_detected_clause_count": 0, "contract_b_detected_clause_count": 0,
            "safer_contract": "Tie", "safety_score_gap": 0,
        },
        "category_comparison": [], "key_differences": [],
    }


# ── LLM-powered comparison ─────────────────────────────────────────

_COMPARE_PROMPT = """\
You are a senior legal analyst comparing two contracts side by side.

Analyze both contracts across these dimensions:
1. Liability Terms — who bears more risk?
2. Termination Flexibility — which contract is easier to exit?
3. Payment Clarity — which has clearer, fairer payment terms?
4. Renewal Control — which gives the signer more renewal control?
5. Dispute Resolution — which has fairer dispute handling?
6. IP & Confidentiality — any IP assignment or NDA concerns?
7. Compliance & Governing Law — any jurisdiction red flags?

Return ONLY valid JSON in this exact format (no markdown):
{{
  "summary": "<3-4 sentence executive summary of which contract is better and why>",
  "winner": "<Contract A|Contract B|Tie>",
  "contract_a_safety_score": <int 0-100>,
  "contract_b_safety_score": <int 0-100>,
  "key_differences": [
    {{
      "dimension": "<label>",
      "better_contract": "<A|B|Tie>",
      "contract_a_finding": "<what Contract A says>",
      "contract_b_finding": "<what Contract B says>",
      "explanation": "<why one is better>"
    }}
  ]
}}

Rules:
- Base your analysis ONLY on the text provided. Do NOT hallucinate.
- Be specific and cite actual clauses when possible.
- Safety score: 100 = very safe, 0 = very dangerous.

--- CONTRACT A ---
{text_a}
--- END CONTRACT A ---

--- CONTRACT B ---
{text_b}
--- END CONTRACT B ---
"""


def _parse_llm_comparison(raw_json: str) -> dict | None:
    """Parse and validate the LLM JSON into the expected response structure."""
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    summary = str(data.get("summary", "")).strip()
    winner_raw = str(data.get("winner", "Tie")).strip()
    if "A" in winner_raw and "B" not in winner_raw:
        winner = CONTRACT_A_LABEL
    elif "B" in winner_raw and "A" not in winner_raw:
        winner = CONTRACT_B_LABEL
    else:
        winner = TIE_LABEL

    safety_a = max(0, min(100, int(data.get("contract_a_safety_score", 50))))
    safety_b = max(0, min(100, int(data.get("contract_b_safety_score", 50))))
    safer_contract = CONTRACT_A_LABEL if safety_a > safety_b else (CONTRACT_B_LABEL if safety_b > safety_a else TIE_LABEL)

    key_differences_raw = data.get("key_differences", [])
    key_differences = []
    category_comparison = []

    for item in (key_differences_raw if isinstance(key_differences_raw, list) else []):
        if not isinstance(item, dict):
            continue
        bc = str(item.get("better_contract", "Tie"))
        better = "A" if "A" in bc else ("B" if "B" in bc else "Tie")
        dim_label = str(item.get("dimension", "Unknown"))

        key_differences.append({
            "dimension": dim_label,
            "better_contract": better,
            "contract_a_evidence": str(item.get("contract_a_finding", "")),
            "contract_b_evidence": str(item.get("contract_b_finding", "")),
            "explanation": str(item.get("explanation", "")),
        })
        category_comparison.append({
            "key": dim_label.lower().replace(" ", "_"),
            "label": dim_label,
            "contract_a_score": 1 if better == "A" else (-1 if better == "B" else 0),
            "contract_b_score": 1 if better == "B" else (-1 if better == "A" else 0),
            "better_contract": better,
            "contract_a_verdict": "favorable" if better == "A" else ("unfavorable" if better == "B" else "mixed"),
            "contract_b_verdict": "favorable" if better == "B" else ("unfavorable" if better == "A" else "mixed"),
            "contract_a_evidence": str(item.get("contract_a_finding", "")),
            "contract_b_evidence": str(item.get("contract_b_finding", "")),
        })

    total_a = sum(d["contract_a_score"] for d in category_comparison)
    total_b = sum(d["contract_b_score"] for d in category_comparison)

    return {
        "summary": summary or "Comparison completed.",
        "contract_a_score": total_a,
        "contract_b_score": total_b,
        "winner": winner,
        "risk_comparison": {
            "contract_a_safety_score": safety_a,
            "contract_b_safety_score": safety_b,
            "contract_a_risk_score": 100 - safety_a,
            "contract_b_risk_score": 100 - safety_b,
            "contract_a_risk_level": "",
            "contract_b_risk_level": "",
            "contract_a_detected_clause_count": 0,
            "contract_b_detected_clause_count": 0,
            "safer_contract": safer_contract,
            "safety_score_gap": abs(safety_a - safety_b),
        },
        "category_comparison": category_comparison,
        "key_differences": key_differences,
    }


def _llm_compare(text_a: str, text_b: str) -> dict | None:
    # Truncate each contract to ~15k chars so both fit in context.
    truncated_a = text_a[:15_000]
    truncated_b = text_b[:15_000]
    prompt = _COMPARE_PROMPT.format(text_a=truncated_a, text_b=truncated_b)
    raw = generate_json(prompt)
    if not raw:
        return None
    return _parse_llm_comparison(raw)


# ── Public API ──────────────────────────────────────────────────────

def compare_contracts(text_a: str, text_b: str) -> dict:
    """Compare two contracts and return structured risk/fairness differences.

    Uses Gemini LLM when available for intelligent comparison.
    Falls back to deterministic keyword engine otherwise.
    """
    if not text_a or not text_a.strip() or not text_b or not text_b.strip():
        return _empty_comparison()

    if gemini_available():
        llm_result = _llm_compare(text_a, text_b)
        if llm_result is not None:
            logger.info("LLM comparison complete: winner=%s", llm_result.get("winner"))
            return llm_result
        logger.warning("LLM comparison failed — falling back to keyword engine.")

    return _deterministic_compare(text_a, text_b)


__all__ = ["CompareDimension", "compare_contracts"]
