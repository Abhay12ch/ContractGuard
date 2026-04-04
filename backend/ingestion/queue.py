"""Background indexing queue for asynchronous embedding/index generation via asyncio."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import asyncio
from typing import Literal

from ..contracts.services import ContractService
from ..core.exceptions import ContractGuardError, IndexingQueueFullError


logger = logging.getLogger("contractguard.ingestion")

IndexingState = Literal["processing", "ready", "failed"]


@dataclass(frozen=True)
class IndexingJobStatus:
    contract_id: str
    status: IndexingState
    embedding_count: int = 0
    error: str | None = None


class IndexingJobQueue:
    """Single-worker queue to build vector indexes outside request threads using asyncio."""

    def __init__(self, contract_service: ContractService, *, max_size: int = 256) -> None:
        self._contract_service = contract_service
        self._max_size = max(1, max_size)
        self._queue: asyncio.Queue[str | object] | None = None
        self._statuses: dict[str, IndexingJobStatus] = {}
        self._lock: asyncio.Lock | None = None
        self._worker_task: asyncio.Task | None = None
        self._sentinel = object()

    def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._max_size)
        if self._lock is None:
            self._lock = asyncio.Lock()
        
        loop = asyncio.get_event_loop()
        self._worker_task = loop.create_task(self._worker_loop())

    def stop(self) -> None:
        if self._worker_task and self._queue:
            try:
                self._queue.put_nowait(self._sentinel)
            except asyncio.QueueFull:
                pass
            self._queue = None
            self._lock = None

    def submit(self, contract_id: str) -> None:
        self._set_status(contract_id, status="processing", embedding_count=0, error=None)
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._max_size)
        try:
            self._queue.put_nowait(contract_id)
        except asyncio.QueueFull as exc:
            self._set_status(
                contract_id,
                status="failed",
                embedding_count=0,
                error="Indexing queue is currently full.",
            )
            raise IndexingQueueFullError(self._queue.maxsize) from exc

    def get_status(self, contract_id: str) -> IndexingJobStatus | None:
        # Dictionary gets are thread-safe enough, but we should use it carefully though it's all in the event-loop thread.
        status = self._statuses.get(contract_id)
        if status is None:
            return None
        return IndexingJobStatus(
            contract_id=status.contract_id,
            status=status.status,
            embedding_count=status.embedding_count,
            error=status.error,
        )

    def _set_status(
        self,
        contract_id: str,
        *,
        status: IndexingState | None = None,
        embedding_count: int | None = None,
        error: str | None = None,
    ) -> None:
        # Dictionary gets are thread-safe enough
        current = self._statuses.get(contract_id, IndexingJobStatus(contract_id, "processing"))
        new_status = current.status if status is None else status
        new_count = current.embedding_count if embedding_count is None else embedding_count
        new_error = error if error is not None else current.error

        self._statuses[contract_id] = IndexingJobStatus(
            contract_id=contract_id,
            status=new_status,
            embedding_count=new_count,
            error=new_error,
        )

    async def _worker_loop(self) -> None:
        while True:
            try:
                item = await self._queue.get()
            except asyncio.CancelledError:
                break
                
            if item is self._sentinel:
                self._queue.task_done()
                break

            contract_id = str(item)
            try:
                vector_store = await self._contract_service.get_or_build_vector_store(contract_id)
                chunks = vector_store.get("chunks", [])
                self._set_status(
                    contract_id,
                    status="ready",
                    embedding_count=len(chunks),
                    error=None,
                )
            except (ContractGuardError, RuntimeError, OSError, ValueError, TypeError, AttributeError) as exc:
                self._set_status(
                    contract_id,
                    status="failed",
                    embedding_count=0,
                    error=str(exc),
                )
                logger.warning("Indexing failed for contract %s: %s", contract_id, exc)
            finally:
                self._queue.task_done()


__all__ = ["IndexingJobQueue", "IndexingJobStatus", "IndexingState"]
