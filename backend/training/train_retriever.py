"""Fine-tune a sentence-transformer retriever on ContractGuard training pairs.

Input format (JSONL): each row must include at least:
- query
- positive
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from sentence_transformers import InputExample, SentenceTransformer, losses
from torch.utils.data import DataLoader


def _load_examples(path: Path, max_examples: int | None = None) -> List[InputExample]:
    examples: List[InputExample] = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            if max_examples is not None and idx >= max_examples:
                break
            row = json.loads(line)
            query = str(row.get("query", "")).strip()
            positive = str(row.get("positive", "")).strip()
            if not query or not positive:
                continue
            examples.append(InputExample(texts=[query, positive]))
    return examples


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ContractGuard retriever model")
    parser.add_argument(
        "--pairs-file",
        default="data/train/retrieval_pairs_bootstrap.jsonl",
        help="Training pairs JSONL file",
    )
    parser.add_argument(
        "--base-model",
        default="all-MiniLM-L6-v2",
        help="Sentence-transformers base model",
    )
    parser.add_argument(
        "--output-dir",
        default="models/contract-embedder-v1",
        help="Directory to save trained model",
    )
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--warmup-steps", type=int, default=10)
    parser.add_argument("--max-examples", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pairs_file = Path(args.pairs_file).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not pairs_file.exists():
        raise FileNotFoundError(f"Pairs file not found: {pairs_file}")

    examples = _load_examples(pairs_file, max_examples=args.max_examples)
    if not examples:
        raise RuntimeError("No valid training examples found in pairs file.")

    print(f"Loaded training examples: {len(examples)}")
    model = SentenceTransformer(args.base_model)

    dataloader = DataLoader(examples, shuffle=True, batch_size=args.batch_size)
    train_loss = losses.MultipleNegativesRankingLoss(model)

    model.fit(
        train_objectives=[(dataloader, train_loss)],
        epochs=args.epochs,
        warmup_steps=args.warmup_steps,
        show_progress_bar=True,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(output_dir))
    print(f"Saved trained retriever model to: {output_dir}")


if __name__ == "__main__":
    main()
