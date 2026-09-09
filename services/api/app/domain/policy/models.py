from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


PolicyDocumentStatus = Literal["uploaded", "parsing", "review_pending", "approved", "rejected"]
PolicyFactStatus = Literal["candidate", "approved", "rejected"]
DataSourceStatus = Literal["active", "paused", "error"]


@dataclass(frozen=True)
class PolicyCandidate:
    field_id: str
    value: Any
    unit: str | None
    confidence: float | None
    source: str | None


@dataclass(frozen=True)
class PolicyDocument:
    id: str
    city_id: str
    original_name: str
    mime_type: str
    size: int
    sha256: str
    source: str
    status: PolicyDocumentStatus
    uploaded_at: str


@dataclass(frozen=True)
class PolicyFact:
    id: str
    document_id: str
    city_id: str
    field_id: str
    value: Any
    unit: str | None
    confidence: float | None
    source: str | None
    status: PolicyFactStatus
    reviewer: str | None
    reviewed_at: str | None
    effective_date: str | None


@dataclass(frozen=True)
class DataSource:
    id: str
    city_id: str
    name: str
    kind: str
    url: str | None
    status: DataSourceStatus
