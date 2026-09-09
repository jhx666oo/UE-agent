from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .repository import JsonProjectRepository, PostgresProjectRepository, VercelBlobPolicyFileStore


def default_data_path() -> Path:
    configured = os.getenv("UE_AGENT_DATA_FILE")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "projects.json"


def allowed_origins() -> list[str]:
    configured = os.getenv("UE_AGENT_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def create_repository() -> JsonProjectRepository:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return PostgresProjectRepository(database_url, file_store=VercelBlobPolicyFileStore())
    return JsonProjectRepository(default_data_path())


def create_app(repository: JsonProjectRepository | None = None) -> FastAPI:
    app = FastAPI(title="UE Agent API", version="0.1.0")
    app.state.repository = repository or create_repository()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    return app


app = create_app()
