"""Build a training corpus from existing contract documents.

This script scans one or more input paths for PDF, DOCX, TXT, and MD files,
extracts text, chunks it with the same pipeline as runtime retrieval, and writes
JSONL files that can be used to fine-tune retrieval models.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List

from backend.embedder import chunk_contract_text
from backend.parser import extract_text_from_file

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}
SKIP_DIR_NAMES = {".venv", "venv", "__pycache__", ".git", "node_modules"}
PREFERRED_CSV_TEXT_COLUMNS = {
    "text",
    "contract_text",
    "clause",
    "clause_text",
    "content",
    "body",
    "question",
    "query",
    "answer",
}


def _iter_documents(paths: Iterable[Path]) -> Iterable[Path]:
    for input_path in paths:
        if input_path.is_file() and input_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield input_path
            continue

        if input_path.is_dir():
            for child in input_path.rglob("*"):
                if any(part in SKIP_DIR_NAMES for part in child.parts):
                    continue
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    yield child


def _extract_csv_text(path: Path, max_rows: int | None = None) -> str:
    rows: List[str] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            return ""

        fieldnames = [name.strip() for name in reader.fieldnames if name and name.strip()]
        preferred = [name for name in fieldnames if name.lower() in PREFERRED_CSV_TEXT_COLUMNS]
        selected_columns = preferred if preferred else fieldnames

        for row_idx, row in enumerate(reader):
            if max_rows is not None and row_idx >= max_rows:
                break
            values = []
            for col in selected_columns:
                value = str(row.get(col, "") or "").strip()
                if value:
                    values.append(value)
            if values:
                rows.append(" | ".join(values))

    return "\n".join(rows)


def _read_document(path: Path, max_csv_rows: int | None = None) -> str:
    suffix = path.suffix.lower()
    if suffix in {".pdf", ".docx"}:
        return extract_text_from_file(str(path))
    if suffix == ".csv":
        return _extract_csv_text(path, max_rows=max_csv_rows)

    return path.read_text(encoding="utf-8", errors="ignore")


def _weak_queries_for_chunk(chunk: str) -> List[str]:
    """Generate basic synthetic queries from chunk text for bootstrap training."""
    text = " ".join(chunk.split())
    if len(text) > 240:
        text = text[:240]

    return [
        f"Summarize this clause: {text}",
        f"What risk is present in this clause: {text}",
        f"Explain this contract term: {text}",
    ]


def build_corpus(
    input_paths: List[Path],
    output_dir: Path,
    min_chunk_chars: int = 120,
    max_csv_rows: int | None = None,
) -> Dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)

    chunks_file = output_dir / "corpus_chunks.jsonl"
    pairs_file = output_dir / "retrieval_pairs_bootstrap.jsonl"

    doc_count = 0
    chunk_count = 0
    pair_count = 0

    with chunks_file.open("w", encoding="utf-8") as chunk_out, pairs_file.open("w", encoding="utf-8") as pair_out:
        for doc_path in _iter_documents(input_paths):
            try:
                raw_text = _read_document(doc_path, max_csv_rows=max_csv_rows)
            except Exception as exc:
                print(f"[skip] {doc_path}: {exc}")
                continue

            if not raw_text or not raw_text.strip():
                continue

            chunks = [c for c in chunk_contract_text(raw_text) if len(c.strip()) >= min_chunk_chars]
            if not chunks:
                continue

            doc_count += 1
            rel_path = str(doc_path)

            for idx, chunk in enumerate(chunks):
                chunk_count += 1
                chunk_row = {
                    "doc_path": rel_path,
                    "chunk_id": f"{doc_path.stem}-{idx}",
                    "chunk_index": idx,
                    "text": chunk,
                }
                chunk_out.write(json.dumps(chunk_row, ensure_ascii=True) + "\n")

                for query in _weak_queries_for_chunk(chunk):
                    pair_count += 1
                    pair_row = {
                        "query": query,
                        "positive": chunk,
                        "source_chunk_id": chunk_row["chunk_id"],
                        "doc_path": rel_path,
                    }
                    pair_out.write(json.dumps(pair_row, ensure_ascii=True) + "\n")

    return {
        "documents": doc_count,
        "chunks": chunk_count,
        "bootstrap_pairs": pair_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build training corpus from contract documents")
    parser.add_argument(
        "--input",
        nargs="+",
        default=["data"],
        help="Input files/directories to scan (default: data)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/train",
        help="Output directory for corpus files (default: data/train)",
    )
    parser.add_argument(
        "--min-chunk-chars",
        type=int,
        default=120,
        help="Drop chunks shorter than this number of characters",
    )
    parser.add_argument(
        "--max-csv-rows",
        type=int,
        default=None,
        help="Use at most this many rows from each CSV file (default: all)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_paths = [Path(p).resolve() for p in args.input]
    output_dir = Path(args.output_dir).resolve()

    stats = build_corpus(
        input_paths,
        output_dir,
        min_chunk_chars=args.min_chunk_chars,
        max_csv_rows=args.max_csv_rows,
    )

    print("Training corpus build complete")
    print(json.dumps(stats, indent=2))
    print(f"Wrote: {output_dir / 'corpus_chunks.jsonl'}")
    print(f"Wrote: {output_dir / 'retrieval_pairs_bootstrap.jsonl'}")


if __name__ == "__main__":
    main()
