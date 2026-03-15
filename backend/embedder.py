"""Embedding, chunking, and FAISS utilities for ContractGuard."""

from typing import Dict, List

import faiss
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer


_EMBEDDER_MODEL: SentenceTransformer | None = None


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


def _get_embedder(model_name: str = "all-MiniLM-L6-v2") -> SentenceTransformer:
    """Lazy-load and cache the sentence-transformer model."""
    global _EMBEDDER_MODEL
    if _EMBEDDER_MODEL is None:
        _EMBEDDER_MODEL = SentenceTransformer(model_name)
    return _EMBEDDER_MODEL


def _embed_texts(texts: List[str]) -> np.ndarray:
    """Convert text chunks to normalized embeddings suitable for FAISS cosine search."""
    if not texts:
        return np.empty((0, 0), dtype=np.float32)

    model = _get_embedder()
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
    index = faiss.IndexFlatIP(dimension)
    index.add(vectors)

    return {
        "index": index,
        "chunks": clean_chunks,
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
    if index is None or not chunks:
        return []

    query_vec = _embed_texts([question])
    if query_vec.size == 0:
        return []

    k = max(1, min(top_k, len(chunks)))
    _, indices = index.search(query_vec, k)

    hits: List[str] = []
    for idx in indices[0].tolist():
        if 0 <= idx < len(chunks):
            hits.append(chunks[idx])
    return hits
