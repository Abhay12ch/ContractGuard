"""Vendor verification engine using Gemini AI assessment.

For hackathon MVP: uses the Gemini LLM to perform an intelligent
Know-Your-Business (KYB) assessment of the vendor named in a contract.

The AI evaluates:
  1. Whether the company name appears to be a real, registered entity
  2. Whether the company is plausibly active / operational
  3. Whether the incorporation timeline is consistent with the contract
  4. Whether the vendor name is consistent (no suspicious variations)
  5. Whether the jurisdiction aligns with the governing law

Trust Score (0-100): Sum of weighted checks.
Trust Level: Verified (≥75), Caution (≥40), Unverified (<40).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .gemini_client import gemini_available, generate_json

logger = logging.getLogger("contractguard.vendor_verifier")

# ── Score weights ──────────────────────────────────────────────────

CHECKS = [
    {"id": "registry_found", "label": "Company Recognition", "points": 25,
     "description": "Company name is recognized as a known business entity"},
    {"id": "status_active", "label": "Active Status", "points": 25,
     "description": "Company appears to be currently active and operational"},
    {"id": "incorporation_valid", "label": "Timeline Consistency", "points": 20,
     "description": "Company establishment predates the contract"},
    {"id": "name_match", "label": "Name Consistency", "points": 15,
     "description": "Vendor name is consistent and unambiguous"},
    {"id": "jurisdiction_match", "label": "Jurisdiction Alignment", "points": 15,
     "description": "Jurisdiction aligns with governing law of the contract"},
]

# ── Gemini Assessment Prompt ───────────────────────────────────────

_VERIFY_PROMPT = """\
You are a corporate due-diligence analyst. Assess the vendor named in this
contract for a Know-Your-Business (KYB) verification. Use your training
knowledge about real companies, corporate registries, and business entities.

VENDOR INFORMATION FROM CONTRACT:
- Vendor Name: {vendor_name}
- Customer Name: {customer_name}
- Contract Type: {contract_type}
- Effective Date: {effective_date}
- Governing Law / Jurisdiction: {governing_law}

Perform these 5 checks and return ONLY valid JSON in this exact format:
{{
  "vendor_analysis": {{
    "recognized_entity": true/false,
    "recognition_detail": "<Is this a known real company? Brief explanation>",
    "estimated_status": "Active" | "Inactive" | "Unknown",
    "status_detail": "<Brief assessment of operational status>",
    "estimated_founding": "<estimated year or 'Unknown'>",
    "founding_detail": "<Brief note about company history>",
    "name_legitimate": true/false,
    "name_detail": "<Is the name format legitimate for a business? Any red flags?>",
    "jurisdiction_consistent": true/false,
    "jurisdiction_detail": "<Does the jurisdiction make sense for this vendor?>"
  }},
  "registry_info": {{
    "probable_jurisdiction": "<e.g. India, Delaware USA, England & Wales>",
    "probable_type": "<e.g. Private Limited, LLP, Corporation, LLC>",
    "probable_registration": "<CIN/Company Number if known, else 'Not verified'>",
    "industry": "<Likely industry sector>"
  }},
  "red_flags": ["<list of specific concerns, empty array if none>"],
  "overall_assessment": "<2-3 sentence professional assessment>"
}}

Rules:
- Be factual. If the company is a well-known entity (TCS, Infosys, Google, etc.),
  confirm it. If unknown, say so honestly.
- Do NOT hallucinate real registration numbers. Use "Not verified" if unsure.
- For small/unknown companies, check if the name format looks legitimate
  (e.g. "XYZ Pvt Ltd" vs suspicious names like "ABCD 123 Corp").
- If vendor_name is empty, mark all checks as failed.
"""


def _parse_ai_assessment(raw: str) -> Optional[Dict[str, Any]]:
    """Parse Gemini's verification JSON response."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "vendor_analysis" not in data:
        return None
    return data


def _compute_trust_score(analysis: Dict[str, Any], effective_date: str) -> Dict[str, Any]:
    """Compute trust score from AI assessment data."""
    va = analysis.get("vendor_analysis", {})

    checks_results: List[Dict[str, Any]] = []
    total_score = 0

    # Check 1: Company Recognition
    passed = bool(va.get("recognized_entity", False))
    pts = CHECKS[0]["points"] if passed else 0
    total_score += pts
    checks_results.append({
        "check": CHECKS[0]["label"],
        "description": CHECKS[0]["description"],
        "passed": passed,
        "points": pts,
        "max_points": CHECKS[0]["points"],
        "detail": va.get("recognition_detail", ""),
    })

    # Check 2: Active Status
    status = va.get("estimated_status", "Unknown")
    passed = status == "Active"
    pts = CHECKS[1]["points"] if passed else (10 if status == "Unknown" else 0)
    total_score += pts
    checks_results.append({
        "check": CHECKS[1]["label"],
        "description": CHECKS[1]["description"],
        "passed": passed,
        "points": pts,
        "max_points": CHECKS[1]["points"],
        "detail": va.get("status_detail", ""),
    })

    # Check 3: Timeline Consistency
    founding = va.get("estimated_founding", "Unknown")
    if founding != "Unknown" and effective_date:
        try:
            founding_year = int(str(founding).strip()[:4])
            contract_year = int(str(effective_date).strip()[-4:]) if len(effective_date) >= 4 else 0
            if contract_year == 0:
                # Try extracting year from various date formats
                import re
                year_match = re.search(r'\b(19|20)\d{2}\b', effective_date)
                contract_year = int(year_match.group()) if year_match else 0
            passed = founding_year <= contract_year if contract_year > 0 else False
        except (ValueError, IndexError):
            passed = False
    else:
        passed = False
    pts = CHECKS[2]["points"] if passed else 0
    total_score += pts
    checks_results.append({
        "check": CHECKS[2]["label"],
        "description": CHECKS[2]["description"],
        "passed": passed,
        "points": pts,
        "max_points": CHECKS[2]["points"],
        "detail": va.get("founding_detail", f"Est. {founding}"),
    })

    # Check 4: Name Consistency
    passed = bool(va.get("name_legitimate", False))
    pts = CHECKS[3]["points"] if passed else 0
    total_score += pts
    checks_results.append({
        "check": CHECKS[3]["label"],
        "description": CHECKS[3]["description"],
        "passed": passed,
        "points": pts,
        "max_points": CHECKS[3]["points"],
        "detail": va.get("name_detail", ""),
    })

    # Check 5: Jurisdiction Alignment
    passed = bool(va.get("jurisdiction_consistent", False))
    pts = CHECKS[4]["points"] if passed else 0
    total_score += pts
    checks_results.append({
        "check": CHECKS[4]["label"],
        "description": CHECKS[4]["description"],
        "passed": passed,
        "points": pts,
        "max_points": CHECKS[4]["points"],
        "detail": va.get("jurisdiction_detail", ""),
    })

    # Determine trust level
    if total_score >= 75:
        trust_level = "Verified"
    elif total_score >= 40:
        trust_level = "Caution"
    else:
        trust_level = "Unverified"

    return {
        "trust_score": total_score,
        "trust_level": trust_level,
        "checks": checks_results,
    }


def _build_empty_result(vendor_name: str, reason: str) -> Dict[str, Any]:
    """Build an empty/failed verification result."""
    return {
        "vendor_name": vendor_name or "Unknown",
        "trust_score": 0,
        "trust_level": "Unverified",
        "verification_mode": "unavailable",
        "registry_data": {},
        "red_flags": [reason],
        "checks": [
            {
                "check": c["label"],
                "description": c["description"],
                "passed": False,
                "points": 0,
                "max_points": c["points"],
                "detail": reason,
            }
            for c in CHECKS
        ],
        "overall_assessment": reason,
    }


# ── Public API ─────────────────────────────────────────────────────

def verify_vendor(
    vendor_name: str,
    customer_name: str = "",
    contract_type: str = "",
    effective_date: str = "",
    governing_law: str = "",
) -> Dict[str, Any]:
    """Verify a vendor using Gemini AI assessment.

    Returns a dict with trust_score, trust_level, checks, red_flags, etc.
    """
    if not vendor_name or not vendor_name.strip():
        return _build_empty_result("", "No vendor name found in contract — cannot verify.")

    if not gemini_available():
        return _build_empty_result(vendor_name, "AI verification unavailable — Gemini API not configured.")

    # Build prompt
    prompt = _VERIFY_PROMPT.format(
        vendor_name=vendor_name,
        customer_name=customer_name or "Not specified",
        contract_type=contract_type or "Not specified",
        effective_date=effective_date or "Not specified",
        governing_law=governing_law or "Not specified",
    )

    raw = generate_json(prompt)
    if not raw:
        return _build_empty_result(vendor_name, "AI assessment failed — could not generate analysis.")

    analysis = _parse_ai_assessment(raw)
    if not analysis:
        return _build_empty_result(vendor_name, "AI assessment returned invalid data.")

    # Compute score
    score_result = _compute_trust_score(analysis, effective_date)

    # Build registry data from AI analysis
    registry_info = analysis.get("registry_info", {})
    red_flags = analysis.get("red_flags", [])
    overall = analysis.get("overall_assessment", "")

    return {
        "vendor_name": vendor_name,
        "trust_score": score_result["trust_score"],
        "trust_level": score_result["trust_level"],
        "verification_mode": "ai_assessment",
        "registry_data": {
            "jurisdiction": registry_info.get("probable_jurisdiction", "Unknown"),
            "company_type": registry_info.get("probable_type", "Unknown"),
            "registration_number": registry_info.get("probable_registration", "Not verified"),
            "industry": registry_info.get("industry", "Unknown"),
            "estimated_status": analysis.get("vendor_analysis", {}).get("estimated_status", "Unknown"),
            "estimated_founding": analysis.get("vendor_analysis", {}).get("estimated_founding", "Unknown"),
        },
        "red_flags": red_flags if isinstance(red_flags, list) else [],
        "checks": score_result["checks"],
        "overall_assessment": overall,
    }


__all__ = ["verify_vendor"]
