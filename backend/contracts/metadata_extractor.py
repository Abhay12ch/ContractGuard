"""LLM-powered structured metadata extraction from contract text.

Extracts key business entities (parties, payment terms, billing cycle,
renewal terms, dates) using Gemini structured output.

Falls back to a lightweight regex extractor when Gemini is unavailable
so the analytics dashboard always has data to show.

This module is fully independent — it does NOT import from summarizer,
analyzer, or any other AI module.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from .gemini_client import gemini_available, generate_json

logger = logging.getLogger("contractguard.metadata_extractor")

# ── Schema definition ──────────────────────────────────────────────

METADATA_FIELDS = [
    "customer_name",
    "vendor_name",
    "contract_type",
    "effective_date",
    "expiration_date",
    "payment_terms",
    "billing_cycle",
    "total_value",
    "renewal_terms",
    "governing_law",
]

_EMPTY_METADATA: Dict[str, Any] = {
    "customer_name": {"value": "", "confidence": 0},
    "vendor_name": {"value": "", "confidence": 0},
    "contract_type": {"value": "", "confidence": 0},
    "effective_date": {"value": "", "confidence": 0},
    "expiration_date": {"value": "", "confidence": 0},
    "payment_terms": {"value": "", "confidence": 0},
    "billing_cycle": {"value": "", "confidence": 0},
    "total_value": {"value": "", "confidence": 0},
    "renewal_terms": {"value": "", "confidence": 0},
    "governing_law": {"value": "", "confidence": 0},
}


# ── LLM-powered extraction ────────────────────────────────────────

_EXTRACTION_PROMPT = """\
You are a contract metadata extraction engine. Extract the following fields
from the contract text below. For each field, provide:
- value: the extracted text (empty string if not found)
- confidence: integer 0-100 representing how confident you are

Return ONLY valid JSON in this exact format (no markdown, no commentary):
{{
  "customer_name": {{"value": "<name or empty>", "confidence": <0-100>}},
  "vendor_name": {{"value": "<name or empty>", "confidence": <0-100>}},
  "contract_type": {{"value": "<e.g. Service Agreement, NDA, Employment>", "confidence": <0-100>}},
  "effective_date": {{"value": "<date or empty>", "confidence": <0-100>}},
  "expiration_date": {{"value": "<date or empty>", "confidence": <0-100>}},
  "payment_terms": {{"value": "<e.g. Net 30, Due on receipt>", "confidence": <0-100>}},
  "billing_cycle": {{"value": "<e.g. Monthly, Quarterly, $5000/month>", "confidence": <0-100>}},
  "total_value": {{"value": "<e.g. $120,000 or empty>", "confidence": <0-100>}},
  "renewal_terms": {{"value": "<e.g. Auto-renews annually with 30-day notice>", "confidence": <0-100>}},
  "governing_law": {{"value": "<e.g. State of California>", "confidence": <0-100>}}
}}

Rules:
- Only extract what is ACTUALLY in the text. Do NOT hallucinate.
- If a field is not present, set value to "" and confidence to 0.
- Confidence should reflect how clearly the information appears (not a guess).

--- CONTRACT TEXT ---
{contract_text}
--- END ---
"""


def _parse_llm_metadata(raw_json: str) -> Dict[str, Any] | None:
    """Parse and validate the LLM JSON into the metadata dict."""
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    result: Dict[str, Any] = {}
    for field in METADATA_FIELDS:
        entry = data.get(field, {})
        if not isinstance(entry, dict):
            result[field] = {"value": "", "confidence": 0}
            continue
        value = str(entry.get("value", "")).strip()
        confidence = entry.get("confidence", 0)
        try:
            confidence = max(0, min(100, int(confidence)))
        except (ValueError, TypeError):
            confidence = 0
        result[field] = {"value": value, "confidence": confidence}

    return result


def _llm_extract(text: str) -> Dict[str, Any] | None:
    """Extract metadata using Gemini. Returns None on failure."""
    truncated = text[:30_000]
    prompt = _EXTRACTION_PROMPT.format(contract_text=truncated)
    raw = generate_json(prompt)
    if not raw:
        return None
    return _parse_llm_metadata(raw)


# ── Deterministic regex fallback ───────────────────────────────────

_REGEX_PATTERNS: Dict[str, List[str]] = {
    "customer_name": [
        r"customer\s*[:\-]\s*([A-Za-z0-9&.,''\-\s]{3,80})",
        r"client\s*[:\-]\s*([A-Za-z0-9&.,''\-\s]{3,80})",
        r"between\s+([A-Za-z0-9&.,''\-\s]{3,60})\s+(?:and|&)",
    ],
    "vendor_name": [
        r"vendor\s*[:\-]\s*([A-Za-z0-9&.,''\-\s]{3,80})",
        r"supplier\s*[:\-]\s*([A-Za-z0-9&.,''\-\s]{3,80})",
        r"provider\s*[:\-]\s*([A-Za-z0-9&.,''\-\s]{3,80})",
        r"between\s+[A-Za-z0-9&.,''\-\s]{3,60}\s+(?:and|&)\s+([A-Za-z0-9&.,''\-\s]{3,60})",
    ],
    "contract_type": [
        r"(service\s+agreement|consulting\s+agreement|employment\s+agreement|non-?disclosure\s+agreement|NDA|lease\s+agreement|software\s+license)",
    ],
    "effective_date": [
        r"effective\s+(?:date|as\s+of)\s*[:\-]?\s*(\w+\s+\d{1,2},?\s+\d{4})",
        r"commencing\s+on\s+(\w+\s+\d{1,2},?\s+\d{4})",
    ],
    "expiration_date": [
        r"expir(?:es?|ation)\s*(?:date)?\s*[:\-]?\s*(\w+\s+\d{1,2},?\s+\d{4})",
        r"terminat(?:es?|ion)\s+on\s+(\w+\s+\d{1,2},?\s+\d{4})",
    ],
    "payment_terms": [
        r"(net\s*\d{1,3})",
        r"payment\s+within\s+(\d{1,3}\s+days)",
        r"(due\s+on\s+receipt)",
        r"(advance\s+payment)",
    ],
    "billing_cycle": [
        r"(\$\s?[\d,]+(?:\.\d{2})?\s+per\s+(?:month|year|quarter|week))",
        r"billing\s+cycle\s*[:\-]\s*([A-Za-z\s]{3,40})",
        r"(monthly|quarterly|annually|yearly|weekly)\s+billing",
    ],
    "total_value": [
        r"total\s+(?:contract\s+)?value\s*[:\-]?\s*(\$[\d,]+(?:\.\d{2})?)",
        r"(?:amount|sum)\s+of\s+(\$[\d,]+(?:\.\d{2})?)",
    ],
    "renewal_terms": [
        r"([^.\n]{0,80}auto-?renew[^.\n]{0,140})",
        r"([^.\n]{0,80}renewal[^.\n]{0,140})",
        r"([^.\n]{0,80}term\s+of\s+\d+\s+(?:month|year)[^.\n]{0,120})",
    ],
    "governing_law": [
        r"govern(?:ing|ed\s+by)\s+(?:the\s+)?law[s]?\s+of\s+(?:the\s+)?([A-Za-z\s,]{3,60})",
        r"jurisdiction\s+of\s+(?:the\s+)?([A-Za-z\s,]{3,60})",
    ],
}


def _regex_extract(text: str) -> Dict[str, Any]:
    """Lightweight regex-based fallback extraction."""
    result: Dict[str, Any] = {}
    for field, patterns in _REGEX_PATTERNS.items():
        value = ""
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                if match.groups():
                    value = match.group(1).strip(" .,:;\n\t")
                else:
                    value = match.group(0).strip(" .,:;\n\t")
                break
        result[field] = {
            "value": value,
            "confidence": 72 if value else 0,
        }
    return result


# ── Public API ─────────────────────────────────────────────────────

def extract_contract_metadata(text: str) -> Dict[str, Any]:
    """Extract structured metadata from contract text.

    Uses Gemini LLM when available for accurate extraction.
    Falls back to regex patterns when Gemini is unavailable.

    Returns a dict of field_name -> {"value": str, "confidence": int}.
    """
    if not text or not text.strip():
        return dict(_EMPTY_METADATA)

    if gemini_available():
        llm_result = _llm_extract(text)
        if llm_result is not None:
            extracted_count = sum(1 for v in llm_result.values() if v.get("value"))
            logger.info(
                "LLM metadata extraction complete: %d/%d fields extracted.",
                extracted_count,
                len(METADATA_FIELDS),
            )
            return llm_result
        logger.warning("LLM metadata extraction failed — falling back to regex.")

    return _regex_extract(text)


__all__ = ["extract_contract_metadata", "METADATA_FIELDS"]
