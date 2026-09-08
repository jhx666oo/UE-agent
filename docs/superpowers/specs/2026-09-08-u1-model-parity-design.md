# U1 Excel Parity Model Foundation Design

## 1. 目标

建立 UE-Agent 的第一版 U1 模型复刻基座：将现有 Excel 的参数、公式、阶段和关键输出映射为版本化、可测试、可追溯的确定性计算模块。

本阶段的首要目标不是修正 Excel，而是回答三个问题：

1. 系统是否能在相同输入下复现 Excel 的计算路径。
2. 每个系统结果能否追溯到参数编号、Excel 单元格和原始公式。
3. Excel 中的疑似错误、空值和公式错误能否被显式暴露，而不是被静默转成看似正常的数字。

## 2. 业务边界

### 2.1 本阶段包含

- U1 参数字典和参数元数据。
- Excel 单元格到标准参数编号的映射。
- Excel 公式台账和公式状态。
- 筹备期、启动期、平台期三阶段逻辑。
- 24 个月月度投影所需的纯计算函数。
- 收入、变动成本、固定成本、利润、现金流和盈亏平衡客户数计算。
- Excel 基准样例的回归测试。
- 疑似问题清单和计算结果中的待确认标记。

### 2.2 本阶段不包含

- 不修改或覆盖原始 Excel。
- 不把 Excel 文件作为生产运行时依赖。
- 不擅自修正公式、参数单位或业务口径。
- 不实现公开数据爬虫、政策解析、用户登录和权限管理。
- 不实现完整项目持久化和后台模型版本发布页面。
- 不在页面端重复实现任何财务公式。

## 3. 设计原则

### 3.1 Excel 优先，但 Excel 不等于已确认口径

第一版计算结果以 Excel 当前公式为复刻对象。复刻对象本身仍需要业务确认，因此每条公式都保存以下状态之一：

| 状态 | 含义 |
|---|---|
| `parity` | 已按 Excel 公式复刻，当前没有记录疑点 |
| `needs_business_confirmation` | 公式可以复刻，但字段语义、引用或结果数量级存在疑点 |
| `blocked` | 缺少必要信息，暂不能安全复刻 |

`needs_business_confirmation` 不阻止引擎计算，但会进入结果的 `issues` 数组并在前端显示。

### 3.2 错误和缺失值不伪装成零

系统区分：

- 有效数值 `number`。
- 真实零值 `0`。
- 空值 `null`。
- Excel 公式错误，例如 `#DIV/0!`。
- 依赖待确认口径但仍按 Excel 复刻的结果。

计算函数不得使用无条件的 `IFERROR(..., 0)` 等逻辑隐藏错误。若分母为零，结果保留 `formula_error: DIV0`，并提供对应单元格和公式。

### 3.3 计算与展示分离

计算引擎只返回结构化结果、状态和来源链路，不负责中文格式化、页面布局或图表。前端读取模型字典和计算结果后负责展示。

## 4. 目标目录和职责

```text
UE-agent/
├── packages/
│   └── model-spec/
│       ├── parameters/
│       │   └── u1.parameters.json
│       ├── formulas/
│       │   └── u1.formulas.json
│       └── fixtures/
│           └── u1-baseline.json
├── services/
│   └── api/
│       ├── pyproject.toml
│       ├── app/
│       │   └── domain/u1/
│       │       ├── models.py
│       │       ├── issues.py
│       │       ├── formulas.py
│       │       ├── engine.py
│       │       └── stages.py
│       └── tests/
│           └── domain/u1/
│               ├── test_parameters.py
│               ├── test_stages.py
│               ├── test_formulas.py
│               └── test_baseline.py
└── docs/
    └── model/
        ├── u1-parameter-dictionary.md
        ├── u1-formula-ledger.md
        └── u1-known-issues.md
```

`packages/model-spec` 是可被前端和 Python 服务读取的静态契约；`services/api/app/domain/u1` 是唯一拥有 U1 计算逻辑的代码边界；`docs/model` 用于业务人员阅读和确认，不作为运行时输入。

## 5. 参数字典

参数以 Excel 控制台的编号为外部稳定标识，例如 `C1`、`P1`、`S1`、`B1`、`D1`、`E1`、`A1` 和 `Z1`。参数元数据至少包含：

```json
{
  "id": "P1",
  "name": "单小时服务单价",
  "unit": "元/小时",
  "excelCell": "控制台!E17",
  "inputKind": "reference_or_manual",
  "valueType": "number",
  "stage": "P0",
  "sourceType": "自动爬虫",
  "required": true,
  "min": 0,
  "max": null,
  "parityStatus": "parity"
}
```

参数值在运行时使用：

```text
ParameterValue {
  parameterId: string
  value: number | string | boolean | null
  valueSource: reference | manual | formula
  sourceId?: string
  asOf?: string
  confirmed: boolean
}
```

参考值和人工确认值必须分开记录。参考值可以一键填入表单，但填入后必须变成可识别的人工输入，不得在后台静默覆盖已确认值。

## 6. 公式台账

每条被复刻的 Excel 公式记录 Excel 来源、标准输出、公式文本和问题状态：

```json
{
  "id": "formula.station_coverage_disabled_limit",
  "excelCell": "控制台!E32",
  "outputKey": "station.coverage_disabled_customer_limit",
  "excelFormula": "PI()*E28^2*E12*E7*(E9*0.6+E10*0.3+E12*0.1)",
  "translatedFormula": "PI()*S1^2*city.population_density*C4*(C6*0.6+C7*0.3+C12*0.1)",
  "unit": "人",
  "parityStatus": "needs_business_confirmation",
  "issueCode": "SUSPECTED_CELL_REFERENCE"
}
```

`translatedFormula` 只把 Excel 单元格替换为标准参数编号，不改变运算顺序、常数或引用关系。公式修正必须新增模型版本，不允许直接改写已发布公式台账。

## 7. 计算结果契约

引擎入口为纯函数：

```python
def calculate_u1(input: U1Input, model_version: str) -> U1Result:
    ...
```

`U1Result` 至少包含：

```text
U1Result {
  modelVersion: string
  status: calculated | calculated_with_issues | blocked | formula_error
  parameters: resolved parameter values with provenance
  months: 24 monthly projection records
  stageSummary: preparation/startup/platform summaries
  headlineMetrics: payback month, max cash deficit, platform monthly profit, break-even customers
  issues: ModelIssue[]
}
```

月度记录保留 Excel 月份编号、阶段、客户数、单客收入、总收入、变动成本、固定成本、毛利润、净利润、累计净利润、累计现金流、现金流回正标记、现金流回正月份和盈亏平衡客户数。

## 8. 阶段与公式复刻策略

计算顺序固定为：

1. 解析和校验参数值，不把缺失值转换成零。
2. 按 `D1`、`D2`、`D3` 生成 24 个月阶段序列。
3. 计算站点覆盖、目标客户池和签约客户数。
4. 计算单客月收入、基金支付收入、个人自付收入及辅助收入。
5. 计算护理员、销售、护士等变动成本。
6. 计算管理、租金、系统、培训、物料、合规等固定成本。
7. 计算毛利润、净利润、累计净利润和累计现金流。
8. 计算现金流回正月份和平台期盈亏平衡客户数。
9. 汇总阶段指标并收集疑点、公式错误和输入缺失。

每一步对应公式台账中的 `outputKey`。引擎不通过页面字段顺序或 Excel 单元格地址直接写业务逻辑。

## 9. 已登记的待确认问题

### 9.1 `控制台!E32`

字段名称是“站点覆盖失能客户上限”，Excel 公式中的最后一项使用 `E12*0.1`。`E12` 当前是区域人口密度，而 `E11` 才是 80 岁以上失能率。第一版保持 Excel 原引用，并记录：

```text
issueCode: SUSPECTED_CELL_REFERENCE
severity: warning
status: needs_business_confirmation
```

### 9.2 `阶段汇总表!B12`

筹备期累计收入为零时，Excel 公式 `B8/B5` 返回 `#DIV/0!`。第一版保留公式错误，不改成零、不改成空值。结果状态必须让前端能展示“筹备期净利率不可计算”。

### 9.3 客户规模和收入数量级

当前样例输入下，站点覆盖客户和 24 个月收入出现异常大的结果。第一版不通过限幅、四舍五入或隐藏异常来改变 Excel 结果，只记录数量级待确认问题，并在后续业务评审中确认城市总量、区域总量、站点覆盖和目标市场覆盖率的边界关系。

## 10. 测试策略

测试分为四层：

1. 参数层：单位、类型、必填、空值、真实零值和来源状态。
2. 公式层：阶段判断、收入、成本、累计值、回正月份和 `ROUNDUP` 边界。
3. 问题层：`E32` 疑点必须出现、`B12` 必须保留 `DIV0`、数量级问题必须出现警告。
4. 基准层：使用当前 Excel 基准输入，对比关键单元格的缓存值或人工确认结果；金额采用明确容差，枚举、月份和错误码精确匹配。

首批固定场景只使用当前工作簿的基准输入。完成业务确认后，再增加乐观、基准、悲观三个版本，避免把未经确认的样例结果固化为业务真相。

## 11. 后续 UI 接入

计算基座验证通过后，U1 页面分为五步：

1. 测算范围：城市、行政区、基准月份和站点模式。
2. 关键假设：按参数分组展示来源、单位、默认值和确认状态。
3. 数据准备：展示缺失项、参考值和待确认问题。
4. 执行测算：调用后端计算接口，显示计算中、错误和带问题结果。
5. 结果复核：展示 24 个月结果、阶段摘要、异常清单和模型版本。

页面只调用计算接口，不复制公式。任何待确认问题都必须在执行测算和结果复核中持续可见。

## 12. 验收标准

- 在不修正疑似公式的前提下，基准输入可以生成 24 个月结果。
- 每个关键结果都可以追溯到标准参数、Excel 单元格和公式台账。
- `E32` 疑点、`B12` 的 `DIV0` 和异常数量级都不会被隐藏。
- 空值、真实零值、公式错误和待确认状态在结果中可区分。
- 纯计算模块可以脱离 Next.js、数据库和 Excel 文件运行。
- 测试覆盖参数、阶段、核心公式和基准场景。
- 业务确认公式后，可以通过新增模型版本修正，不修改旧版本结果。
