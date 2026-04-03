"""Embedding, chunking, and retrieval utilities for ContractGuard.

Supports provider-based embeddings:
- local : SentenceTransformers (with NumPy hash fallback)
- gemini: Gemini API embeddings via the google-genai SDK
- auto  : Gemini when configured and available, else local

All vectors are normalized for cosine similarity search.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Literal
import importlib
import logging
import os
import re
import warnings

import numpy as np

logger = logging.getLogger("contractguard.embedder")

def _load_faiss() -> Any:
    """Import faiss while suppressing Python 3.14 SWIG deprecation noise."""
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"builtin type SwigPyPacked has no __module__ attribute",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r"builtin type SwigPyObject has no __module__ attribute",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r"builtin type swigvarlink has no __module__ attribute",
                category=DeprecationWarning,
            )
            return importlib.import_module("faiss")  # type: ignore
    except ImportError:
        return None


faiss = _load_faiss()

try:
    _sentence_transformers = importlib.import_module("sentence_transformers")
    SentenceTransformer = getattr(_sentence_transformers, "SentenceTransformer")
except (ImportError, AttributeError):
    SentenceTransformer = None  # type: ignore[assignment]


EmbedMode = Literal["document", "query"]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _embedding_provider() -> str:
    provider = os.getenv("EMBEDDING_PROVIDER", "auto").strip().lower()
    if provider in {"auto", "local", "gemini"}:
        return provider
    logger.warning("Unknown EMBEDDING_PROVIDER=%s. Falling back to 'auto'.", provider)
    return "auto"


def _gemini_model_name() -> str:
    return os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001").strip() or "gemini-embedding-001"


def _gemini_batch_size() -> int:
    return max(1, _env_int("GEMINI_EMBEDDING_BATCH_SIZE", 32))


def _fallback_to_local_enabled() -> bool:
    return os.getenv("EMBEDDING_FALLBACK_TO_LOCAL", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _embedding_dimension() -> int | None:
    # Optional override. If omitted, model default dimensionality is used.
    # Common values: 768, 1536, 3072
    dim = _env_optional_int("GEMINI_EMBEDDING_DIMENSION")
    if dim is None:
        return None
    if 128 <= dim <= 3072:
        return dim
    logger.warning("Ignoring GEMINI_EMBEDDING_DIMENSION=%s (valid range 128..3072).", dim)
    return None


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, np.finfo(np.float32).eps)
    return vectors / norms


@lru_cache(maxsize=1)
def _load_embedder(model_name: str) -> Any:
    if SentenceTransformer is None:
        return None
    return SentenceTransformer(model_name)


@lru_cache(maxsize=1)
def _load_gemini_modules() -> tuple[Any | None, Any | None]:
    try:
        genai_mod = importlib.import_module("google.genai")
        types_mod = importlib.import_module("google.genai.types")
        return genai_mod, types_mod
    except ImportError:
        return None, None


@lru_cache(maxsize=1)
def _get_gemini_client(api_key: str) -> Any | None:
    genai_mod, _ = _load_gemini_modules()
    if genai_mod is None:
        return None
    return genai_mod.Client(api_key=api_key)


def _gemini_available() -> bool:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False

    client = _get_gemini_client(api_key)
    return client is not None


def warmup_embedder() -> bool:
    """Warm up selected embedding backend.

    Returns True when warmup loaded an active provider backend:
    - local mode: sentence-transformer loaded
    - gemini mode: Gemini client initialized
    """
    provider = _embedding_provider()
    if provider == "gemini":
        return _gemini_available()

    if provider == "auto" and _gemini_available():
        return True

    return _get_local_embedder() is not None


def chunk_contract_text(
    text: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> List[str]:
    """Split large contract text into manageable chunks."""
    if not text or not text.strip():
        return []

    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return []

    chunks: List[str] = []
    step = max(1, chunk_size - chunk_overlap)
    start = 0
    text_len = len(clean_text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = clean_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start += step

    return chunks


def _get_local_embedder(model_name: str | None = None) -> Any:
    if SentenceTransformer is None:
        return None

    resolved_model_name = (
        model_name
        or os.getenv("EMBEDDER_MODEL_NAME", "").strip()
        or os.getenv("EMBEDDER_MODEL_PATH", "").strip()
        or "all-MiniLM-L6-v2"
    )

    return _load_embedder(resolved_model_name)


def _hash_embed_texts(texts: List[str], dimension: int = 384) -> np.ndarray:
    vectors = np.zeros((len(texts), dimension), dtype=np.float32)
    token_pattern = re.compile(r"[a-zA-Z0-9]+")

    for row_idx, text in enumerate(texts):
        for token in token_pattern.findall(text.lower()):
            col = hash(token) % dimension
            vectors[row_idx, col] += 1.0

    return _normalize_vectors(vectors)


def _embed_texts_local(texts: List[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    model = _get_local_embedder()
    if model is None:
        return _hash_embed_texts(texts)

    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.astype(np.float32)


def _gemini_query_task(model_name: str) -> str:
    if "embedding-2" in model_name:
        return "task: question answering | query: {content}"
    return "QUESTION_ANSWERING"


def _gemini_document_task(model_name: str) -> str:
    if "embedding-2" in model_name:
        return "title: none | text: {content}"
    return "RETRIEVAL_DOCUMENT"


def _prepare_gemini_contents(texts: List[str], *, mode: EmbedMode, model_name: str) -> List[str]:
    if "embedding-2" not in model_name:
        return texts

    if mode == "query":
        query_fmt = _gemini_query_task(model_name)
        return [query_fmt.format(content=text) for text in texts]

    doc_fmt = _gemini_document_task(model_name)
    return [doc_fmt.format(content=text) for text in texts]


def _build_gemini_config(types_mod: Any, *, mode: EmbedMode, model_name: str) -> Any | None:
    kwargs: dict[str, Any] = {}

    dim = _embedding_dimension()
    if dim is not None:
        kwargs["output_dimensionality"] = dim

    if "embedding-2" not in model_name:
        kwargs["task_type"] = (
            _gemini_query_task(model_name)
            if mode == "query"
            else _gemini_document_task(model_name)
        )

    if not kwargs:
        return None

    return types_mod.EmbedContentConfig(**kwargs)


def _batch(items: List[str], batch_size: int) -> List[List[str]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _embed_texts_gemini(texts: List[str], *, mode: EmbedMode) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set for Gemini embeddings.")

    client = _get_gemini_client(api_key)
    _, types_mod = _load_gemini_modules()

    if client is None or types_mod is None:
        raise RuntimeError("google-genai SDK is not installed for Gemini embeddings.")

    model_name = _gemini_model_name()
    prepared_contents = _prepare_gemini_contents(texts, mode=mode, model_name=model_name)
    embed_config = _build_gemini_config(types_mod, mode=mode, model_name=model_name)

    vectors_out: List[np.ndarray] = []
    for text_batch in _batch(prepared_contents, _gemini_batch_size()):
        request: dict[str, Any] = {
            "model": model_name,
            "contents": text_batch,
        }
        if embed_config is not None:
            request["config"] = embed_config

        result = client.models.embed_content(**request)
        embeddings = getattr(result, "embeddings", None)
        if not embeddings:
            raise RuntimeError("Gemini embedding call returned no embeddings.")

        for embedding in embeddings:
            values = np.array(getattr(embedding, "values", []), dtype=np.float32)
            if values.size == 0:
                raise RuntimeError("Gemini embedding vector was empty.")
            vectors_out.append(values)

    if not vectors_out:
        return np.empty((0, 0), dtype=np.float32)

    vectors = np.vstack(vectors_out).astype(np.float32)
    return _normalize_vectors(vectors)


def _embed_texts(texts: List[str], *, mode: EmbedMode = "document") -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    provider = _embedding_provider()

    if provider in {"gemini", "auto"}:
        try:
            return _embed_texts_gemini(texts, mode=mode)
        except (RuntimeError, ValueError, TypeError) as exc:
            if provider == "gemini" or not _fallback_to_local_enabled():
                raise
            logger.warning(
                "Gemini embeddings unavailable (%s). Falling back to local embeddings.",
                exc,
            )

    return _embed_texts_local(texts)


def build_faiss_store(chunks: List[str]) -> Dict[str, object]:
    """Generate embeddings for chunks and store them in a FAISS index."""
    clean_chunks = [chunk for chunk in chunks if chunk and chunk.strip()]
    if not clean_chunks:
        return {
            "index": None,
            "chunks": [],
            "embedding_count": 0,
            "dimension": 0,
        }

    vectors = _embed_texts(clean_chunks, mode="document")
    dimension = int(vectors.shape[1])

    index = None
    if faiss is not None:
        index = faiss.IndexFlatIP(dimension)
        index.add(vectors)

    return {
        "index": index,
        "chunks": clean_chunks,
        "vectors": vectors,
        "use_faiss": index is not None,
        "embedding_count": len(clean_chunks),
        "dimension": dimension,
    }


def retrieve_relevant_chunks(
    question: str,
    vector_store: Dict[str, object],
    top_k: int = 4,
) -> List[str]:
    """Retrieve top-k semantically relevant chunks for a question."""
    if not question or not question.strip():
        return []

    index = vector_store.get("index")
    chunks = vector_store.get("chunks", [])
    vectors = vector_store.get("vectors")
    if not chunks:
        return []

    query_vec = _embed_texts([question], mode="query")
    if query_vec.size == 0:
        return []

    k = max(1, min(top_k, len(chunks)))
    if index is not None:
        _, indices = index.search(query_vec, k)
        ranked_indices = indices[0].tolist()
    elif isinstance(vectors, np.ndarray) and vectors.size:
        scores = np.dot(vectors, query_vec[0])
        ranked_indices = np.argsort(scores)[::-1][:k].tolist()
    else:
        return []

    hits: List[str] = []
    for idx in ranked_indices:
        if 0 <= idx < len(chunks):
            hits.append(chunks[idx])
    return hits


__all__ = [
    "build_faiss_store",
    "chunk_contract_text",
    "retrieve_relevant_chunks",
    "warmup_embedder",
]
