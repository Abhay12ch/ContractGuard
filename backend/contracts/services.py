"""Application services for contract ingestion and retrieval lifecycle."""

from __future__ import annotations

import logging
import time
import uuid

from ..api.schemas import UploadResponse
from ..core.exceptions import ContractNotFoundError
from . import embedder as contract_embedder
from .store import InMemoryContractStore


logger = logging.getLogger("contractguard.services")


class ContractService:
    """Service-layer orchestration for contract text/chunk/vector management."""

    def __init__(
        self,
        store: InMemoryContractStore,
        *,
        precompute_embeddings_on_upload: bool = False,
    ) -> None:
        self.store = store
        self.precompute_embeddings_on_upload = precompute_embeddings_on_upload

    def store_contract_and_index(self, text: str, filename: str) -> UploadResponse:
        return self._store_contract(
            text=text,
            filename=filename,
            precompute_embeddings=self.precompute_embeddings_on_upload,
            status="ready",
        )

    def store_contract_without_index(self, text: str, filename: str) -> UploadResponse:
        return self._store_contract(
            text=text,
            filename=filename,
            precompute_embeddings=False,
            status="processing",
        )

    def _store_contract(
        self,
        *,
        text: str,
        filename: str,
        precompute_embeddings: bool,
        status: str,
    ) -> UploadResponse:
        start = time.perf_counter()

        contract_id = str(uuid.uuid4())
        chunks = contract_embedder.chunk_contract_text(text)

        embedding_count = 0
        if precompute_embeddings:
            vector_store = contract_embedder.build_faiss_store(chunks)
            embedding_count = int(vector_store.get("embedding_count", 0))
        else:
            vector_store = {
                "index": None,
                "chunks": chunks,
                "embedding_count": 0,
                "dimension": 0,
            }

        self.store.save_contract(
            contract_id=contract_id,
            text=text,
            chunks=chunks,
            vector_store=vector_store,
        )

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

    def get_contract_text(self, contract_id: str) -> str | None:
        return self.store.get_text(contract_id)

    def require_contract_text(self, contract_id: str) -> str:
        text = self.get_contract_text(contract_id)
        if text is None:
            raise ContractNotFoundError(contract_id)
        return text

    def get_or_build_vector_store(self, contract_id: str) -> dict:
        vector_store = self.store.get_vector_store(contract_id)
        if vector_store:
            has_index = vector_store.get("index") is not None
            has_vectors = vector_store.get("vectors") is not None
            if has_index or has_vectors:
                return vector_store

        if vector_store and vector_store.get("chunks") and int(vector_store.get("embedding_count", 0)) > 0:
            return vector_store

        chunks = self.store.get_chunks(contract_id)
        if chunks is None:
            text = self.require_contract_text(contract_id)
            chunks = contract_embedder.chunk_contract_text(text)
            self.store.set_chunks(contract_id, chunks)

        start = time.perf_counter()
        built_store = contract_embedder.build_faiss_store(chunks)
        self.store.set_vector_store(contract_id, built_store)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "Built vector store lazily for %s in %d ms (chunks=%d)",
            contract_id,
            elapsed_ms,
            len(chunks),
        )

        return built_store


__all__ = ["ContractService"]
