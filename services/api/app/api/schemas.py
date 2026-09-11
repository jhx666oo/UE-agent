from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    cityId: str | None = Field(default=None, max_length=80)
    city: str = Field(min_length=1, max_length=60)
    district: str | None = Field(default=None, max_length=60)
    baseMonth: str | None = Field(default=None, max_length=7)
    stationMode: str = Field(default="自营", min_length=1, max_length=20)


class ScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    inputs: dict[str, Any] | None = None


class ScenarioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    inputs: dict[str, Any] | None = None


class FieldValueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any = None


class DataSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cityId: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="web", min_length=1, max_length=30)
    url: str | None = Field(default=None, max_length=500)
    status: str = Field(default="active", min_length=1, max_length=20)
    timeoutSeconds: int | None = Field(default=None, ge=1, le=60)
    maxBytes: int | None = Field(default=None, ge=1, le=20 * 1024 * 1024)
    note: str | None = Field(default=None, max_length=500)


class DataSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: str | None = Field(default=None, min_length=1, max_length=30)
    url: str | None = Field(default=None, max_length=500)
    status: Literal["active", "paused", "error"] | None = None
    timeoutSeconds: int | None = Field(default=None, ge=1, le=60)
    maxBytes: int | None = Field(default=None, ge=1, le=20 * 1024 * 1024)
    note: str | None = Field(default=None, max_length=500)


class PolicyCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fieldId: str = Field(min_length=1, max_length=120)
    value: Any = None
    unit: str | None = Field(default=None, max_length=40)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str | None = Field(default=None, max_length=500)


class PolicyParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[PolicyCandidateInput] = Field(default_factory=list, max_length=100)


class PolicyReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1, max_length=80)
    source: str | None = Field(default=None, max_length=500)
    effectiveDate: str | None = Field(default=None, max_length=30)


# ---------- AI 回传链路（WorkBuddy 驱动架构） ----------


class FetchRequestItem(BaseModel):
    """WorkBuddy 声明要抓取的一个 URL。"""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2000)
    cityId: str | None = Field(default=None, max_length=80)
    sourceId: str | None = Field(default=None, max_length=120)
    name: str | None = Field(default=None, max_length=120)


class FetchRequestBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: list[FetchRequestItem] = Field(min_length=1, max_length=50)
    maxChars: int | None = Field(default=None, ge=1000, le=200000)


class ExtractionFact(BaseModel):
    """WorkBuddy 抽取出的单个字段值。quote 必填 —— 空引用不予采信。"""

    model_config = ConfigDict(extra="forbid")

    fieldId: str = Field(min_length=1, max_length=20)
    value: Any = None
    unit: str | None = Field(default=None, max_length=40)
    confidence: float | None = Field(default=None, ge=0, le=1)
    quote: str | None = Field(default=None, max_length=2000)
    effectiveDate: str | None = Field(default=None, max_length=30)


class ExtractionSubmissionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceId: str | None = Field(default=None, max_length=120)
    artifactId: str | None = Field(default=None, max_length=120)
    extractedAt: str | None = Field(default=None, max_length=40)
    facts: list[ExtractionFact] = Field(default_factory=list, max_length=200)
    notDisclosed: list[str] = Field(default_factory=list, max_length=100)


class ExtractionSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cityId: str = Field(min_length=1, max_length=80)
    agentRunId: str | None = Field(default=None, max_length=120)
    agentVersion: str | None = Field(default=None, max_length=60)
    submissions: list[ExtractionSubmissionItem] = Field(min_length=1, max_length=50)


class SourceCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=300)
    domain: str | None = Field(default=None, max_length=200)
    publishedAt: str | None = Field(default=None, max_length=40)
    summary: str | None = Field(default=None, max_length=2000)
    targetFields: list[str] = Field(default_factory=list, max_length=50)
    relevance: float | None = Field(default=None, ge=0, le=1)
    origin: str | None = Field(default=None, max_length=40)


class SourceCandidateBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cityId: str = Field(min_length=1, max_length=80)
    candidates: list[SourceCandidateInput] = Field(min_length=1, max_length=100)


class SourceCandidateReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)
