import { describe, expect, it, vi } from "vitest";
import {
  buildCostStructure,
  buildDashboardQuery,
  cityMetricStanding,
  getDashboardOverview,
  metricMedian,
  resolveDashboardScope,
  resolveViewMode,
  type DashboardOverviewResponse,
} from "./dashboard";

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

describe("Dashboard view routing", () => {
  it("maps the city checkbox selection to a scope and view mode", () => {
    expect(resolveDashboardScope([])).toBe("global");
    expect(resolveDashboardScope(["changsha"])).toBe("city");
    expect(resolveDashboardScope(["changsha", "zhuzhou"])).toBe("compare");
    expect(resolveViewMode("global")).toBe("overview");
    expect(resolveViewMode("city")).toBe("single-city");
    expect(resolveViewMode("compare")).toBe("multi-city");
  });

  it("falls back to the global overview when the selection exceeds the compare limit", () => {
    expect(resolveDashboardScope(["a", "b", "c", "d", "e", "f"])).toBe("global");
  });
});

describe("City standing against peers", () => {
  it("computes an even-length median and marks the better side", () => {
    expect(metricMedian([1, 2, 3, 4])).toBe(2.5);
    expect(metricMedian([])).toBeNull();

    const standing = cityMetricStanding(100, [50, 100, 150, 200]);
    expect(standing.median).toBe(125);
    expect(standing.best).toBe(200);
    expect(standing.comparison).toBe("below");
  });

  it("treats a shorter payback as better when the direction is lower-is-better", () => {
    const standing = cityMetricStanding(10, [10, 20, 30], "lower-is-better");
    expect(standing.best).toBe(10);
    expect(standing.comparison).toBe("below");
    expect(standing.delta).toBe(-10);
  });

  it("keeps unknown when the city or the peer set has no numeric value", () => {
    expect(cityMetricStanding(null, [1, 2]).comparison).toBe("unknown");
    expect(cityMetricStanding(5, []).comparison).toBe("unknown");
  });
});

describe("Cost structure", () => {
  it("sums non-null components and derives ratios", () => {
    const { slices, total } = buildCostStructure({ caregiverCost: 300, salesCost: 100, nurseCost: null, fixedCost: 100 });
    expect(total).toBe(500);
    expect(slices.find((slice) => slice.key === "caregiverCost")?.ratio).toBeCloseTo(0.6);
    expect(slices.find((slice) => slice.key === "nurseCost")?.ratio).toBeNull();
  });

  it("returns a null total when every component is missing", () => {
    const { slices, total } = buildCostStructure({ caregiverCost: null, salesCost: null, nurseCost: null, fixedCost: null });
    expect(total).toBeNull();
    expect(slices.every((slice) => slice.ratio === null)).toBe(true);
  });
});
