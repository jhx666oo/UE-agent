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


class DataSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cityId: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="web", min_length=1, max_length=30)
    url: str | None = Field(default=None, max_length=500)


class DataSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: str | None = Field(default=None, min_length=1, max_length=30)
    url: str | None = Field(default=None, max_length=500)
    status: Literal["active", "paused", "error"] | None = None


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
