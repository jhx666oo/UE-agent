import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, type ProjectRecord, type ScenarioRecord, type U1ModelSpec } from "@/lib/api";
import { CityProjectWorkbench } from "./city-project-workbench";

const spec: U1ModelSpec = {
  modelVersion: "u1-excel-v2.1-parity",
  parameters: [
    { id: "C3", name: "参保人数", unit: "人", excelCell: "控制台!E3", inputKind: "manual", valueType: "number", stage: "P0", sourceType: "内部填写", required: true, parityStatus: "parity" },
    { id: "P3", name: "个人自付比例", unit: "%", excelCell: "控制台!E19", inputKind: "formula", valueType: "number", stage: "P0", sourceType: "公式自动", required: false, parityStatus: "parity" },
  ],
  baselineInputs: { C3: 1000, P3: 0.2 },
  issues: [],
};

const project: ProjectRecord = {
  id: "project-1",
  name: "长沙项目",
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
  inputs: { C3: 1000, P3: 0.2 },
  result: {
    modelVersion: "u1-excel-v2.1-parity",
    status: "ok",
    parameters: { C3: 1000, P3: 0.2 },
    months: [],
    stageSummary: {},
    headlineMetrics: {},
    issues: [],
  },
  status: "calculated",
  createdAt: "2026-09-08T00:00:00Z",
  updatedAt: "2026-09-08T00:00:00Z",
  inputSnapshot: { C3: 1000, P3: 0.2 },
  calculatedAt: "2026-09-08T00:00:00Z",
  resultSnapshotId: "snapshot-1",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CityProjectWorkbench", () => {
  it("groups parameters, marks edited calculated inputs stale and links back to dashboard", () => {
    render(<CityProjectWorkbench project={project} scenario={scenario} spec={spec} />);

    expect(screen.getByText("城市与市场")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^C3 参保人数/), { target: { value: "1100" } });
    expect(screen.getAllByText("待重算").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "返回总览" })).toHaveAttribute("href", "/");
  });

  it("shows save feedback after persisting draft inputs", async () => {
    const api = await import("@/lib/api");
    vi.spyOn(api, "updateScenario").mockResolvedValue({ ...scenario, status: "stale" });
    render(<CityProjectWorkbench project={project} scenario={scenario} spec={spec} />);

    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));

    await waitFor(() => expect(screen.getByText("已保存")).toBeInTheDocument());
  });

  it("keeps blocked calculation issues visible", async () => {
    const api = await import("@/lib/api");
    vi.spyOn(api, "updateScenario").mockResolvedValue({ ...scenario, status: "stale" });
    vi.spyOn(api, "calculateScenario").mockRejectedValue(new ApiError("MODEL_BLOCKED", "缺少参保人数", { modelVersion: "u1-excel-v2.1-parity", status: "blocked", parameters: {}, months: [], stageSummary: {}, headlineMetrics: {}, issues: [{ code: "MISSING_REQUIRED_INPUT", excelCell: "控制台!E3", severity: "danger", status: "blocked", message: "缺少参保人数" }] }));
    render(<CityProjectWorkbench project={project} scenario={scenario} spec={spec} />);

    fireEvent.click(screen.getByRole("button", { name: "运行测算" }));

    await waitFor(() => expect(screen.getAllByText("缺少参保人数").length).toBeGreaterThan(0));
    expect(screen.getAllByText("计算失败").length).toBeGreaterThan(0);
  });
});
