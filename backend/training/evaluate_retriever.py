"""Evaluate retrieval quality for base vs trained sentence-transformer models.

This script computes Hit@k and MRR over query-positive pairs stored in JSONL.
Each query is evaluated against the full positive corpus as candidate passages.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer


def _load_pairs(path: Path, max_examples: int | None = None) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            if max_examples is not None and idx >= max_examples:
                break
            payload = json.loads(line)
            query = str(payload.get("query", "")).strip()
            positive = str(payload.get("positive", "")).strip()
            if query and positive:
                rows.append({"query": query, "positive": positive})
    return rows


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return vectors / norms


def _rank_metrics(similarities: np.ndarray, target_indices: np.ndarray, ks: Tuple[int, ...]) -> Dict[str, float]:
    n = similarities.shape[0]
    order = np.argsort(similarities, axis=1)[:, ::-1]

    hit_counts = {k: 0 for k in ks}
    rr_sum = 0.0

    for i in range(n):
        ranking = order[i]
        target = int(target_indices[i])
        position = int(np.where(ranking == target)[0][0]) + 1
        rr_sum += 1.0 / position

        for k in ks:
            if position <= k:
                hit_counts[k] += 1

    metrics: Dict[str, float] = {f"hit@{k}": hit_counts[k] / n for k in ks}
    metrics["mrr"] = rr_sum / n
    return metrics


def evaluate_model(model_name_or_path: str, pairs: List[Dict[str, str]], ks: Tuple[int, ...]) -> Dict[str, float]:
    model = SentenceTransformer(model_name_or_path)

    queries = [row["query"] for row in pairs]
    positives = [row["positive"] for row in pairs]

    # Use unique positives as retrieval corpus.
    corpus: List[str] = []
    corpus_index: Dict[str, int] = {}
    target_indices: List[int] = []

    for passage in positives:
        if passage not in corpus_index:
            corpus_index[passage] = len(corpus)
            corpus.append(passage)
        target_indices.append(corpus_index[passage])

    query_vec = model.encode(queries, convert_to_numpy=True)
    corpus_vec = model.encode(corpus, convert_to_numpy=True)

    query_vec = _normalize(query_vec.astype(np.float32))
    corpus_vec = _normalize(corpus_vec.astype(np.float32))

    sims = np.matmul(query_vec, corpus_vec.T)
    return _rank_metrics(sims, np.array(target_indices, dtype=np.int32), ks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate base vs trained retriever")
    parser.add_argument(
        "--pairs-file",
        default="data/train/retrieval_pairs_bootstrap.jsonl",
        help="JSONL file with query/positive pairs",
    )
    parser.add_argument(
        "--base-model",
        default="all-MiniLM-L6-v2",
        help="Baseline model name",
    )
    parser.add_argument(
        "--trained-model",
        default="models/contract-embedder-v1",
        help="Trained model path",
    )
    parser.add_argument("--max-examples", type=int, default=300)
    parser.add_argument("--k-values", nargs="+", type=int, default=[1, 3, 5, 10])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pairs_file = Path(args.pairs_file).resolve()

    if not pairs_file.exists():
        raise FileNotFoundError(f"Pairs file not found: {pairs_file}")

    pairs = _load_pairs(pairs_file, max_examples=args.max_examples)
    if len(pairs) < 5:
        raise RuntimeError("Need at least 5 evaluation pairs.")

    ks = tuple(sorted(set(args.k_values)))

    print(f"Loaded evaluation pairs: {len(pairs)}")
    base_metrics = evaluate_model(args.base_model, pairs, ks)
    tuned_metrics = evaluate_model(args.trained_model, pairs, ks)

    print("\nBaseline metrics")
    for key, value in base_metrics.items():
        print(f"  {key}: {value:.4f}")

    print("\nTrained metrics")
    for key, value in tuned_metrics.items():
        print(f"  {key}: {value:.4f}")

    print("\nDelta (trained - baseline)")
    for key in base_metrics:
        print(f"  {key}: {(tuned_metrics[key] - base_metrics[key]):+.4f}")


if __name__ == "__main__":
    main()
