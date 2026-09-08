# U1 model specification

本目录保存 `u1-excel-v2.1-parity` 的参数字典、公式台账、已知问题和脱敏基准输入。它们共同构成前后端共享的模型契约。

- `parameters/`：75 个控制台参数的稳定 ID 与 Excel 单元格映射。
- `formulas/`：控制台、月度投影、阶段汇总和核心指标公式台账。
- `issues/`：需要随结果展示的疑似引用、公式错误和口径风险。
- `fixtures/`：只读对照工作簿提取出的脱敏基准，不包含源 Excel 文件。
