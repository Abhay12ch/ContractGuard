"""Retrieval-based Q&A over contract content.

This module currently uses a lightweight extractive strategy over retrieved
chunks. It can be swapped later with an LLM answer chain.
"""

import os
from typing import List
import re


def _tokenize(text: str) -> List[str]:
    return [tok for tok in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(tok) > 2]


def _score_line(line: str, query_tokens: List[str]) -> int:
    line_tokens = set(_tokenize(line))
    return sum(1 for token in query_tokens if token in line_tokens)


RISK_KEYWORDS = {
    "liability": ["liability", "liable", "damages", "indemn"],
    "termination": ["termination", "terminate", "early exit", "cancellation"],
    "penalty": ["penalty", "fee", "fine", "charge"],
    "auto_renewal": ["auto renewal", "renews automatically", "renewal"],
    "non_compete": ["non-compete", "non compete", "restrictive covenant", "restraint"],
    "payment": ["payment", "invoice", "schedule", "due date"],
}


def _detect_risk_type(text: str) -> str:
    hay = text.lower()
    for risk_type, words in RISK_KEYWORDS.items():
        if any(word in hay for word in words):
            return risk_type
    return "general"


def _risk_label(risk_type: str) -> str:
    labels = {
        "liability": "High",
        "termination": "High",
        "penalty": "High",
        "auto_renewal": "Medium",
        "non_compete": "Medium",
        "payment": "Low",
        "general": "Medium",
    }
    return labels.get(risk_type, "Medium")


def _format_bullet_answer(question: str, ranked_lines: List[str]) -> str:
    """Format a concise, hackathon-friendly response with structured bullets."""
    top_lines = ranked_lines[:3]
    bullets: List[str] = []

    for line in top_lines:
        risk_type = _detect_risk_type(line)
        label = _risk_label(risk_type)
        risk_name = risk_type.replace("_", " ").title()
        bullets.append(
            f"- Risk type: {risk_name} ({label})\n"
            f"  Clause evidence: {line}\n"
            f"  Why it matters: This clause may create {label.lower()} legal/financial exposure."
        )

    header = f"Question: {question}\nTop findings:"
    return header + "\n" + "\n".join(bullets)


def _generate_with_gemini(question: str, retrieved_chunks: List[str]) -> str:
    """Generate an answer using Gemini with retrieved chunks as context.

    Returns an empty string when Gemini is unavailable or not configured.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    try:
        import google.generativeai as genai
    except Exception:
        return ""

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        context = "\n\n".join(
            [f"Clause Chunk {idx + 1}:\n{chunk}" for idx, chunk in enumerate(retrieved_chunks)]
        )
        prompt = (
            "You are a contract analysis assistant. "
            "Answer the user's question only using the provided contract chunks. "
            "If the answer is not present, clearly say so. "
            "Be concise and practical.\n\n"
            f"Question:\n{question}\n\n"
            f"Contract Chunks:\n{context}\n"
        )
        response = model.generate_content(prompt)
        text = getattr(response, "text", "")
        return text.strip()
    except Exception:
        return ""


def answer_question(question: str, retrieved_chunks: List[str]) -> str:
    """Generate an answer from retrieved chunks.

    The function selects the most relevant lines from retrieval results and
    synthesizes a concise response. If configured, Gemini is used first.
    """
    if not retrieved_chunks:
        return "I could not find relevant clauses for that question in the contract."

    llm_answer = _generate_with_gemini(question, retrieved_chunks)
    if llm_answer:
        return llm_answer

    query_tokens = _tokenize(question)
    candidate_lines: List[str] = []
    for chunk in retrieved_chunks:
        for raw_line in re.split(r"[\n\r]+", chunk):
            line = raw_line.strip()
            if len(line) >= 20:
                candidate_lines.append(line)

    if not candidate_lines:
        return "I found related content, but not enough detail to answer clearly."

    ranked = sorted(
        candidate_lines,
        key=lambda line: (_score_line(line, query_tokens), len(line)),
        reverse=True,
    )
    return _format_bullet_answer(question, ranked)
