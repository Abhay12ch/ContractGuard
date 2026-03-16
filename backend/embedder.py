"""Embedding, chunking, and retrieval utilities for ContractGuard.

The module prefers SentenceTransformers + FAISS when available, but can run
fully with NumPy fallback vectors in constrained deployment environments.
"""

from typing import Any, Dict, List
import re

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    import faiss  # type: ignore
except Exception:
    faiss = None  # type: ignore

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None  # type: ignore


_EMBEDDER_MODEL: Any = None


def chunk_contract_text(
    text: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> List[str]:
    """Split large contract text into manageable chunks.

    Uses RecursiveCharacterTextSplitter to preserve semantic boundaries where
    possible while keeping chunk sizes stable for retrieval/embedding pipelines.
    """
    if not text or not text.strip():
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_text(text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _get_embedder(model_name: str = "all-MiniLM-L6-v2") -> Any:
    """Lazy-load and cache the sentence-transformer model if available."""
    global _EMBEDDER_MODEL
    if SentenceTransformer is None:
        return None
    if _EMBEDDER_MODEL is None:
        _EMBEDDER_MODEL = SentenceTransformer(model_name)
    return _EMBEDDER_MODEL


def _hash_embed_texts(texts: List[str], dimension: int = 384) -> np.ndarray:
    """Create lightweight normalized embeddings without external ML packages."""
    vectors = np.zeros((len(texts), dimension), dtype=np.float32)
    token_pattern = re.compile(r"[a-zA-Z0-9]+")

    for row_idx, text in enumerate(texts):
        for token in token_pattern.findall(text.lower()):
            col = hash(token) % dimension
            vectors[row_idx, col] += 1.0

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return vectors / norms


def _embed_texts(texts: List[str]) -> np.ndarray:
    """Convert text chunks to normalized embeddings suitable for FAISS cosine search."""
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    model = _get_embedder()
    if model is None:
        return _hash_embed_texts(texts)

    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.astype(np.float32)


def build_faiss_store(chunks: List[str]) -> Dict[str, object]:
    """Generate embeddings for chunks and store them in a FAISS index.

    Returns an in-memory store containing the FAISS index and chunk metadata.
    """
    clean_chunks = [chunk for chunk in chunks if chunk and chunk.strip()]
    if not clean_chunks:
        return {
            "index": None,
            "chunks": [],
            "embedding_count": 0,
            "dimension": 0,
        }

    vectors = _embed_texts(clean_chunks)
    dimension = int(vectors.shape[1])

    # Normalized vectors + inner product = cosine similarity search.
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
    """Retrieve top-k semantically relevant chunks for a question from FAISS."""
    if not question or not question.strip():
        return []

    index = vector_store.get("index")
    chunks = vector_store.get("chunks", [])
    vectors = vector_store.get("vectors")
    if not chunks:
        return []

    query_vec = _embed_texts([question])
    if query_vec.size == 0:
        return []

    k = max(1, min(top_k, len(chunks)))
    if index is not None:
        _, indices = index.search(query_vec, k)
        ranked_indices = indices[0].tolist()
    elif isinstance(vectors, np.ndarray) and vectors.size:
        # Pure NumPy cosine retrieval fallback for environments without FAISS.
        scores = np.dot(vectors, query_vec[0])
        ranked_indices = np.argsort(scores)[::-1][:k].tolist()
    else:
        return []

    hits: List[str] = []
    for idx in ranked_indices:
        if 0 <= idx < len(chunks):
            hits.append(chunks[idx])
    return hits
