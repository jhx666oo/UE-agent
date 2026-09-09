import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  type FieldValueView,
  type ProjectRecord,
  type ScenarioRecord,
  type ScenarioValuesResponse,
  type U1ModelSpec,
} from "@/lib/api";
import { CityProjectWorkbench } from "./city-project-workbench";

const spec: U1ModelSpec = {
  modelVersion: "u1-excel-v2.1-parity",
  parameters: [
    { id: "C3", name: "参保人数", unit: "人", excelCell: "控制台!E3", inputKind: "manual", valueType: "number", stage: "P0", sourceType: "内部填写", required: true, parityStatus: "parity", block: "城市与市场", blockOrder: 1 },
    { id: "P1", name: "单小时服务单价", unit: "元/小时", excelCell: "控制台!E17", inputKind: "reference_or_manual", valueType: "number", stage: "P0", sourceType: "自动爬虫", required: true, parityStatus: "parity", block: "政策准入", blockOrder: 2 },
    { id: "P3", name: "个人自付比例", unit: "%", excelCell: "控制台!E19", inputKind: "formula", valueType: "number", stage: "P0", sourceType: "公式自动", required: false, parityStatus: "parity", block: "政策准入", blockOrder: 2 },
    { id: "B3", name: "护士用工方式", unit: "-", excelCell: "控制台!E38", inputKind: "manual", valueType: "string", stage: "P0", sourceType: "内部填写", required: true, parityStatus: "parity", block: "成本参数", blockOrder: 4, options: ["挂证", "全职", "兼任"] },
  ],
  baselineInputs: { C3: 1000, P1: 50, P3: 0.2 },
  issues: [],
};

const project: ProjectRecord = {
  id: "project-1",
  name: "长沙城市测算",
  city: "长沙",
  district: "岳麓区",
  baseMonth: "2026-09",
  stationMode: "自营",
  createdAt: "2026-09-08T00:00:00Z",
  updatedAt: "2026-09-08T00:00:00Z",
  scenarios: [],
};

const scenario: ScenarioRecord = {
  id: "scenario-1",
  name: "基准",
  inputs: { C3: 1000, P1: 50, P3: 0.2 },
  result: {
    modelVersion: "u1-excel-v2.1-parity",
    status: "ok",
    parameters: { C3: 1000, P1: 50, P3: 0.2 },
    months: [],
    stageSummary: {},
    headlineMetrics: {},
    issues: [],
  },
  status: "calculated",
  createdAt: "2026-09-08T00:00:00Z",
  updatedAt: "2026-09-08T00:00:00Z",
  inputSnapshot: { C3: 1000, P1: 50, P3: 0.2 },
  calculatedAt: "2026-09-08T00:00:00Z",
  resultSnapshotId: "snapshot-1",
};

function field(overrides: Partial<FieldValueView> & Pick<FieldValueView, "fieldId" | "sourceType">): FieldValueView {
  return {
    name: overrides.name ?? "字段",
    unit: overrides.unit ?? "-",
    block: overrides.block ?? "城市与市场",
    blockOrder: overrides.blockOrder ?? 1,
    readOnly: overrides.sourceType === "公式自动",
    currentValue: overrides.currentValue ?? null,
    suggestedValue: overrides.suggestedValue ?? null,
    suggestedSource: overrides.suggestedSource ?? null,
    suggestedAt: overrides.suggestedAt ?? null,
    valueState: overrides.valueState ?? "manual",
    ...overrides,
  };
}

const values: ScenarioValuesResponse = {
  scenarioId: "scenario-1",
  fields: [
    field({ fieldId: "C3", name: "参保人数", unit: "人", sourceType: "内部填写", currentValue: 1000 }),
    field({
      fieldId: "P1",
      name: "单小时服务单价",
      unit: "元/小时",
      sourceType: "自动爬虫",
      block: "政策准入",
      blockOrder: 2,
      currentValue: 50,
      suggestedValue: 60,
      suggestedSource: { sourceName: "长沙市医保局", url: "https://example.test/policy" },
      suggestedAt: "2026-09-09T00:00:00Z",
      valueState: "suggestion_ready",
    }),
    field({
      fieldId: "P3",
      name: "个人自付比例",
      unit: "%",
      sourceType: "公式自动",
      block: "政策准入",
      blockOrder: 2,
      currentValue: 0.2,
      valueState: "formula",
    }),
    field({
      fieldId: "B3",
      name: "护士用工方式",
      sourceType: "内部填写",
      block: "成本参数",
      blockOrder: 4,
      currentValue: "全职",
      valueState: "manual",
      options: ["挂证", "全职", "兼任"],
    }),
  ],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CityProjectWorkbench", () => {
  it("renders blocks in PRD order with suggestion and formula affordances", () => {
    render(<CityProjectWorkbench project={project} scenario={scenario} spec={spec} initialValues={values} />);

    expect(screen.getByText("城市与市场")).toBeInTheDocument();
    expect(screen.getByText("政策准入")).toBeInTheDocument();
    expect(screen.getByText("成本参数")).toBeInTheDocument();
    // 公式自动字段只读
    const formulaInput = screen.getByLabelText("P3 个人自付比例");
    expect(formulaInput).toHaveAttribute("readonly");
    // 爬虫建议值：灰色提示 + 采用按钮 + 查看来源
    expect(screen.getByText(/建议值：60 元\/小时/)).toBeInTheDocument();
    expect(screen.getByText(/来源：长沙市医保局/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "采用建议值" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看来源" })).toHaveAttribute("href", "https://example.test/policy");
    // 顶部建议值计数
    expect(screen.getByText("1 个建议值待采用")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回总览" })).toHaveAttribute("href", "/");
  });

  it("accepting a suggestion updates the field and marks scenario stale", async () => {
    const api = await import("@/lib/api");
    vi.spyOn(api, "acceptFieldSuggestion").mockResolvedValue(
      field({
        fieldId: "P1",
        sourceType: "自动爬虫",
        currentValue: 60,
        suggestedValue: 60,
        valueState: "accepted",
      }),
    );
    render(<CityProjectWorkbench project={project} scenario={scenario} spec={spec} initialValues={values} />);

    fireEvent.click(screen.getByRole("button", { name: "采用建议值" }));

    await waitFor(() => expect(screen.getByText(/已采用 单小时服务单价 的建议值/)).toBeInTheDocument());
    expect(api.acceptFieldSuggestion).toHaveBeenCalledWith("project-1", "scenario-1", "P1");
    expect(screen.getAllByText("待重算").length).toBeGreaterThan(0);
  });

  it("manual edit on a crawler field is persisted per-field", async () => {
    const api = await import("@/lib/api");
    vi.spyOn(api, "patchScenarioValue").mockResolvedValue(
      field({ fieldId: "P1", sourceType: "自动爬虫", currentValue: 55, suggestedValue: 60, valueState: "overridden" }),
    );
    render(<CityProjectWorkbench project={project} scenario={scenario} spec={spec} initialValues={values} />);

    fireEvent.change(screen.getByLabelText("P1 单小时服务单价"), { target: { value: "55" } });

    await waitFor(() => expect(api.patchScenarioValue).toHaveBeenCalledWith("project-1", "scenario-1", "P1", 55));
    await waitFor(() => expect(screen.getByText("已手动覆盖")).toBeInTheDocument());
  });

  it("renders enum options as a select control", () => {
    render(<CityProjectWorkbench project={project} scenario={scenario} spec={spec} initialValues={values} />);

    const select = screen.getByLabelText("B3 护士用工方式") as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");
    expect(select.value).toBe("全职");
    const options = Array.from(select.options).map((option) => option.value);
    expect(options).toEqual(["挂证", "全职", "兼任"]);
  });

  it("keeps blocked calculation issues visible", async () => {
    const api = await import("@/lib/api");
    vi.spyOn(api, "listScenarioSnapshots").mockResolvedValue([]);
    vi.spyOn(api, "listScenarioValues").mockResolvedValue(values);
    vi.spyOn(api, "calculateScenario").mockRejectedValue(
      new ApiError("MODEL_BLOCKED", "缺少参保人数", {
        modelVersion: "u1-excel-v2.1-parity",
        status: "blocked",
        parameters: {},
        months: [],
        stageSummary: {},
        headlineMetrics: {},
        issues: [{ code: "MISSING_REQUIRED_INPUT", excelCell: "控制台!E3", severity: "danger", status: "blocked", message: "缺少参保人数" }],
      }),
    );
    render(<CityProjectWorkbench project={project} scenario={scenario} spec={spec} initialValues={values} />);

    fireEvent.click(screen.getByRole("button", { name: "运行测算" }));

    await waitFor(() => expect(screen.getAllByText("缺少参保人数").length).toBeGreaterThan(0));
    expect(screen.getAllByText("计算失败").length).toBeGreaterThan(0);
  });
});
