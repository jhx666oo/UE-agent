import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DashboardOverview } from "./dashboard-overview";
import type { DashboardOverviewResponse } from "@/lib/dashboard";

const baseResponse: DashboardOverviewResponse = {
  scope: "global",
  period: 12,
  scenarioRule: "latest",
  includeStale: true,
  updatedAt: "2026-09-08T00:00:00Z",
  summary: {
    eligibleCityCount: 1,
    totalCityCount: 2,
    targetCustomers: 100,
    monthlyRevenue: 1000,
    monthlyNetProfit: 200,
    initialInvestment: 5000,
    cumulativeNetProfit: 4800,
    paybackMedian: 12,
    paybackDistribution: [{ range: "1-12个月", count: 1 }],
    pendingIssueCount: 1,
  },
  cities: [
    {
      cityId: "changsha",
      cityName: "长沙",
      district: "岳麓区",
      dataStatus: "ready",
      hasValidResult: true,
      stale: false,
      scenario: { scenarioId: "scenario-1", name: "基准", status: "calculated", calculatedAt: "2026-09-08T00:00:00Z", modelVersion: "test-v1", snapshotId: "snapshot-1" },
      metrics: { targetCustomers: 100, monthlyRevenue: 1000, monthlyNetProfit: 200, initialInvestment: 5000, paybackMonth: 12, cumulativeNetProfit: 4800 },
      monthlyTrend: [],
      costBreakdown: { caregiverCost: 300, salesCost: 100, nurseCost: 50, fixedCost: 150 },
      issueCount: 1,
      dataCompleteness: 100,
      projectId: "project-1",
      projectIds: ["project-1"],
    },
    {
      cityId: "zhuzhou",
      cityName: "株洲",
      district: null,
      dataStatus: "stale",
      hasValidResult: true,
      stale: true,
      scenario: { scenarioId: "scenario-2", name: "扩张", status: "stale", calculatedAt: "2026-09-07T00:00:00Z", modelVersion: "test-v1", snapshotId: "snapshot-2" },
      metrics: { targetCustomers: null, monthlyRevenue: null, monthlyNetProfit: null, initialInvestment: null, paybackMonth: null, cumulativeNetProfit: null },
      monthlyTrend: [],
      costBreakdown: { caregiverCost: null, salesCost: null, nurseCost: null, fixedCost: null },
      issueCount: 0,
      dataCompleteness: 0,
      projectId: "project-2",
      projectIds: ["project-2"],
    },
  ],
  trend: [],
  alerts: [{ type: "stale", severity: "warning", cityId: "zhuzhou", cityName: "株洲", message: "参数已修改，结果待重算", href: "/projects/project-2" }, { type: "issue", severity: "warning", cityId: "changsha", cityName: "长沙", message: "有 1 个待确认问题", href: "/projects/project-1" }],
  policySummary: { pendingReviewCount: 1, cities: [], alerts: [{ type: "policy", severity: "info", cityId: "changsha", cityName: "长沙", message: "有政策文件待审核", href: "/policies/changsha" }] },
};

afterEach(() => cleanup());

describe("DashboardOverview", () => {
  it("renders the global title and eligible city count", () => {
    render(<DashboardOverview initialData={baseResponse} />);

    expect(screen.getByRole("heading", { name: "总览" })).toBeInTheDocument();
    expect(screen.getByText(/1 个城市有有效测算结果/)).toBeInTheDocument();
  });

  it("emits a city scope change when a city checkbox is toggled", () => {
    const onQueryChange = vi.fn();
    render(<DashboardOverview initialData={baseResponse} onQueryChange={onQueryChange} />);

    fireEvent.click(screen.getByRole("checkbox", { name: /长沙/ }));

    expect(onQueryChange).toHaveBeenCalledWith(expect.objectContaining({ scope: "city", cityIds: ["changsha"] }));
  });

  it("emits a compare scope change when two cities are checked", () => {
    const onQueryChange = vi.fn();
    render(<DashboardOverview initialData={baseResponse} onQueryChange={onQueryChange} />);

    fireEvent.click(screen.getByRole("checkbox", { name: /长沙/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /株洲/ }));

    expect(onQueryChange).toHaveBeenLastCalledWith(expect.objectContaining({ scope: "compare", cityIds: ["changsha", "zhuzhou"] }));
  });

  it("renders the single-city analysis view with the policy extraction section", async () => {
    const singleCity: DashboardOverviewResponse = {
      ...baseResponse,
      scope: "city",
      cities: [baseResponse.cities[0]],
    };
    vi.spyOn(await import("@/lib/policies"), "getPolicyCityDetail").mockResolvedValue({
      cityId: "changsha",
      cityName: "长沙",
      documents: [],
      dataSources: [
        { id: "s1", cityId: "changsha", name: "长沙医保局", kind: "web", url: "https://example.gov.cn", status: "active", createdAt: "2026-09-01T00:00:00Z", updatedAt: "2026-09-08T00:00:00Z", lastFetchedAt: "2026-09-08T00:00:00Z" },
      ],
      facts: [
        { id: "f1", cityId: "changsha", documentId: null, fieldId: "P1", value: 60, status: "candidate", quote: "每月不低于60小时", source: "https://example.gov.cn" },
        { id: "f2", cityId: "changsha", documentId: null, fieldId: "P2", value: 0.8, status: "approved", effectiveDate: "2026-01-01" },
      ],
      approvedFacts: [],
      pendingReviewCount: 1,
      projects: [{ id: "project-1", name: "长沙" }],
    });

    render(<DashboardOverview initialData={singleCity} />);

    expect(screen.getByRole("heading", { name: "长沙营收分析" })).toBeInTheDocument();
    expect(screen.getByText("政策信息提炼")).toBeInTheDocument();
    expect(await screen.findByText(/待审核候选字段（1）/)).toBeInTheDocument();
    expect(screen.getByText(/已采用政策字段（1）/)).toBeInTheDocument();
  });

  it("shows empty guidance when no city has a valid result", () => {
    const empty = { ...baseResponse, summary: { ...baseResponse.summary, eligibleCityCount: 0 }, cities: [] };
    render(<DashboardOverview initialData={empty} />);

    expect(screen.getByText("暂无有效测算结果")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "进入城市测算" })).toHaveAttribute("href", "/projects");
  });

  it("keeps stale, policy and issue alerts visible with next-step links", () => {
    render(<DashboardOverview initialData={baseResponse} />);

    expect(screen.getByText("参数已修改，结果待重算")).toBeInTheDocument();
    expect(screen.getByText("有政策文件待审核")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /查看/ }).some((link) => /projects|policies/.test(link.getAttribute("href") ?? ""))).toBe(true);
  });
});
