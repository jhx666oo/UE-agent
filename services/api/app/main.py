from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .repository import JsonProjectRepository


def default_data_path() -> Path:
    configured = os.getenv("UE_AGENT_DATA_FILE")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "projects.json"


def create_app(repository: JsonProjectRepository | None = None) -> FastAPI:
    app = FastAPI(title="UE Agent API", version="0.1.0")
    app.state.repository = repository or JsonProjectRepository(default_data_path())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    return app


app = create_app()
