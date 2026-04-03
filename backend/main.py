"""FastAPI entrypoint for ContractGuard.

API surface:
- POST /upload   : upload a contract (PDF/DOCX), returns contract_id
- POST /summary  : get plain-language summary
- POST /risks    : get risky clauses + risk score
- POST /ask      : ask a question about a contract
- POST /compare  : compare two uploaded contracts
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from .api.errors import to_http_exception
from .api.schemas import (
    ContractStatusResponse,
    CompareRequest,
    CompareResponse,
    IngestTextRequest,
    QARequest,
    QAResponse,
    RisksRequest,
    RisksResponse,
    SummaryRequest,
    SummaryResponse,
    UploadResponse,
)
from .contracts.analyzer import analyze_contract
from .contracts.comparator import compare_contracts
from .contracts.embedder import retrieve_relevant_chunks, warmup_embedder
from .contracts.parser import extract_text_from_file
from .contracts.qa_chain import answer_question
from .contracts.services import ContractService
from .contracts.store import InMemoryContractStore
from .core.config import settings
from .core.exceptions import (
    ContractGuardError,
    ContractNotFoundError,
    ContractStorageError,
    EmptyContractTextError,
    IndexingFailedError,
    IndexingInProgressError,
)
from .core.logging_config import configure_logging
from .ingestion.queue import IndexingJobQueue
from .ingestion.upload_validation import validate_upload_payload


configure_logging(settings)
logger = logging.getLogger("contractguard.api")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Application lifespan hooks for startup/shutdown tasks."""
    if settings.async_indexing_enabled:
        indexing_queue.start()

    if settings.prewarm_embedder_on_startup:
        try:
            loaded = await run_in_threadpool(warmup_embedder)
            if loaded:
                logger.info("Embedder prewarm complete.")
            else:
                logger.info("Embedder prewarm skipped (no active embedding backend warmed).")
        except (RuntimeError, OSError, ValueError) as exc:  # pragma: no cover - defensive startup logging
            logger.warning("Embedder prewarm failed during startup: %s", exc)

    try:
        yield
    finally:
        if settings.async_indexing_enabled:
            indexing_queue.stop()


app = FastAPI(title=settings.app_name, lifespan=_lifespan)

store = InMemoryContractStore()
contract_service = ContractService(
    store,
    precompute_embeddings_on_upload=settings.precompute_embeddings_on_upload,
)
indexing_queue = IndexingJobQueue(
    contract_service,
    max_size=settings.indexing_queue_max_size,
)


def _cleanup_temp_file(tmp_path: Path) -> None:
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to remove temp file: %s", tmp_path)


def _get_contract_text(contract_id: str) -> str:
    try:
        return contract_service.require_contract_text(contract_id)
    except ContractNotFoundError as exc:
        raise to_http_exception(exc) from exc


def _clamp_summary_chars(requested: int) -> int:
    return max(settings.summary_min_chars, min(requested, settings.summary_max_chars))


def _submit_indexing_job(contract_id: str) -> None:
    if settings.async_indexing_enabled:
        indexing_queue.submit(contract_id)


def _contract_status(contract_id: str) -> ContractStatusResponse:
    status_record = indexing_queue.get_status(contract_id) if settings.async_indexing_enabled else None
    if status_record is not None:
        return ContractStatusResponse(
            contract_id=contract_id,
            status=status_record.status,
            embedding_count=status_record.embedding_count,
            error=status_record.error,
        )

    vector_store = store.get_vector_store(contract_id) or {}
    embedding_count = int(vector_store.get("embedding_count", 0))
    status = "ready" if embedding_count > 0 else "processing"
    return ContractStatusResponse(
        contract_id=contract_id,
        status=status,
        embedding_count=embedding_count,
        error=None,
    )


def _extract_text_from_upload_bytes(filename: str, contents: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = Path(tmp.name)
    except OSError as exc:
        raise ContractStorageError(filename) from exc

    try:
        return extract_text_from_file(str(tmp_path))
    finally:
        _cleanup_temp_file(tmp_path)


@app.get("/", summary="Health check")
def root() -> dict:
    return {"message": "ContractGuard backend is running"}


@app.post("/upload", responses={400: {"description": "Invalid file upload request"}})
async def upload_contract(file: Annotated[UploadFile, File(...)]) -> UploadResponse:
    """Upload a contract file (PDF/DOCX) and return a contract_id."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    contents = await file.read()

    try:
        await run_in_threadpool(
            validate_upload_payload,
            filename=file.filename,
            content_type=file.content_type,
            contents=contents,
            max_bytes=settings.upload_max_bytes,
        )
        text = await run_in_threadpool(_extract_text_from_upload_bytes, file.filename, contents)
    except ContractGuardError as exc:
        logger.warning("Upload parse failed for %s: %s", file.filename, exc)
        raise to_http_exception(exc) from exc

    if not text or not text.strip():
        raise to_http_exception(EmptyContractTextError(file.filename))

    try:
        if settings.async_indexing_enabled:
            response = await run_in_threadpool(
                contract_service.store_contract_without_index,
                text,
                file.filename,
            )
            await run_in_threadpool(_submit_indexing_job, response.contract_id)
            return response

        return await run_in_threadpool(
            contract_service.store_contract_and_index,
            text,
            file.filename,
        )
    except ContractGuardError as exc:
        logger.warning("Upload indexing setup failed for %s: %s", file.filename, exc)
        raise to_http_exception(exc) from exc


@app.post("/ingest-text", responses={400: {"description": "Invalid text ingest payload"}})
async def ingest_text(payload: IngestTextRequest) -> UploadResponse:
    """Ingest plain contract text directly without file upload."""
    raw_text = payload.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Text input cannot be empty")

    filename = payload.title.strip() or "Pasted Contract Text"
    try:
        if settings.async_indexing_enabled:
            response = await run_in_threadpool(
                contract_service.store_contract_without_index,
                raw_text,
                filename,
            )
            await run_in_threadpool(_submit_indexing_job, response.contract_id)
            return response

        return await run_in_threadpool(
            contract_service.store_contract_and_index,
            raw_text,
            filename,
        )
    except ContractGuardError as exc:
        raise to_http_exception(exc) from exc


@app.get("/contracts/{contract_id}/status")
async def get_contract_status(contract_id: str) -> ContractStatusResponse:
    _ = _get_contract_text(contract_id)
    return _contract_status(contract_id)


@app.post("/summary")
async def generate_summary(payload: SummaryRequest) -> SummaryResponse:
    """Return a lightweight heuristic summary (first N chars)."""
    text = _get_contract_text(payload.contract_id)
    max_chars = _clamp_summary_chars(payload.max_chars)
    return SummaryResponse(contract_id=payload.contract_id, summary=text[:max_chars])


@app.post("/risks")
async def get_risks(payload: RisksRequest) -> RisksResponse:
    """Return detected risky clauses + Contract Risk Score."""
    text = _get_contract_text(payload.contract_id)
    result = await run_in_threadpool(analyze_contract, text)

    safety_score = int(result.get("safety_score", result.get("risk_score", 0)))
    risk_score = int(result.get("risk_score", safety_score))
    risk_level = str(result.get("risk_level", "Unknown"))
    detected_clause_count = int(result.get("detected_clause_count", len(result.get("risks", []))))
    risks = result.get("risks", [])

    return RisksResponse(
        contract_id=payload.contract_id,
        risk_score=risk_score,
        safety_score=safety_score,
        risk_level=risk_level,
        detected_clause_count=detected_clause_count,
        risks=risks,
    )


@app.post("/ask")
async def ask_question(payload: QARequest) -> QAResponse:
    """Interactive Q&A over a single contract."""
    _ = _get_contract_text(payload.contract_id)

    if settings.async_indexing_enabled:
        contract_status = _contract_status(payload.contract_id)
        if contract_status.status == "processing":
            raise to_http_exception(IndexingInProgressError(payload.contract_id))
        if contract_status.status == "failed":
            raise to_http_exception(IndexingFailedError(payload.contract_id, contract_status.error))

    vector_store = await run_in_threadpool(
        contract_service.get_or_build_vector_store,
        payload.contract_id,
    )

    retrieved_chunks = await run_in_threadpool(
        retrieve_relevant_chunks,
        payload.question,
        vector_store,
        payload.top_k,
    )
    answer = await run_in_threadpool(answer_question, payload.question, retrieved_chunks)

    return QAResponse(
        contract_id=payload.contract_id,
        question=payload.question,
        answer=answer,
        retrieved_chunks_count=len(retrieved_chunks),
    )


@app.post("/compare")
async def compare(payload: CompareRequest) -> CompareResponse:
    """Compare two uploaded contracts."""
    text_a = _get_contract_text(payload.contract_id_a)
    text_b = _get_contract_text(payload.contract_id_b)

    result = await run_in_threadpool(compare_contracts, text_a, text_b)
    result = result or {}

    return CompareResponse(
        contract_id_a=payload.contract_id_a,
        contract_id_b=payload.contract_id_b,
        summary=result.get("summary", "Comparison not implemented yet"),
        details=result,
    )
