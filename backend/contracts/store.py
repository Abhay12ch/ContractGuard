"""Thread-safe in-memory storage primitives for contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List


@dataclass
class InMemoryContractStore:
    """In-memory store for contract text, chunks, and vector stores."""

    contract_text: Dict[str, str] = field(default_factory=dict)
    contract_chunks: Dict[str, List[str]] = field(default_factory=dict)
    contract_vector_stores: Dict[str, dict] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def save_contract(self, contract_id: str, text: str, chunks: List[str], vector_store: dict) -> None:
        with self._lock:
            self.contract_text[contract_id] = text
            self.contract_chunks[contract_id] = list(chunks)
            self.contract_vector_stores[contract_id] = dict(vector_store)

    def get_text(self, contract_id: str) -> str | None:
        with self._lock:
            return self.contract_text.get(contract_id)

    def get_chunks(self, contract_id: str) -> List[str] | None:
        with self._lock:
            chunks = self.contract_chunks.get(contract_id)
            return list(chunks) if chunks is not None else None

    def set_chunks(self, contract_id: str, chunks: List[str]) -> None:
        with self._lock:
            self.contract_chunks[contract_id] = list(chunks)

    def get_vector_store(self, contract_id: str) -> dict | None:
        with self._lock:
            vector_store = self.contract_vector_stores.get(contract_id)
            return dict(vector_store) if vector_store is not None else None

    def set_vector_store(self, contract_id: str, vector_store: dict) -> None:
        with self._lock:
            self.contract_vector_stores[contract_id] = dict(vector_store)


__all__ = ["InMemoryContractStore"]
