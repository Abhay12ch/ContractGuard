"""Pydantic request/response schemas for ContractGuard API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel


class UploadResponse(BaseModel):
    contract_id: str
    filename: str
    text_preview: str
    chunk_count: int
    embedding_count: int
    status: Literal["processing", "ready", "failed"] = "ready"


class ContractStatusResponse(BaseModel):
    contract_id: str
    status: Literal["processing", "ready", "failed"]
    embedding_count: int = 0
    error: str | None = None


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
    session_id: str = ""


class QAResponse(BaseModel):
    contract_id: str
    question: str
    answer: str
    retrieved_chunks_count: int
    session_id: str = ""


class MetadataRequest(BaseModel):
    contract_id: str


class MetadataResponse(BaseModel):
    contract_id: str
    metadata: Dict[str, Any]


class CompareRequest(BaseModel):
    contract_id_a: str
    contract_id_b: str


class CompareResponse(BaseModel):
    contract_id_a: str
    contract_id_b: str
    summary: str
    details: dict


class ContractListItem(BaseModel):
    contract_id: str
    title: str
    uploaded_at: str


class ContractListResponse(BaseModel):
    contracts: List[ContractListItem]


__all__ = [
    "ContractStatusResponse",
    "ContractListItem",
    "ContractListResponse",
    "CompareRequest",
    "CompareResponse",
    "IngestTextRequest",
    "MetadataRequest",
    "MetadataResponse",
    "QARequest",
    "QAResponse",
    "RisksRequest",
    "RisksResponse",
    "SummaryRequest",
    "SummaryResponse",
    "UploadResponse",
]
