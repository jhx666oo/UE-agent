#!/usr/bin/env python3
"""从 services/api/pyproject.toml 解析运行依赖并输出为 pip 可安装列表。

发布安装脚本用它保证依赖清单与 API 的 pyproject 始终一致，避免手写列表漏项
（例如 app/main.py 顶层导入 vercel / psycopg，缺任何一个都会让 uvicorn 启动失败）。
不引入 tomllib 之外的依赖；Python 3.11+ 自带 tomllib。
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

pyproject = Path(__file__).resolve().parents[1] / "services" / "api" / "pyproject.toml"
data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
dependencies = data.get("project", {}).get("dependencies", [])
if not dependencies:
    print("未从 pyproject 解析到依赖", file=sys.stderr)
    sys.exit(1)
# 每行一个依赖，交给 shell 读取
print("\n".join(dependencies))
