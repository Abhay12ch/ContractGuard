"""Background indexing queue for asynchronous embedding/index generation."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from queue import Empty, Full, Queue
from threading import Event, RLock, Thread
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
    """Single-worker queue to build vector indexes outside request threads."""

    def __init__(self, contract_service: ContractService, *, max_size: int = 256) -> None:
        self._contract_service = contract_service
        self._queue: Queue[object] = Queue(maxsize=max(1, max_size))
        self._statuses: dict[str, IndexingJobStatus] = {}
        self._lock = RLock()
        self._stop_event = Event()
        self._worker_thread: Thread | None = None
        self._sentinel = object()

    def start(self) -> None:
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                return

            self._stop_event.clear()
            self._worker_thread = Thread(
                target=self._worker_loop,
                name="contractguard-indexing-worker",
                daemon=True,
            )
            self._worker_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._queue.put_nowait(self._sentinel)
        except Full:
            pass

        worker = self._worker_thread
        if worker is not None:
            worker.join(timeout=2.0)

        with self._lock:
            self._worker_thread = None

    def submit(self, contract_id: str) -> None:
        self._set_status(contract_id, status="processing", embedding_count=0, error=None)
        try:
            self._queue.put_nowait(contract_id)
        except Full as exc:
            self._set_status(
                contract_id,
                status="failed",
                embedding_count=0,
                error="Indexing queue is currently full.",
            )
            raise IndexingQueueFullError(self._queue.maxsize) from exc

    def get_status(self, contract_id: str) -> IndexingJobStatus | None:
        with self._lock:
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
        status: IndexingState,
        embedding_count: int,
        error: str | None,
    ) -> None:
        with self._lock:
            self._statuses[contract_id] = IndexingJobStatus(
                contract_id=contract_id,
                status=status,
                embedding_count=embedding_count,
                error=error,
            )

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.25)
            except Empty:
                continue

            if item is self._sentinel:
                self._queue.task_done()
                if self._stop_event.is_set():
                    break
                continue

            contract_id = str(item)
            try:
                vector_store = self._contract_service.get_or_build_vector_store(contract_id)
                embedding_count = int(vector_store.get("embedding_count", 0))
                self._set_status(
                    contract_id,
                    status="ready",
                    embedding_count=embedding_count,
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
