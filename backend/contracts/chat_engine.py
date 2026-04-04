"""Conversational Q&A engine with memory for ContractGuard.

This module handles LLM-powered conversational answering over contract
chunks. It maintains conversation context by accepting chat history
and building multi-turn prompts.

This is completely separate from qa_chain.py which handles the
extractive (non-LLM) fallback path.

Architecture:
    main.py → chat_engine.generate_answer() → gemini_client
                                              ↓ (fallback)
              qa_chain.answer_question()  ← extractive path
"""

from __future__ import annotations

import logging
from typing import Dict, List

from .gemini_client import gemini_available, generate_text

logger = logging.getLogger("contractguard.chat_engine")

# Maximum number of prior turns to include for context
MAX_HISTORY_TURNS = 6

_SYSTEM_PROMPT = """\
You are a contract analysis assistant for ContractGuard. Your role is to
answer questions about a specific contract using the provided contract
chunks as your knowledge base.

Rules:
- Answer ONLY based on the provided contract chunks. Do NOT hallucinate.
- If the answer is not in the chunks, clearly say "I couldn't find that
  information in this contract."
- Be concise, practical, and specific. Cite relevant clauses when useful.
- Use everyday language a non-lawyer can understand.
- When answering follow-up questions, use the conversation history for context.
"""


def _format_history_block(history: List[Dict[str, str]]) -> str:
    """Format chat history into a prompt-friendly string.

    Each history entry should have 'question' and 'answer' keys.
    Only includes the last MAX_HISTORY_TURNS entries.
    """
    if not history:
        return ""

    recent = history[-MAX_HISTORY_TURNS:]
    lines: List[str] = ["Previous conversation:"]
    for turn in recent:
        q = str(turn.get("question", "")).strip()
        a = str(turn.get("answer", "")).strip()
        if q:
            lines.append(f"User: {q}")
        if a:
            # Truncate long answers to save context window
            truncated_a = a[:500] + "..." if len(a) > 500 else a
            lines.append(f"Assistant: {truncated_a}")
    lines.append("")  # Trailing newline
    return "\n".join(lines)


def _format_chunks_block(chunks: List[str]) -> str:
    """Format retrieved chunks into a numbered context block."""
    if not chunks:
        return "No contract context available."

    parts: List[str] = []
    for idx, chunk in enumerate(chunks, 1):
        parts.append(f"[Chunk {idx}]\n{chunk}")
    return "\n\n".join(parts)


def _build_prompt(
    question: str,
    chunks: List[str],
    history: List[Dict[str, str]],
) -> str:
    """Build the full multi-turn prompt for Gemini."""
    history_block = _format_history_block(history)
    chunks_block = _format_chunks_block(chunks)

    prompt_parts = [_SYSTEM_PROMPT]

    if history_block:
        prompt_parts.append(history_block)

    prompt_parts.append(f"Contract Context:\n{chunks_block}")
    prompt_parts.append(f"Current Question: {question}")
    prompt_parts.append("Answer:")

    return "\n\n".join(prompt_parts)


def generate_answer(
    question: str,
    retrieved_chunks: List[str],
    chat_history: List[Dict[str, str]] | None = None,
) -> str:
    """Generate a conversational answer using Gemini with memory.

    Args:
        question: The user's current question.
        retrieved_chunks: Semantically relevant contract chunks.
        chat_history: List of prior {"question": ..., "answer": ...} dicts.

    Returns:
        The answer string. Returns empty string if Gemini is unavailable
        (caller should fall back to qa_chain.answer_question).
    """
    if not question or not question.strip():
        return ""

    if not gemini_available():
        return ""

    if not retrieved_chunks:
        return ""

    history = chat_history or []
    prompt = _build_prompt(question.strip(), retrieved_chunks, history)

    answer = generate_text(prompt)
    if answer:
        logger.info(
            "Chat engine answered with %d history turns, %d chunks.",
            len(history),
            len(retrieved_chunks),
        )
    return answer


def is_available() -> bool:
    """Check if the conversational chat engine is available (Gemini configured)."""
    return gemini_available()


__all__ = ["generate_answer", "is_available"]
