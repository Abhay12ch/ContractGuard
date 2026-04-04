"""Application services for contract ingestion and retrieval lifecycle."""

from __future__ import annotations

import logging
import time
import uuid
import numpy as np

from ..api.schemas import UploadResponse
from ..core.exceptions import ContractNotFoundError
from . import embedder as contract_embedder
from .store import MongoContractStore


logger = logging.getLogger("contractguard.services")


class ContractService:
    """Service-layer orchestration for contract text/chunk/vector management via MongoDB."""

    def __init__(
        self,
        store: MongoContractStore,
        *,
        precompute_embeddings_on_upload: bool = False,
    ) -> None:
        self.store = store
        self.precompute_embeddings_on_upload = precompute_embeddings_on_upload

    async def store_contract_and_index(self, text: str, filename: str) -> UploadResponse:
        return await self._store_contract(
            text=text,
            filename=filename,
            precompute_embeddings=self.precompute_embeddings_on_upload,
            status="ready",
        )

    async def store_contract_without_index(self, text: str, filename: str) -> UploadResponse:
        return await self._store_contract(
            text=text,
            filename=filename,
            precompute_embeddings=False,
            status="processing",
        )

    async def _store_contract(
        self,
        *,
        text: str,
        filename: str,
        precompute_embeddings: bool,
        status: str,
    ) -> UploadResponse:
        start = time.perf_counter()

        contract_id = str(uuid.uuid4())
        
        # Save textual component first
        await self.store.save_contract(contract_id=contract_id, title=filename, text=text)
        
        chunks = contract_embedder.chunk_contract_text(text)

        embedding_count = 0
        if precompute_embeddings:
            # We must compute embeddings to save to mongo
            # Right now build_faiss_store doesn't return the raw embeddings
            # We'll just build the store lazily. Let's offload FAISS init.
            vector_store = contract_embedder.build_faiss_store(chunks)
            embedding_count = int(vector_store.get("embedding_count", 0))
            # Here we might ideally save the chunks into Mongo 
            await self.store.save_contract_chunks_and_embeddings(
                contract_id, 
                chunks, 
                [], # Empty list for now, we'll reconstruct dynamically if not saved
                vector_store["dimension"]
            )
        else:
            await self.store.save_contract_chunks_and_embeddings(contract_id, chunks, [], 0)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "Stored contract %s in %d ms (chunks=%d, precomputed=%s)",
            contract_id,
            elapsed_ms,
            len(chunks),
            precompute_embeddings,
        )

        preview = text[:300].replace("\n", " ")
        return UploadResponse(
            contract_id=contract_id,
            filename=filename,
            text_preview=preview,
            chunk_count=len(chunks),
            embedding_count=embedding_count,
            status=status,
        )

    async def get_contract_text(self, contract_id: str) -> str | None:
        return await self.store.get_text(contract_id)

    async def require_contract_text(self, contract_id: str) -> str:
        text = await self.get_contract_text(contract_id)
        if text is None:
            raise ContractNotFoundError(contract_id)
        return text

    async def get_or_build_vector_store(self, contract_id: str) -> dict:
        """Hydrates FAISS vector index from Mongo or rebuilds if missing."""
        doc = await self.store.get_contract_data(contract_id)
        if not doc:
            raise ContractNotFoundError(contract_id)
            
        chunks = doc.get("chunks")
        if not chunks:
            text = doc.get("text", "")
            chunks = contract_embedder.chunk_contract_text(text)
            await self.store.save_contract_chunks_and_embeddings(contract_id, chunks, [], 0)

        start = time.perf_counter()
        
        # In a fully robust scenario, we would store and retrieve embeddings directly.
        # For simplicity without breaking the FAISS abstraction in embedder.py,
        # we'll build it using the chunks.
        built_store = contract_embedder.build_faiss_store(chunks)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "Built vector store lazily for %s in %d ms (chunks=%d)",
            contract_id,
            elapsed_ms,
            len(chunks),
        )

        return built_store

__all__ = ["ContractService"]
