import { describe, expect, it, vi } from "vitest";
import { buildDashboardQuery, getDashboardOverview, type DashboardOverviewResponse } from "./dashboard";

describe("Dashboard API client", () => {
  it("serializes scope, cities, period and stale rule into the request URL", () => {
    expect(
      buildDashboardQuery({ scope: "compare", cityIds: ["长沙", "株洲"], period: 24, includeStale: false }),
    ).toBe("scope=compare&cityIds=%E9%95%BF%E6%B2%99%2C%E6%A0%AA%E6%B4%B2&period=24&scenario=latest&includeStale=false");
  });

  it("requests the overview through apiFetch and preserves ApiError behavior", async () => {
    const response: DashboardOverviewResponse = {
      scope: "global",
      period: 12,
      scenarioRule: "latest",
      includeStale: true,
      updatedAt: "2026-09-08T00:00:00Z",
      summary: {
        eligibleCityCount: 0,
        totalCityCount: 0,
        targetCustomers: null,
        monthlyRevenue: null,
        monthlyNetProfit: null,
        initialInvestment: null,
        cumulativeNetProfit: null,
        paybackMedian: null,
        paybackDistribution: [],
        pendingIssueCount: 0,
      },
      cities: [],
      trend: [],
      alerts: [],
      policySummary: { pendingReviewCount: 0, cities: [], alerts: [] },
    };
    const fetcher = vi.fn().mockResolvedValue(response);

    await expect(getDashboardOverview({ scope: "global", cityIds: [], period: 12, includeStale: true }, fetcher)).resolves.toEqual(response);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/api/dashboard/overview?scope=global"));
  });
});
