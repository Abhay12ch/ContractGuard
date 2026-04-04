"""Session lifecycle management for ContractGuard chat conversations.

Manages deterministic session IDs so chat history is properly scoped
per contract. Thin layer over MongoDB storage — no AI logic.

Architecture:
    frontend → session_manager.get_or_create_session()
             → session_manager.get_session_history()
             → store.get_chat_history() / store.append_chat()
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger("contractguard.session_manager")


def generate_session_id(contract_id: str, user_id: str = "default") -> str:
    """Generate a deterministic session ID for a (contract, user) pair.

    The session ID is stable: same contract + same user = same session,
    so conversation history persists across page reloads.

    Args:
        contract_id: The contract being discussed.
        user_id: The user identifier (defaults to "default" for single-user).

    Returns:
        A short, deterministic session ID string.
    """
    if not contract_id:
        raise ValueError("contract_id is required for session creation.")

    raw = f"{contract_id}:{user_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def format_history_for_display(
    interactions: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Format raw MongoDB chat interactions for frontend display.

    Args:
        interactions: List of {"question": ..., "answer": ..., "timestamp": ...} dicts.

    Returns:
        Cleaned list suitable for UI rendering.
    """
    display: List[Dict[str, str]] = []
    for entry in interactions:
        q = str(entry.get("question", "")).strip()
        a = str(entry.get("answer", "")).strip()
        if not q:
            continue
        display.append({
            "question": q,
            "answer": a or "No answer generated.",
            "timestamp": str(entry.get("timestamp", "")),
        })
    return display


def timestamp_now() -> str:
    """ISO timestamp for the current moment (UTC)."""
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "generate_session_id",
    "format_history_for_display",
    "timestamp_now",
]
