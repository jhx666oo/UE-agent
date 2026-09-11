from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .repository import PostgresProjectRepository, ProjectRepository, VercelBlobPolicyFileStore
from .sqlite_repository import SqliteProjectRepository, default_database_path


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


def create_repository() -> ProjectRepository:
    """本地默认使用 SQLite；只有显式配置 DATABASE_URL 才走云端文档存储。"""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return PostgresProjectRepository(database_url, file_store=VercelBlobPolicyFileStore())
    return SqliteProjectRepository(default_database_path())


def create_app(repository: ProjectRepository | None = None) -> FastAPI:
    app = FastAPI(title="UE Agent API", version="0.1.0")
    app.state.repository = repository or create_repository()
    # 仅本地端到端验证用：显式设置 UE_AGENT_E2E_ALLOW_PRIVATE=1 才放行回环/私有地址。
    # 生产路径必须保持拒绝（crawlers 模块默认 SSRF 防护）。
    app.state.crawl_allow_private = os.getenv("UE_AGENT_E2E_ALLOW_PRIVATE") == "1"
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
