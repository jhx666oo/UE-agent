import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { U1Workbench } from "./u1-workbench";
import type { ScenarioRecord, U1ModelSpec, U1Result } from "@/lib/api";

const spec: U1ModelSpec = {
  modelVersion: "u1-excel-v2.1-parity",
  parameters: [
    {
      id: "A1",
      name: "辅具租赁月均收入",
      unit: "元/月",
      excelCell: "控制台!E68",
      inputKind: "manual",
      valueType: "number",
      stage: "P2",
      sourceType: "内部填写",
      required: true,
      parityStatus: "parity",
    },
    {
      id: "P3",
      name: "个人自付比例",
      unit: "%",
      excelCell: "控制台!E19",
      inputKind: "formula",
      valueType: "number",
      stage: "P0",
      sourceType: "公式自动",
      required: false,
      parityStatus: "parity",
    },
  ],
  baselineInputs: { A1: 0 },
  issues: [],
};

const result: U1Result = {
  modelVersion: "u1-excel-v2.1-parity",
  status: "ok",
  parameters: { A1: 0, P3: 0.2 },
  months: [],
  stageSummary: { 筹备期: { netMargin: { value: null, status: "formula_error", errorCode: "DIV0" } } },
  headlineMetrics: {
    payback_month: { value: 24, status: "ok", errorCode: null },
  },
  issues: [
    { code: "SUSPECTED_CELL_REFERENCE", excelCell: "控制台!E32", severity: "warning", status: "needs_business_confirmation", message: "待确认" },
    { code: "DIV0_IN_SUMMARY", excelCell: "阶段汇总表!B12", severity: "warning", status: "needs_business_confirmation", message: "待确认" },
    { code: "CUMULATIVE_SERIES_SUM", excelCell: "核心指标卡!C9", severity: "warning", status: "needs_business_confirmation", message: "待确认" },
  ],
};

const scenario: ScenarioRecord = {
  id: "scenario-1",
  name: "基准",
  inputs: { A1: 0, P3: 0.2 },
  result,
  status: "calculated",
  createdAt: "2026-09-08T00:00:00Z",
  updatedAt: "2026-09-08T00:00:00Z",
};

afterEach(() => cleanup());

describe("U1Workbench", () => {
  it("keeps formula fields read-only and preserves a manually entered zero", () => {
    render(<U1Workbench projectId="project-1" scenario={scenario} spec={spec} />);

    expect(screen.getByLabelText("P3 个人自付比例")).toHaveAttribute("readOnly");
    const manualInput = screen.getByLabelText(/^A1 辅具租赁月均收入/) as HTMLInputElement;
    fireEvent.change(manualInput, { target: { value: "0" } });
    expect(manualInput.value).toBe("0");
  });

  it("renders formula errors and every known issue code", () => {
    render(<U1Workbench projectId="project-1" scenario={scenario} spec={spec} />);

    expect(screen.getAllByText("不可计算：DIV0").length).toBeGreaterThan(0);
    expect(screen.getByText("SUSPECTED_CELL_REFERENCE")).toBeInTheDocument();
    expect(screen.getByText("DIV0_IN_SUMMARY")).toBeInTheDocument();
    expect(screen.getByText("CUMULATIVE_SERIES_SUM")).toBeInTheDocument();
  });
});
