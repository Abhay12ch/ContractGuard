"""LLM-powered contract summarisation for ContractGuard.

Generates concise, plain-language summaries using Gemini.
Falls back to a naive first-N-characters extraction when the LLM is
unavailable, so the API never breaks.
"""

from __future__ import annotations

import logging
from typing import List

from .gemini_client import gemini_available, generate_text

logger = logging.getLogger("contractguard.summarizer")

_SUMMARY_SYSTEM_PROMPT = """\
You are a senior legal analyst AI. Summarise the following contract in plain English.

Your output MUST follow this exact structure:

**Contract Type:** <one-line description of what kind of contract this is>

**Parties Involved:** <list the parties>

**Key Terms:**
- <bullet 1>
- <bullet 2>
- <bullet 3>
(add more bullets only if genuinely important)

**Important Dates & Deadlines:** <any dates, durations, renewal periods>

**Notable Risks or Concerns:** <anything a signer should watch out for>

Rules:
- Be concise — no more than 250 words total.
- Use everyday language a non-lawyer can understand.
- If a section has no relevant information, write "None identified."
- Do NOT hallucinate facts. Only state what is in the contract text.
"""


def _fallback_summary(text: str, max_chars: int) -> str:
    """Deterministic first-N-chars extraction used when Gemini is unavailable."""
    clamped = max(100, min(max_chars, 2000))
    return text[:clamped]


def summarize_contract(text: str, *, max_chars: int = 600) -> str:
    """Return a concise summary of the contract.

    Tries Gemini first; falls back to naive truncation if unavailable.
    """
    if not text or not text.strip():
        return "No contract text provided."

    if not gemini_available():
        logger.info("Gemini unavailable — using fallback summary (first %d chars).", max_chars)
        return _fallback_summary(text, max_chars)

    # Cap input to ~30 000 chars to stay within context limits comfortably.
    truncated_text = text[:30_000]

    prompt = f"{_SUMMARY_SYSTEM_PROMPT}\n\n--- CONTRACT TEXT ---\n{truncated_text}\n--- END ---"

    result = generate_text(prompt)
    if result:
        return result

    logger.warning("Gemini returned empty summary — falling back to truncation.")
    return _fallback_summary(text, max_chars)


__all__ = ["summarize_contract"]
