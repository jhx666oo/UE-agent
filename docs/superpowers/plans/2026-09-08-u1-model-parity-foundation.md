# U1 Excel Parity Model Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a dependency-light Python U1 model foundation that reproduces the current Excel formulas, preserves formula errors and suspicious references, and produces tested 24-month results with traceable issues.

**Architecture:** `packages/model-spec` stores parameter metadata, formula templates, known issues, and one sanitized baseline input fixture. `services/api/app/domain/u1` owns pure Python dataclasses and deterministic calculation functions; it has no Next.js, database, Excel runtime, crawler, or LLM dependency. The future FastAPI layer will call this pure engine after the parity tests pass.

**Tech Stack:** Python 3.14-compatible standard library, dataclasses, `json`, `math`, `unittest`; existing Next.js workspace scripts remain unchanged except for a root `model:test` command.

## Global Constraints

- Strictly reproduce the current Excel formulas and references; do not correct `控制台!E32`, `阶段汇总表!B12`, or any other suspicious formula in this version.
- Every suspicious formula or abnormal result must be returned as a structured `ModelIssue` with an Excel cell, issue code, severity, and `needs_business_confirmation` status.
- Distinguish valid numeric zero, missing value, and formula error; never turn a required missing value or `DIV0` into zero.
- Keep calculation logic in `services/api/app/domain/u1`; the React application must not copy financial formulas.
- Use a fixed model version string `u1-excel-v2.1-parity` for the first baseline implementation.
- Use `unittest` so the model test suite runs in a clean Python environment without installing new third-party packages.
- Use the existing workbook only as a read-only reference; commit an extracted baseline JSON fixture, never the source workbook.
- Run the targeted test after each red-green cycle, then run `python3 -m unittest discover -s services/api/tests -p 'test_*.py'`, `pnpm test`, `pnpm typecheck`, `pnpm lint`, and `pnpm build` before completion.

## File Map

- `packages/model-spec/parameters/u1.parameters.json`: stable parameter IDs, labels, units, source kinds, stages, Excel cells, and parity status.
- `packages/model-spec/formulas/u1.formulas.json`: formula ledger for control formulas, monthly rows, stage summaries, and headline outputs.
- `packages/model-spec/issues/u1.issues.json`: known parity issues that must be surfaced by the engine.
- `packages/model-spec/fixtures/u1-baseline.json`: current workbook inputs and selected cached results used for regression tests.
- `services/api/app/domain/u1/models.py`: input, formula value, issue, monthly, stage, and result dataclasses.
- `services/api/app/domain/u1/spec.py`: JSON spec loading and parameter validation.
- `services/api/app/domain/u1/stages.py`: Excel stage selection and 24-month stage sequence.
- `services/api/app/domain/u1/formulas.py`: small pure helpers that mirror individual Excel formulas.
- `services/api/app/domain/u1/issues.py`: issue catalog loading and dynamic issue creation.
- `services/api/app/domain/u1/engine.py`: ordered 24-month calculation and stage/headline aggregation.
- `services/api/tests/`: red-green tests for spec, helpers, errors, baseline outputs, and issue propagation.
- `docs/model/`: human-readable parameter dictionary, formula ledger, and known issue record.

---

### Task 1: Create the model specification package and baseline fixture

**Files:**
- Create: `packages/model-spec/parameters/u1.parameters.json`
- Create: `packages/model-spec/formulas/u1.formulas.json`
- Create: `packages/model-spec/issues/u1.issues.json`
- Create: `packages/model-spec/fixtures/u1-baseline.json`
- Create: `services/api/app/__init__.py`
- Create: `services/api/app/domain/__init__.py`
- Create: `services/api/app/domain/u1/__init__.py`
- Create: `services/api/tests/__init__.py`
- Create: `services/api/tests/test_spec_contract.py`
- Create: `services/api/app/domain/u1/spec.py`

**Interfaces:**
- `load_json_spec(relative_path: str) -> object` loads only files under `packages/model-spec`.
- `load_parameter_catalog() -> dict[str, dict[str, object]]` returns the catalog keyed by parameter ID.
- `validate_parameter_catalog(catalog) -> list[str]` returns deterministic validation messages.

- [x] **Step 1: Write the failing specification contract test**

Create `services/api/tests/test_spec_contract.py`:

```python
import unittest

from app.domain.u1.spec import load_parameter_catalog, validate_parameter_catalog


class SpecContractTests(unittest.TestCase):
    def test_catalog_contains_all_excel_parameter_groups_and_no_duplicate_ids(self):
        catalog = load_parameter_catalog()
        errors = validate_parameter_catalog(catalog)

        self.assertEqual(errors, [])
        self.assertEqual(len(catalog), 75)
        self.assertEqual(catalog["C1"]["excelCell"], "控制台!E4")
        self.assertEqual(catalog["P1"]["excelCell"], "控制台!E17")
        self.assertEqual(catalog["Z5"]["excelCell"], "控制台!E78")
        self.assertEqual(catalog["P3"]["inputKind"], "formula")


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the test to verify the expected failure**

Run `PYTHONPATH=services/api python3 -m unittest services/api/tests/test_spec_contract.py -v`.

Expected: FAIL with an import error because `app.domain.u1.spec` does not exist.

- [x] **Step 3: Add the parameter catalog and spec loader**

Create 75 entries covering `C1-C13`, `P1-P11`, `S1-S8`, `B1-B16`, `D1-D8`, `E1-E8`, `A1-A6`, and `Z1-Z5`. Each entry must contain `id`, `name`, `unit`, `excelCell`, `inputKind`, `valueType`, `stage`, `sourceType`, `required`, and `parityStatus`. Mark `C9`, `P3`, `S3`, `S5`, and `B16` as `inputKind: "formula"`; mark the remaining control inputs as `manual` or `reference_or_manual` according to the workbook source type.

Create `u1-baseline.json` with the workbook's current values from `控制台!E4:E78`, excluding formula cells from the input map and preserving the blank `C11` value as `null`. Include selected cached results for `核心指标卡!C5:C14`, `阶段汇总表!B12`, and `月度投影表!B:Y` rows 3, 5, 11, 29, 32, 33, 35, and 36.

Create `spec.py` with a repository-root resolver, JSON loading, duplicate-ID detection, Excel cell format validation, and the expected ID-group check. The loader must return a clear `FileNotFoundError` for a missing spec file and must not silently return an empty catalog.

- [x] **Step 4: Run the targeted test to verify green**

Run `PYTHONPATH=services/api python3 -m unittest services/api/tests/test_spec_contract.py -v`.

Expected: one passing test and zero failures.

- [x] **Step 5: Commit the specification baseline**

```bash
git add packages/model-spec services/api/app services/api/tests/test_spec_contract.py
git commit -m "feat: add U1 model specification baseline"
```

### Task 2: Implement stages, formula values, and known issue propagation

**Files:**
- Create: `services/api/app/domain/u1/models.py`
- Create: `services/api/app/domain/u1/stages.py`
- Create: `services/api/app/domain/u1/formulas.py`
- Create: `services/api/app/domain/u1/issues.py`
- Create: `services/api/tests/test_stages.py`
- Create: `services/api/tests/test_formulas.py`

**Interfaces:**
- `stage_for_month(month: int, preparation_months: int, startup_months: int) -> str` returns `筹备期`, `启动期`, or `平台期`.
- `build_stage_sequence(preparation_months: int, startup_months: int, platform_months: int) -> tuple[str, ...]` returns exactly 24 stages for the baseline input.
- `formula_value(value, *, error_code: str | None = None) -> FormulaValue` creates an `ok` or `formula_error` value.
- `ceil_excel(value: float, significance: float = 1.0) -> int` mirrors Excel `CEILING(number, significance)` for the positive values used by this model.
- `load_known_issues() -> tuple[ModelIssue, ...]` loads the static issue catalog.

- [x] **Step 1: Write failing stage and formula tests**

Create tests that require:

```python
class StageTests(unittest.TestCase):
    def test_baseline_has_one_preparation_six_startup_and_seventeen_platform_months(self):
        sequence = build_stage_sequence(1, 6, 17)
        self.assertEqual(sequence, ("筹备期", "启动期", "启动期", "启动期", "启动期", "启动期", "启动期", *(["平台期"] * 17)))


class FormulaTests(unittest.TestCase):
    def test_excel_parity_helpers_preserve_the_suspected_e32_reference(self):
        values = {"S1": 3, "C9": 0.002, "C10": 0.008, "C11": 0.025, "C4": 0.2, "C8": 20000, "C12": 20000}
        self.assertAlmostEqual(station_daily_caregiver_hours(values), 689.893746728319, places=9)
        self.assertAlmostEqual(station_coverage_disabled_limit(values), 226195078.208873, places=6)

    def test_zero_denominator_is_a_formula_error(self):
        result = safe_ratio(-48250, 0)
        self.assertEqual(result.status, "formula_error")
        self.assertEqual(result.error_code, "DIV0")
        self.assertIsNone(result.value)
```

- [x] **Step 2: Run the targeted tests to verify red**

Run `PYTHONPATH=services/api python3 -m unittest services/api/tests/test_stages.py services/api/tests/test_formulas.py -v`.

Expected: FAIL because the stage and formula modules do not exist.

- [x] **Step 3: Implement the minimal models and helpers**

Use frozen dataclasses. `FormulaValue` must have `value`, `status`, and `error_code`; `ModelIssue` must have `code`, `excelCell`, `severity`, `status`, and `message`. Keep the static issue codes `SUSPECTED_CELL_REFERENCE`, `DIV0_IN_SUMMARY`, and `CUMULATIVE_SERIES_SUM` in the issue JSON. Implement the exact Excel formulas for `E12`, `E19`, `E30`, `E32`, and `E51` in small named functions.

- [x] **Step 4: Run the targeted tests to verify green**

Run the same unittest command. Expected: all stage and formula tests pass.

### Task 3: Implement the 24-month U1 engine

**Files:**
- Modify: `services/api/app/domain/u1/models.py`
- Create: `services/api/app/domain/u1/engine.py`
- Create: `services/api/tests/test_engine_baseline.py`

**Interfaces:**
- `calculate_u1(values: Mapping[str, object], model_version: str = "u1-excel-v2.1-parity") -> U1Result`.
- `U1Result.months` contains 24 `MonthlyProjection` objects in month order.
- Each `MonthlyProjection` contains `month`, `stage`, and the named outputs `signed_customers`, `single_customer_month_revenue`, `total_revenue`, `variable_cost`, `fixed_cost`, `net_profit`, `cumulative_net_profit`, `cumulative_cash_flow`, `cash_flow_positive_month`, and `break_even_customers`.

- [x] **Step 1: Write the failing baseline engine tests**

Create tests that assert the baseline behavior before implementation:

```python
class BaselineEngineTests(unittest.TestCase):
    def test_calculates_24_months_and_preserves_baseline_stage_transition(self):
        result = calculate_u1(load_baseline_inputs())
        self.assertEqual(len(result.months), 24)
        self.assertEqual(result.months[0].stage, "筹备期")
        self.assertEqual(result.months[1].stage, "启动期")
        self.assertEqual(result.months[7].stage, "平台期")
        self.assertEqual(result.months[0].signed_customers.value, 0)
        self.assertAlmostEqual(result.months[1].single_customer_month_revenue.value, 1950)

    def test_required_missing_input_blocks_only_when_a_used_driver_is_missing(self):
        values = load_baseline_inputs()
        values["P1"] = None
        result = calculate_u1(values)
        self.assertEqual(result.status, "blocked")
        self.assertIn("MISSING_REQUIRED_INPUT", {issue.code for issue in result.issues})
```

- [x] **Step 2: Run the targeted tests to verify red**

Run `PYTHONPATH=services/api python3 -m unittest services/api/tests/test_engine_baseline.py -v`.

Expected: FAIL because `engine.py` and `calculate_u1` do not exist.

- [x] **Step 3: Implement the calculation pipeline**

Implement the Excel row order without page or database dependencies:

1. Resolve derived controls `C9`, `P3`, `S3`, `S5`, and `B16`.
2. Build the 24-month stage sequence.
3. Calculate rows 5-16 for customers, revenue, and variable costs.
4. Calculate rows 17-27 for fixed costs.
5. Calculate rows 28-36 for profit, margins, cumulative values, cash recovery, and break-even customers.
6. Attach the static parity issues to every result and add dynamic missing-input or formula-error issues.

Do not clamp the station customer limit, normalize the suspect `E32` reference, or hide the `DIV0` result.

- [x] **Step 4: Run the targeted tests to verify green**

Run the baseline engine tests and then `PYTHONPATH=services/api python3 -m unittest discover -s services/api/tests -p 'test_*.py' -v`. Expected: all tests pass.

### Task 4: Add stage summaries, headline metrics, and parity regression checks

**Files:**
- Modify: `services/api/app/domain/u1/engine.py`
- Modify: `services/api/tests/test_engine_baseline.py`
- Create: `services/api/tests/test_regressions.py`

**Interfaces:**
- `U1Result.stage_summary` maps `筹备期`, `启动期`, and `平台期` to monthly count, total revenue, total variable cost, total fixed cost, total net profit, total cash flow, average revenue, average net profit, and net margin.
- `U1Result.headline_metrics` contains `payback_month`, `max_cash_deficit`, `platform_monthly_net_profit`, `platform_net_margin`, `twenty_four_month_cumulative_net_profit`, `break_even_customers`, and `initial_investment`.

- [x] **Step 1: Write failing regression assertions from the workbook cache**

Use the baseline fixture's selected cached results and assert, with a `1e-6` relative tolerance for amounts:

```python
self.assertEqual(result.headline_metrics["payback_month"].value, 24)
self.assertAlmostEqual(result.headline_metrics["max_cash_deficit"].value, -501000, places=6)
self.assertAlmostEqual(result.headline_metrics["platform_monthly_net_profit"].value, 220138554186.338, delta=1e-3)
self.assertEqual(result.headline_metrics["break_even_customers"].value, 23)
self.assertAlmostEqual(result.headline_metrics["initial_investment"].value, 459000, places=6)
self.assertEqual(result.stage_summary["筹备期"]["net_margin"].status, "formula_error")
```

Also assert the issue set contains `SUSPECTED_CELL_REFERENCE`, `DIV0_IN_SUMMARY`, and `CUMULATIVE_SERIES_SUM`.

- [x] **Step 2: Run the regression test to verify red**

Run `PYTHONPATH=services/api python3 -m unittest services/api/tests/test_regressions.py -v`. Expected: FAIL because stage summaries and headline metrics are not yet populated.

- [x] **Step 3: Implement summaries and explicit formula errors**

Aggregate monthly records by stage. Calculate stage averages using the exact Excel denominators. For the preparation-stage net margin, return a `FormulaValue(status="formula_error", error_code="DIV0")`. Reproduce `AB32 = SUM(B32:Y32)` as the headline cumulative-net-profit formula and surface the cumulative-series issue instead of silently replacing it with the month-24 ending balance.

- [x] **Step 4: Run all model tests to verify green**

Run `PYTHONPATH=services/api python3 -m unittest discover -s services/api/tests -p 'test_*.py' -v`. Expected: all tests pass and the issue codes are present.

### Task 5: Document the model base and integrate repository verification

**Files:**
- Create: `services/api/pyproject.toml`
- Create: `services/api/README.md`
- Create: `docs/model/u1-parameter-dictionary.md`
- Create: `docs/model/u1-formula-ledger.md`
- Create: `docs/model/u1-known-issues.md`
- Modify: `package.json`
- Modify: `README.md`
- Modify: `docs/UE-Agent-详细开发规范-v0.1.md`
- Modify: `docs/standards/06-前端验收检查表.md`
- Modify: `docs/superpowers/specs/2026-09-08-u1-model-parity-design.md`

- [x] **Step 1: Add the model test command**

Add the root script:

```json
"model:test": "PYTHONPATH=services/api python3 -m unittest discover -s services/api/tests -p 'test_*.py'"
```

Add `services/api/pyproject.toml` with Python `>=3.11` and no runtime dependencies. Add `services/api/README.md` with the exact commands for model tests and a clear statement that the source workbook remains read-only.

- [x] **Step 2: Write human-readable model documentation**

Generate the parameter dictionary and formula ledger from the JSON spec without adding contradictory business claims. The known issue document must list `E32`, `B12`, and `AB32`, their current Excel behavior, why each is flagged, and the fact that this version does not correct them.

- [x] **Step 3: Update project status and verification checklist**

Record that the Python parity engine and baseline tests are now implemented, while FastAPI, persistence, crawler, and UI form submission remain next. Mark only the model tests and parity checks that actually passed.

- [x] **Step 4: Run the complete verification suite**

Run:

```bash
pnpm model:test
pnpm test
pnpm typecheck
pnpm lint
pnpm build
git diff --check
```

Expected: all commands exit 0. Confirm the source workbook is not staged and the working tree contains only the planned model foundation files.

- [x] **Step 5: Commit and push the model foundation**

```bash
git add package.json README.md docs services/api packages/model-spec
git commit -m "feat: add U1 Excel parity calculation engine"
git push origin main
```

## Self-review

- The plan covers the approved strict-parity rule, explicit issue propagation, 24-month calculation, stage summaries, headline metrics, regression tests, and documentation.
- The plan does not introduce FastAPI, persistence, crawler behavior, or UI formulas before the pure calculation layer is verified.
- All later interfaces use the names defined in earlier tasks: `U1Result`, `FormulaValue`, `ModelIssue`, `calculate_u1`, `load_parameter_catalog`, and `build_stage_sequence`.
- No source workbook, personal data, or unsupported formula correction enters the repository.
