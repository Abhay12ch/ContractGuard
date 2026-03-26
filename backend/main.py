"""FastAPI entrypoint for ContractGuard.

This file exposes the main HTTP API used by the frontend:
- POST /upload   : upload a contract (PDF/DOCX), returns contract_id
- POST /summary  : get plain-language summary
- POST /risks    : get risky clauses + risk score
- POST /ask      : ask a question about a contract
- POST /compare  : compare two uploaded contracts

The actual AI logic lives in the helper modules (parser, analyzer, qa_chain,
comparator). For now, those modules contain stub implementations that can be
incrementally upgraded during the hackathon.
"""

from pathlib import Path
import os
import tempfile
import time
import uuid
from typing import Dict, List

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from dotenv import load_dotenv

from .parser import extract_text_from_file
from .analyzer import analyze_contract
from .qa_chain import answer_question
from .comparator import compare_contracts
from .embedder import build_faiss_store, chunk_contract_text, retrieve_relevant_chunks


app = FastAPI(title="ContractGuard API")


# Load environment variables from project root .env (if present)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


CONTRACT_STORE: Dict[str, str] = {}
CONTRACT_CHUNKS: Dict[str, List[str]] = {}
CONTRACT_VECTOR_STORES: Dict[str, dict] = {}


# On Render free tier, eager embedding on upload can be slow (cold starts/model load).
# Default to lazy indexing, and allow opting back in via env var if needed.
PRECOMPUTE_EMBEDDINGS_ON_UPLOAD = (
    os.getenv("PRECOMPUTE_EMBEDDINGS_ON_UPLOAD", "false").strip().lower() == "true"
)


class UploadResponse(BaseModel):
    contract_id: str
    filename: str
    text_preview: str
    chunk_count: int
    embedding_count: int


class IngestTextRequest(BaseModel):
    text: str
    title: str = "Pasted Contract Text"


class SummaryRequest(BaseModel):
    contract_id: str
    max_chars: int = 600


class SummaryResponse(BaseModel):
    contract_id: str
    summary: str


class RisksRequest(BaseModel):
    contract_id: str


class RisksResponse(BaseModel):
    contract_id: str
    risk_score: int
    safety_score: int
    risk_level: str
    detected_clause_count: int
    risks: List[dict]


class QARequest(BaseModel):
    contract_id: str
    question: str
    top_k: int = 4


class QAResponse(BaseModel):
    contract_id: str
    question: str
    answer: str
    retrieved_chunks_count: int


class CompareRequest(BaseModel):
    contract_id_a: str
    contract_id_b: str


class CompareResponse(BaseModel):
    contract_id_a: str
    contract_id_b: str
    summary: str
    details: dict


def _get_contract_text(contract_id: str) -> str:
    text = CONTRACT_STORE.get(contract_id)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown contract_id. Upload the contract first.",
        )
    return text


def _get_or_build_vector_store(contract_id: str) -> dict:
    """Return cached vector store, building embeddings lazily when needed."""
    vector_store = CONTRACT_VECTOR_STORES.get(contract_id)
    if vector_store:
        has_index = vector_store.get("index") is not None
        has_vectors = vector_store.get("vectors") is not None
        if has_index or has_vectors:
            return vector_store

    if vector_store and vector_store.get("chunks") and int(vector_store.get("embedding_count", 0)) > 0:
        return vector_store

    chunks = CONTRACT_CHUNKS.get(contract_id)
    if chunks is None:
        text = _get_contract_text(contract_id)
        chunks = chunk_contract_text(text)
        CONTRACT_CHUNKS[contract_id] = chunks

    start = time.perf_counter()
    vector_store = build_faiss_store(chunks)
    CONTRACT_VECTOR_STORES[contract_id] = vector_store
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    print(
        f"[ContractGuard] Built vector store lazily for {contract_id} "
        f"in {elapsed_ms} ms (chunks={len(chunks)})."
    )
    return vector_store


def _store_contract_and_index(text: str, filename: str) -> UploadResponse:
    """Store raw contract text, build chunks + FAISS store, and return metadata."""
    start = time.perf_counter()
    contract_id = str(uuid.uuid4())
    CONTRACT_STORE[contract_id] = text
    chunks = chunk_contract_text(text)
    CONTRACT_CHUNKS[contract_id] = chunks

    embedding_count = 0
    if PRECOMPUTE_EMBEDDINGS_ON_UPLOAD:
        vector_store = build_faiss_store(chunks)
        CONTRACT_VECTOR_STORES[contract_id] = vector_store
        embedding_count = int(vector_store.get("embedding_count", 0))
    else:
        # Placeholder store; /ask will build vector index lazily.
        CONTRACT_VECTOR_STORES[contract_id] = {
            "index": None,
            "chunks": chunks,
            "embedding_count": 0,
            "dimension": 0,
        }

    preview = text[:300].replace("\n", " ")
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    print(
        f"[ContractGuard] Stored contract {contract_id} in {elapsed_ms} ms "
        f"(chunks={len(chunks)}, precomputed={PRECOMPUTE_EMBEDDINGS_ON_UPLOAD})."
    )
    return UploadResponse(
        contract_id=contract_id,
        filename=filename,
        text_preview=preview,
        chunk_count=len(chunks),
        embedding_count=embedding_count,
    )


@app.get("/", summary="Health check")
def root() -> dict:
    return {"message": "ContractGuard backend is running"}


@app.post("/upload", response_model=UploadResponse)
async def upload_contract(file: UploadFile = File(...)) -> UploadResponse:
    """Upload a contract file (PDF/DOCX) and return a contract_id.

    The file is written to a temporary location and parsed via parser.extract_text_from_file.
    Parsed text is stored in-memory for subsequent operations.
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        text = extract_text_from_file(str(tmp_path))
    finally:
        # Best-effort cleanup of the temp file
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from contract")

    return _store_contract_and_index(text=text, filename=file.filename)


@app.post("/ingest-text", response_model=UploadResponse)
def ingest_text(payload: IngestTextRequest) -> UploadResponse:
    """Ingest plain text directly, without uploading a file."""
    raw_text = payload.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Text input cannot be empty")

    filename = payload.title.strip() or "Pasted Contract Text"
    return _store_contract_and_index(text=raw_text, filename=filename)


@app.post("/summary", response_model=SummaryResponse)
def generate_summary(payload: SummaryRequest) -> SummaryResponse:
    """Return a very simple heuristic summary for now.

    This can later be replaced by an LLM-powered summary chain.
    """

    text = _get_contract_text(payload.contract_id)

    # Naive "summary": first N characters. Replace with LLM later.
    max_chars = max(100, min(payload.max_chars, 2000))
    summary = text[:max_chars]

    return SummaryResponse(contract_id=payload.contract_id, summary=summary)


@app.post("/risks", response_model=RisksResponse)
def get_risks(payload: RisksRequest) -> RisksResponse:
    """Return detected risky clauses + Contract Risk Score.

    Delegates to analyzer.analyze_contract which currently returns a stub
    structure that can be improved over time.
    """

    text = _get_contract_text(payload.contract_id)
    result = analyze_contract(text)

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


@app.post("/ask", response_model=QAResponse)
def ask_question(payload: QARequest) -> QAResponse:
    """Interactive Q&A over a single contract.

    Uses qa_chain.answer_question(question, context_text).
    """

    _ = _get_contract_text(payload.contract_id)
    vector_store = _get_or_build_vector_store(payload.contract_id)

    retrieved_chunks = retrieve_relevant_chunks(
        question=payload.question,
        vector_store=vector_store,
        top_k=payload.top_k,
    )
    answer = answer_question(payload.question, retrieved_chunks)

    return QAResponse(
        contract_id=payload.contract_id,
        question=payload.question,
        answer=answer,
        retrieved_chunks_count=len(retrieved_chunks),
    )


@app.post("/compare", response_model=CompareResponse)
def compare(payload: CompareRequest) -> CompareResponse:
    """Compare two uploaded contracts.

    Uses comparator.compare_contracts(text_a, text_b).
    """

    text_a = _get_contract_text(payload.contract_id_a)
    text_b = _get_contract_text(payload.contract_id_b)

    result = compare_contracts(text_a, text_b) or {}

    return CompareResponse(
        contract_id_a=payload.contract_id_a,
        contract_id_b=payload.contract_id_b,
        summary=result.get("summary", "Comparison not implemented yet"),
        details=result,
    )
