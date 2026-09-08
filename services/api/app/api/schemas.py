from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
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
