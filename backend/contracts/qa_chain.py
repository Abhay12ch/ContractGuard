"""Retrieval-based Q&A over contract content.

This module currently uses a lightweight extractive strategy over retrieved
chunks. It can be swapped later with an LLM answer chain.
"""

import os
from typing import List
import re
import importlib


def _normalize_token(token: str) -> str:
    token = token.lower()
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for raw in re.findall(r"[a-zA-Z0-9]+", text):
        normalized = _normalize_token(raw)
        if len(normalized) > 2:
            tokens.append(normalized)
    return tokens


QUERY_EXPANSIONS = {
    "obligation": ["shall", "must", "will", "pay", "payment", "deliver", "provide", "within"],
    "duty": ["shall", "must", "will", "pay", "deliver", "provide"],
    "remedy": ["dispute", "settlement", "penalty", "damages", "termination", "breach", "compensation"],
    "dispute": ["settlement", "arbitration", "court", "boundary", "penalty", "damages"],
    "liability": ["liable", "damages", "indemnify", "limitation"],
    "payment": ["pay", "invoice", "schedule", "due", "amount"],
    "termination": ["terminate", "termination", "notice", "penalty"],
}


OBLIGATION_MARKERS = {
    "shall",
    "must",
    "will",
    "pay",
    "payment",
    "due",
    "provide",
    "deliver",
    "within",
    "agree",
    "divided",
    "demarcated",
}


REMEDY_MARKERS = {
    "dispute",
    "settlement",
    "penalty",
    "damages",
    "termination",
    "breach",
    "liable",
    "liability",
    "arbitration",
    "court",
    "refund",
}


def _expand_query_tokens(query_tokens: List[str]) -> List[str]:
    expanded = set(query_tokens)
    for token in query_tokens:
        extras = QUERY_EXPANSIONS.get(token, [])
        for extra in extras:
            expanded.add(_normalize_token(extra))
    return list(expanded)


def _score_line(line: str, query_tokens: List[str]) -> int:
    line_tokens = set(_tokenize(line))
    overlap = sum(1 for token in query_tokens if token in line_tokens)
    if overlap == 0:
        return 0
    # Prefer lines that are slightly more descriptive when overlap ties.
    return overlap * 2 + (1 if len(line) >= 40 else 0)


def _extract_candidate_lines(chunks: List[str]) -> List[str]:
    candidates: List[str] = []
    for chunk in chunks:
        for raw_line in re.split(r"[\n\r]+|(?<=[\.;:!?])\s+(?=[A-Z0-9\-])", chunk):
            line = raw_line.strip(" -\t")
            if len(line) >= 20:
                candidates.append(line)
    return candidates


def _dedupe_preserve_order(lines: List[str]) -> List[str]:
    seen = set()
    deduped: List[str] = []
    for line in lines:
        key = line.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def _pick_lines_by_markers(lines: List[str], markers: set[str], limit: int = 2) -> List[str]:
    picked: List[str] = []
    for line in lines:
        line_tokens = set(_tokenize(line))
        if line_tokens.intersection(markers):
            picked.append(line)
        if len(picked) >= limit:
            break
    return picked


def _format_extractive_answer(question: str, ranked_lines: List[str], query_tokens: List[str]) -> str:
    deduped_ranked = _dedupe_preserve_order(ranked_lines)
    if not deduped_ranked:
        return "I found related content, but not enough detail to answer clearly."

    asks_obligations = any(token in {"obligation", "duty", "must", "shall"} for token in query_tokens)
    asks_remedies = any(token in {"remedy", "dispute", "breach", "penalty", "damages"} for token in query_tokens)

    sections: List[str] = []
    used_lines: set[str] = set()

    if asks_obligations:
        obligations = _pick_lines_by_markers(deduped_ranked, OBLIGATION_MARKERS, limit=2)
        if obligations:
            used_lines.update(line.lower() for line in obligations)
            sections.append("Obligations found:\n" + "\n".join(f"- {line}" for line in obligations))

    if asks_remedies:
        remedy_pool = [line for line in deduped_ranked if line.lower() not in used_lines]
        remedies = _pick_lines_by_markers(remedy_pool, REMEDY_MARKERS, limit=2)
        if remedies:
            used_lines.update(line.lower() for line in remedies)
            sections.append("Remedies / dispute handling found:\n" + "\n".join(f"- {line}" for line in remedies))

    if not sections:
        top_lines = deduped_ranked[:3]
        sections.append("Most relevant clauses:\n" + "\n".join(f"- {line}" for line in top_lines))

    return (
        f"Question: {question}\n"
        "Answer (grounded in uploaded contract text):\n"
        + "\n\n".join(sections)
    )


def _generate_with_gemini(question: str, retrieved_chunks: List[str]) -> str:
    """Generate an answer using Gemini with retrieved chunks as context.

    Returns an empty string when Gemini is unavailable or not configured.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    try:
        genai_mod = importlib.import_module("google.genai")
    except ImportError:
        return ""

    try:
        client = genai_mod.Client(api_key=api_key)
        model_name = os.getenv("GEMINI_QA_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"

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
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        text = getattr(response, "text", "")
        return text.strip()
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
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

    query_tokens = _expand_query_tokens(_tokenize(question))
    candidate_lines = _extract_candidate_lines(retrieved_chunks)

    if not candidate_lines:
        return "I found related content, but not enough detail to answer clearly."

    scored_lines = sorted(
        candidate_lines,
        key=lambda line: (_score_line(line, query_tokens), len(line)),
        reverse=True,
    )

    # If token overlap is too weak, still provide deterministic evidence lines.
    if _score_line(scored_lines[0], query_tokens) == 0:
        scored_lines = sorted(candidate_lines, key=len, reverse=True)

    return _format_extractive_answer(question, scored_lines, query_tokens)


__all__ = ["answer_question"]
