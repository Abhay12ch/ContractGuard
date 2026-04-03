import pytest

from backend.contracts.embedder import build_faiss_store, retrieve_relevant_chunks


def test_auto_provider_falls_back_without_gemini_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "auto")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    store = build_faiss_store(
        [
            "Payment schedule is net 30 days.",
            "Early termination fee applies for cancellation.",
        ]
    )

    assert store["embedding_count"] == 2
    assert store["dimension"] > 0

    hits = retrieve_relevant_chunks("Is there termination fee?", store, top_k=1)
    assert len(hits) == 1


def test_gemini_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("EMBEDDING_FALLBACK_TO_LOCAL", "false")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_faiss_store(["A sample contract clause."])
