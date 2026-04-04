"""MongoDB asynchronous storage primitives for ContractGuard."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("contractguard.store")


class MongoContractStore:
    """MongoDB store for contract text, chunks, embeddings, summaries, and chat history."""

    def __init__(self, uri: str, db_name: str):
        self.uri = uri
        self.db_name = db_name
        self._client = None
        self._db = None

    @property
    def db(self):
        if self._client is None:
            from motor.motor_asyncio import AsyncIOMotorClient
            self._client = AsyncIOMotorClient(self.uri)
            self._db = self._client[self.db_name]
        return self._db

    def close(self) -> None:
        """Close the database client and reset connection state."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

    @property
    def contracts(self): return self.db.contracts
    @property
    def summaries(self): return self.db.summaries
    @property
    def risks(self): return self.db.risks
    @property
    def chat_history(self): return self.db.chat_history
    @property
    def metadata(self): return self.db.metadata

    async def clear_all(self) -> None:
        """Clear the entire database for a new session."""
        await self.contracts.drop()
        await self.summaries.drop()
        await self.risks.drop()
        await self.chat_history.drop()
        await self.metadata.drop()

    async def save_contract(self, contract_id: str, title: str, text: str) -> None:
        """Save basic contract text info without vector data."""
        await self.contracts.update_one(
            {"_id": contract_id},
            {
                "$set": {
                    "title": title, 
                    "text": text,
                    "uploaded_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )

    async def save_contract_chunks_and_embeddings(
        self,
        contract_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        dimension: int
    ) -> None:
        """Save chunk components to avoid re-embedding.
        The numpy array embeddings from FAISS should be converted to lists before passing here.
        """
        await self.contracts.update_one(
            {"_id": contract_id},
            {
                "$set": {
                    "chunks": chunks,
                    "embeddings": embeddings,
                    "dimension": dimension
                }
            },
            upsert=True
        )

    async def get_text(self, contract_id: str) -> str | None:
        doc = await self.contracts.find_one({"_id": contract_id}, {"text": 1})
        return doc.get("text") if doc else None

    async def get_contract_data(self, contract_id: str) -> Dict[str, Any] | None:
        """Returns the full contract document including chunks and embeddings if present."""
        return await self.contracts.find_one({"_id": contract_id})

    async def set_summary(self, contract_id: str, max_chars: int, summary: str) -> None:
        await self.summaries.update_one(
            {"contract_id": contract_id, "max_chars": max_chars},
            {"$set": {"summary": summary}},
            upsert=True
        )

    async def get_summary(self, contract_id: str, max_chars: int) -> str | None:
        doc = await self.summaries.find_one({"contract_id": contract_id, "max_chars": max_chars})
        return doc.get("summary") if doc else None

    async def set_risks(self, contract_id: str, risk_data: dict) -> None:
        await self.risks.update_one(
            {"_id": contract_id},
            {"$set": {"data": risk_data}},
            upsert=True
        )

    async def get_risks(self, contract_id: str) -> dict | None:
        doc = await self.risks.find_one({"_id": contract_id})
        return doc.get("data") if doc else None
        
    # ── Session-aware chat history ──────────────────────────────────

    async def append_chat_interaction(
        self,
        contract_id: str,
        question: str,
        answer: str,
        session_id: str = "",
    ) -> None:
        """Append a Q&A turn, scoped by (contract_id, session_id)."""
        key = {"contract_id": contract_id, "session_id": session_id}
        await self.chat_history.update_one(
            key,
            {
                "$push": {
                    "interactions": {
                        "question": question,
                        "answer": answer,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                }
            },
            upsert=True,
        )

    async def get_chat_history(
        self,
        contract_id: str,
        session_id: str = "",
    ) -> List[dict]:
        """Retrieve chat history for a specific (contract_id, session_id)."""
        key = {"contract_id": contract_id, "session_id": session_id}
        doc = await self.chat_history.find_one(key)
        return doc.get("interactions", []) if doc else []

    async def clear_chat_session(
        self,
        contract_id: str,
        session_id: str = "",
    ) -> None:
        """Clear chat history for a specific (contract_id, session_id)."""
        key = {"contract_id": contract_id, "session_id": session_id}
        await self.chat_history.delete_one(key)

    # ── Metadata storage ─────────────────────────────────────────────

    async def set_metadata(self, contract_id: str, metadata: dict) -> None:
        """Cache extracted metadata for a contract."""
        await self.metadata.update_one(
            {"_id": contract_id},
            {"$set": {"data": metadata}},
            upsert=True,
        )

    async def get_metadata(self, contract_id: str) -> dict | None:
        """Retrieve cached metadata for a contract."""
        doc = await self.metadata.find_one({"_id": contract_id})
        return doc.get("data") if doc else None

    async def list_all_contracts(self) -> List[Dict[str, Any]]:
        """List metadata for all contracts in the database."""
        cursor = self.contracts.find({}, {"title": 1, "uploaded_at": 1, "_id": 1}).sort("uploaded_at", -1)
        contracts = []
        async for doc in cursor:
            contracts.append({
                "contract_id": doc["_id"],
                "title": doc.get("title", "Untitled"),
                "uploaded_at": doc.get("uploaded_at", "")
            })
        return contracts

__all__ = ["MongoContractStore"]
