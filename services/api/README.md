# UE Agent API domain

当前目录先承载不依赖 FastAPI 的 U1 纯计算域。它读取 `packages/model-spec` 中的版本化 JSON 规格，输出 24 个月投影、阶段汇总、关键指标和待业务确认问题。

## 运行模型测试

在仓库根目录执行：

```bash
pnpm model:test
```

也可以直接执行：

```bash
PYTHONPATH=services/api python3 -m unittest discover -s services/api/tests -p 'test_*.py' -v
```

## 重要边界

- 当前引擎不依赖 Excel 文件、数据库、爬虫或大模型。
- 原始工作簿只作为只读对照物，不进入运行时，也不应被脚本改写。
- `u1-excel-v2.1-parity` 严格保留现有 Excel 公式；疑似问题通过 `issues` 返回，不在引擎内擅自修正。
- 下一步才接入 FastAPI 请求契约、项目持久化和前端表单提交。
