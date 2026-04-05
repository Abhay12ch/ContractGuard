"""FastAPI entrypoint for ContractGuard.

API surface:
- POST /upload   : upload a contract (PDF/DOCX, or image when OCR enabled)
- POST /summary  : get plain-language summary
- POST /risks    : get risky clauses + risk score
- POST /ask      : ask a question about a contract
- POST /compare  : compare two uploaded contracts
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import tempfile
from pathlib import Path
from typing import Annotated, Any, Dict

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from .api.errors import to_http_exception
from .api.schemas import (
    ContractListItem,
    ContractListResponse,
    ContractStatusResponse,
    CompareRequest,
    CompareResponse,
    IngestTextRequest,
    MetadataRequest,
    MetadataResponse,
    QARequest,
    QAResponse,
    RisksRequest,
    RisksResponse,
    SummaryRequest,
    SummaryResponse,
    UploadResponse,
    VendorVerifyRequest,
    VendorVerifyResponse,
    ZohoSignatureRequest,
    ZohoSignatureResponse,
    ZohoAuditTrailResponse,
)
from .contracts.analyzer import analyze_contract
from .contracts.chat_engine import generate_answer as chat_generate_answer, is_available as chat_engine_available
from .contracts.comparator import compare_contracts
from .contracts.embedder import retrieve_relevant_chunks, warmup_embedder
from .contracts.metadata_extractor import extract_contract_metadata
from .contracts.parser import extract_text_from_file
from .contracts.qa_chain import answer_question
from .contracts.services import ContractService
from .contracts.session_manager import generate_session_id
from .contracts.summarizer import summarize_contract
from .contracts.vendor_verifier import verify_vendor
from .contracts.zoho_sign import zoho_configured, verify_signature as zoho_verify_signature, get_audit_trail as zoho_get_audit_trail

from .contracts.store import MongoContractStore
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

store = MongoContractStore(settings.mongo_uri, settings.mongo_db_name)
contract_service = ContractService(
    store,
    precompute_embeddings_on_upload=settings.precompute_embeddings_on_upload,
)
indexing_queue = IndexingJobQueue(
    contract_service,
    max_size=settings.indexing_queue_max_size,
)

# ── In-memory cache (eliminates MongoDB round-trips for cached data) ────
_mem_cache: Dict[str, Dict[str, Any]] = {}
# Structure: { contract_id: { "text": str, "filename": str, "summary": {max_chars: str}, "risks": dict, "metadata": dict, "vector_store": dict } }

def _cache_get(contract_id: str, key: str) -> Any:
    return _mem_cache.get(contract_id, {}).get(key)

def _cache_set(contract_id: str, key: str, value: Any) -> None:
    if contract_id not in _mem_cache:
        _mem_cache[contract_id] = {}
    _mem_cache[contract_id][key] = value


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Application lifespan hooks for startup/shutdown tasks."""
    if settings.ocr_enabled:
        logger.info(
            "OCR enabled via Ollama model=%s at %s",
            settings.ollama_ocr_model,
            settings.ollama_base_url,
        )

    if settings.async_indexing_enabled:
        indexing_queue.start()

    # Verify MongoDB connection
    try:
        await store.db.command("ping")
        logger.info("Connected to MongoDB Atlas successfully.")
    except Exception as exc:
        logger.error("Failed to connect to MongoDB: %s", exc)

    if settings.prewarm_embedder_on_startup:
        try:
            loaded = await run_in_threadpool(warmup_embedder)
            if loaded:
                logger.info("Embedder prewarm complete.")
            else:
                logger.info("Embedder prewarm skipped (no active embedding backend warmed).")
        except (RuntimeError, OSError, ValueError) as exc:  # pragma: no cover
            logger.warning("Embedder prewarm failed during startup: %s", exc)

    try:
        yield
    finally:
        if settings.async_indexing_enabled:
            indexing_queue.stop()
        store.close()


app = FastAPI(title=settings.app_name, lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins, adjust if needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/contracts", response_model=ContractListResponse)
async def list_contracts():
    """List all contracts available in the database."""
    try:
        # Build list from memory cache first (instant)
        mem_contracts: list[ContractListItem] = []
        for cid, data in _mem_cache.items():
            if "text" in data:
                mem_contracts.append(
                    ContractListItem(
                        contract_id=cid,
                        title=data.get("filename", "Untitled"),
                        uploaded_at=data.get("uploaded_at") or "",
                    )
                )
        if mem_contracts:
            # Also try MongoDB for contracts not in memory, but don't block if it fails
            try:
                db_rows = await store.list_all_contracts()
                mem_ids = {c.contract_id for c in mem_contracts}
                for row in db_rows:
                    rid = row["contract_id"] if isinstance(row, dict) else row.contract_id
                    if rid not in mem_ids:
                        if isinstance(row, dict):
                            mem_contracts.append(ContractListItem(**row))
                        else:
                            mem_contracts.append(row)
            except Exception:
                pass  # MongoDB unreachable, just use memory
            return ContractListResponse(contracts=mem_contracts)

        # No memory cache, fall back to MongoDB
        db_rows = await store.list_all_contracts()
        items = [ContractListItem(**r) if isinstance(r, dict) else r for r in db_rows]
        return ContractListResponse(contracts=items)
    except Exception as exc:
        logger.exception("Failed to list contracts: %s", exc)
        # Return empty instead of 500 when MongoDB is down
        return ContractListResponse(contracts=[])


def _cleanup_temp_file(tmp_path: Path) -> None:
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to remove temp file: %s", tmp_path)


async def _get_contract_text(contract_id: str) -> str:
    # Try in-memory cache first (instant, no MongoDB)
    cached_text = _cache_get(contract_id, "text")
    if cached_text:
        return cached_text
    try:
        text = await contract_service.require_contract_text(contract_id)
        _cache_set(contract_id, "text", text)  # Cache for future
        return text
    except ContractNotFoundError as exc:
        raise to_http_exception(exc) from exc


def _clamp_summary_chars(requested: int) -> int:
    return max(settings.summary_min_chars, min(requested, settings.summary_max_chars))


def _submit_indexing_job(contract_id: str) -> None:
    if settings.async_indexing_enabled:
        indexing_queue.submit(contract_id)


async def _contract_status(contract_id: str) -> ContractStatusResponse:
    status_record = indexing_queue.get_status(contract_id) if settings.async_indexing_enabled else None
    if status_record is not None:
        return ContractStatusResponse(
            contract_id=contract_id,
            status=status_record.status,
            embedding_count=status_record.embedding_count,
            error=status_record.error,
        )

    # If contract is in memory, it's ready
    if _cache_get(contract_id, "text"):
        return ContractStatusResponse(
            contract_id=contract_id,
            status="ready",
            embedding_count=0,
            error=None,
        )

    # Fall back to MongoDB
    try:
        doc = await store.get_contract_data(contract_id)
        chunks = doc.get("chunks", []) if doc else []
        embedding_count = len(chunks) if chunks else 0
        status = "ready" if embedding_count > 0 else "processing"
        return ContractStatusResponse(
            contract_id=contract_id,
            status=status,
            embedding_count=embedding_count,
            error=None,
        )
    except Exception:
        # MongoDB unreachable but contract is known
        return ContractStatusResponse(
            contract_id=contract_id,
            status="ready",
            embedding_count=0,
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
    """Upload a contract file and return a contract_id."""
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
            allow_images=settings.ocr_enabled,
        )
        text = await run_in_threadpool(_extract_text_from_upload_bytes, file.filename, contents)
    except ContractGuardError as exc:
        logger.warning("Upload parse failed for %s: %s", file.filename, exc)
        raise to_http_exception(exc) from exc

    if not text or not text.strip():
        raise to_http_exception(EmptyContractTextError(file.filename))

    try:
        if settings.async_indexing_enabled:
            response = await contract_service.store_contract_without_index(text, file.filename)
            await run_in_threadpool(_submit_indexing_job, response.contract_id)
        else:
            response = await contract_service.store_contract_and_index(text, file.filename)

        # Seed in-memory cache immediately so subsequent calls are instant
        _cache_set(response.contract_id, "text", text)
        _cache_set(response.contract_id, "filename", file.filename)
        _cache_set(response.contract_id, "uploaded_at", datetime.now(timezone.utc).isoformat())
        return response
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
            response = await contract_service.store_contract_without_index(raw_text, filename)
            await run_in_threadpool(_submit_indexing_job, response.contract_id)
        else:
            response = await contract_service.store_contract_and_index(raw_text, filename)

        # Seed in-memory cache
        _cache_set(response.contract_id, "text", raw_text)
        _cache_set(response.contract_id, "filename", filename)
        _cache_set(response.contract_id, "uploaded_at", datetime.now(timezone.utc).isoformat())
        return response
    except ContractGuardError as exc:
        raise to_http_exception(exc) from exc


@app.get("/contracts/{contract_id}/status")
async def get_contract_status(contract_id: str) -> ContractStatusResponse:
    _ = await _get_contract_text(contract_id)
    return await _contract_status(contract_id)


@app.post("/summary")
async def generate_summary(payload: SummaryRequest) -> SummaryResponse:
    """Return an AI-generated plain-language summary of the contract."""
    text = await _get_contract_text(payload.contract_id)
    max_chars = _clamp_summary_chars(payload.max_chars)

    # 1. Try in-memory cache (instant)
    cache_key = f"summary_{max_chars}"
    cached = _cache_get(payload.contract_id, cache_key)
    if cached:
        return SummaryResponse(contract_id=payload.contract_id, summary=cached)

    # 2. Try MongoDB cache
    try:
        cached_summary = await store.get_summary(payload.contract_id, max_chars)
        if cached_summary:
            _cache_set(payload.contract_id, cache_key, cached_summary)
            return SummaryResponse(contract_id=payload.contract_id, summary=cached_summary)
    except Exception:
        pass  # MongoDB unreachable, skip

    # 3. Compute fresh
    summary = await run_in_threadpool(summarize_contract, text, max_chars=max_chars)
    _cache_set(payload.contract_id, cache_key, summary)
    try:
        await store.set_summary(payload.contract_id, max_chars, summary)
    except Exception:
        pass  # Save to MongoDB best-effort
    return SummaryResponse(contract_id=payload.contract_id, summary=summary)


@app.post("/risks")
async def get_risks(payload: RisksRequest) -> RisksResponse:
    """Return detected risky clauses + Contract Risk Score."""
    text = await _get_contract_text(payload.contract_id)

    # 1. Try in-memory cache (instant)
    cached = _cache_get(payload.contract_id, "risks")
    if cached:
        result = cached
    else:
        # 2. Try MongoDB cache
        result = None
        try:
            result = await store.get_risks(payload.contract_id)
        except Exception:
            pass  # MongoDB unreachable

        # 3. Compute fresh
        if not result:
            result = await run_in_threadpool(analyze_contract, text)
            try:
                await store.set_risks(payload.contract_id, result)
            except Exception:
                pass

        _cache_set(payload.contract_id, "risks", result)

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


@app.post("/extract-metadata")
async def extract_metadata(payload: MetadataRequest) -> MetadataResponse:
    """Extract structured metadata (parties, dates, payment terms, etc.) from a contract."""
    text = await _get_contract_text(payload.contract_id)

    # 1. Try in-memory cache (instant)
    cached_mem = _cache_get(payload.contract_id, "metadata")
    if cached_mem:
        return MetadataResponse(contract_id=payload.contract_id, metadata=cached_mem)

    # 2. Try MongoDB cache
    try:
        cached = await store.get_metadata(payload.contract_id)
        if cached:
            _cache_set(payload.contract_id, "metadata", cached)
            return MetadataResponse(contract_id=payload.contract_id, metadata=cached)
    except Exception:
        pass

    # 3. Compute fresh
    metadata = await run_in_threadpool(extract_contract_metadata, text)
    _cache_set(payload.contract_id, "metadata", metadata)
    try:
        await store.set_metadata(payload.contract_id, metadata)
    except Exception:
        pass
    return MetadataResponse(contract_id=payload.contract_id, metadata=metadata)


@app.post("/ask")
async def ask_question(payload: QARequest) -> QAResponse:
    """Interactive Q&A over a single contract with conversation memory."""
    _ = await _get_contract_text(payload.contract_id)

    if settings.async_indexing_enabled:
        contract_status = await _contract_status(payload.contract_id)
        if contract_status.status == "processing":
            raise to_http_exception(IndexingInProgressError(payload.contract_id))
        if contract_status.status == "failed":
            raise to_http_exception(IndexingFailedError(payload.contract_id, contract_status.error))

    # Use cached vector store or build + cache it
    vector_store = _cache_get(payload.contract_id, "vector_store")
    if not vector_store:
        vector_store = await contract_service.get_or_build_vector_store(payload.contract_id)
        _cache_set(payload.contract_id, "vector_store", vector_store)

    # Determine session_id — generate if not provided
    session_id = payload.session_id or generate_session_id(payload.contract_id)

    # Load conversation history — try memory first, then MongoDB
    chat_history = _cache_get(payload.contract_id, f"chat_{session_id}") or []
    if not chat_history:
        try:
            chat_history = await store.get_chat_history(payload.contract_id, session_id)
        except Exception:
            chat_history = []

    # Retrieve relevant chunks
    retrieved_chunks = await run_in_threadpool(
        retrieve_relevant_chunks,
        payload.question,
        vector_store,
        payload.top_k,
    )

    # Try conversational chat engine first (has memory), fall back to extractive QA
    answer = ""
    if chat_engine_available():
        answer = await run_in_threadpool(
            chat_generate_answer,
            payload.question,
            retrieved_chunks,
            chat_history,
        )
    if not answer:
        answer = await run_in_threadpool(answer_question, payload.question, retrieved_chunks)

    # Store interaction scoped to session — memory + MongoDB
    if not chat_history:
        chat_history = []
    chat_history.append({"question": payload.question, "answer": answer})
    _cache_set(payload.contract_id, f"chat_{session_id}", chat_history)
    try:
        await store.append_chat_interaction(
            payload.contract_id, payload.question, answer, session_id
        )
    except Exception:
        pass  # MongoDB best-effort

    return QAResponse(
        contract_id=payload.contract_id,
        question=payload.question,
        answer=answer,
        retrieved_chunks_count=len(retrieved_chunks),
        session_id=session_id,
    )


@app.post("/compare")
async def compare(payload: CompareRequest) -> CompareResponse:
    """Compare two uploaded contracts."""
    text_a = await _get_contract_text(payload.contract_id_a)
    text_b = await _get_contract_text(payload.contract_id_b)

    result = await run_in_threadpool(compare_contracts, text_a, text_b)
    result = result or {}

    return CompareResponse(
        contract_id_a=payload.contract_id_a,
        contract_id_b=payload.contract_id_b,
        summary=result.get("summary", "Comparison not implemented yet"),
        details=result,
    )

@app.post("/verify-vendor")
async def vendor_verify(payload: VendorVerifyRequest) -> VendorVerifyResponse:
    """Verify the vendor named in a contract using AI assessment."""
    text = await _get_contract_text(payload.contract_id)

    # 1. Try in-memory cache
    cached_mem = _cache_get(payload.contract_id, "vendor_verification")
    if cached_mem:
        return VendorVerifyResponse(contract_id=payload.contract_id, **cached_mem)

    # 2. Try MongoDB cache
    try:
        cached = await store.get_vendor_verification(payload.contract_id)
        if cached:
            _cache_set(payload.contract_id, "vendor_verification", cached)
            return VendorVerifyResponse(contract_id=payload.contract_id, **cached)
    except Exception:
        pass

    # 3. Get metadata first (reuse existing extraction)
    meta_cached = _cache_get(payload.contract_id, "metadata")
    if not meta_cached:
        try:
            meta_cached = await store.get_metadata(payload.contract_id)
        except Exception:
            pass
    if not meta_cached:
        from .contracts.metadata_extractor import extract_contract_metadata
        meta_cached = await run_in_threadpool(extract_contract_metadata, text)
        _cache_set(payload.contract_id, "metadata", meta_cached)

    # Extract vendor info from metadata
    vendor_name = meta_cached.get("vendor_name", {}).get("value", "") if isinstance(meta_cached.get("vendor_name"), dict) else ""
    customer_name = meta_cached.get("customer_name", {}).get("value", "") if isinstance(meta_cached.get("customer_name"), dict) else ""
    contract_type = meta_cached.get("contract_type", {}).get("value", "") if isinstance(meta_cached.get("contract_type"), dict) else ""
    effective_date = meta_cached.get("effective_date", {}).get("value", "") if isinstance(meta_cached.get("effective_date"), dict) else ""
    governing_law = meta_cached.get("governing_law", {}).get("value", "") if isinstance(meta_cached.get("governing_law"), dict) else ""

    # 4. Run verification
    result = await run_in_threadpool(
        verify_vendor,
        vendor_name=vendor_name,
        customer_name=customer_name,
        contract_type=contract_type,
        effective_date=effective_date,
        governing_law=governing_law,
    )

    # Cache result
    _cache_set(payload.contract_id, "vendor_verification", result)
    try:
        await store.set_vendor_verification(payload.contract_id, result)
    except Exception:
        pass

    return VendorVerifyResponse(contract_id=payload.contract_id, **result)


@app.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str):
    """Delete a single contract and all its associated data."""
    _mem_cache.pop(contract_id, None)
    try:
        await store.delete_contract(contract_id)
    except Exception:
        pass
    return {"status": "deleted", "contract_id": contract_id}


@app.post("/clear")
async def clear_session():
    """Wipes the database collections and in-memory cache to start a new session."""
    _mem_cache.clear()
    try:
        await store.clear_all()
    except Exception:
        pass  # MongoDB best-effort
    return {"status": "cleared", "message": "New session created successfully."}


# ── Zoho Sign Endpoints ────────────────────────────────────────────

@app.post("/verify-signature")
async def verify_signature_endpoint(payload: ZohoSignatureRequest) -> ZohoSignatureResponse:
    """Verify the digital signature status of a Zoho Sign document."""
    if not zoho_configured():
        raise HTTPException(
            status_code=503,
            detail="Zoho Sign is not configured. Set ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN.",
        )
    try:
        result = await zoho_verify_signature(payload.request_id)
    except RuntimeError as exc:
        detail = str(exc)
        if "auth failed" in detail.lower():
            raise HTTPException(status_code=401, detail=detail)
        raise HTTPException(status_code=500, detail=detail)

    if result is None:
        raise HTTPException(status_code=404, detail=f"Zoho Sign request {payload.request_id} not found.")

    return ZohoSignatureResponse(**result)


@app.post("/audit-trail")
async def audit_trail_endpoint(payload: ZohoSignatureRequest) -> ZohoAuditTrailResponse:
    """Get the signing audit trail for a Zoho Sign document."""
    if not zoho_configured():
        raise HTTPException(
            status_code=503,
            detail="Zoho Sign is not configured.",
        )
    try:
        events = await zoho_get_audit_trail(payload.request_id)
    except RuntimeError as exc:
        detail = str(exc)
        if "auth failed" in detail.lower():
            raise HTTPException(status_code=401, detail=detail)
        raise HTTPException(status_code=500, detail=detail)

    return ZohoAuditTrailResponse(request_id=payload.request_id, events=events)


@app.get("/zoho-status")
async def zoho_status():
    """Check if Zoho Sign integration is configured."""
    return {"configured": zoho_configured()}
