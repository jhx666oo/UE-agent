# Vercel 部署说明

当前仓库按两个 Vercel 项目部署：

- `apps/web`：Next.js 前端项目 `web`
- `services/api`：FastAPI Python Function 项目 `api`

## 必需环境变量

前端 Preview/Production：

```text
NEXT_PUBLIC_API_BASE_URL=https://<api-project>.vercel.app
```

API Preview/Production：

```text
DATABASE_URL=postgresql://...
UE_AGENT_ALLOWED_ORIGINS=https://<web-project>.vercel.app
```

API 的政策文件使用 Vercel Blob 私有存储。将 Blob 存储绑定到 `api` 项目后，由 Vercel 注入 Blob 认证环境变量；不要把 token 写入仓库或聊天消息。

## 数据迁移

Preview 验收前，先在目标数据库执行：

```bash
PYTHONPATH=services/api uv run --project services/api python services/api/scripts/migrate_json_to_postgres.py
```

脚本默认读取 `services/api/data/projects.json`，也可以通过 `UE_AGENT_DATA_FILE` 指定备份文件。

## 发布顺序

1. 创建并绑定 API 项目的 Postgres 数据库和私有 Blob 存储。
2. 部署 API Preview，检查 `/api/health`、项目读写、测算快照和政策文件上传。
3. 将 API Preview URL 写入前端 `NEXT_PUBLIC_API_BASE_URL`，部署前端 Preview。
4. 验收全城市总览、城市项目、政策中心和结果同步。
5. 备份并迁移正式数据后，再提升为 Production。
