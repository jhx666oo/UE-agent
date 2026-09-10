import { apiFetch, type ApiError } from "@/lib/api";

export type DashboardScope = "global" | "city" | "compare";
export type DashboardPeriod = 12 | 24;
export type DashboardDataStatus = "ready" | "stale" | "missing" | "failed";

export type DashboardQuery = {
  scope: DashboardScope;
  cityIds: string[];
  period: DashboardPeriod;
  includeStale: boolean;
};

export type DashboardMetricSet = {
  targetCustomers: number | null;
  monthlyRevenue: number | null;
  monthlyNetProfit: number | null;
  initialInvestment: number | null;
  paybackMonth: number | null;
  cumulativeNetProfit: number | null;
};

export type DashboardCity = {
  cityId: string;
  cityName: string;
  district: string | null;
  dataStatus: DashboardDataStatus;
  hasValidResult: boolean;
  stale: boolean;
  scenario: {
    scenarioId: string | null;
    name: string | null;
    status: string;
    calculatedAt: string | null;
    modelVersion: string | null;
    snapshotId: string | null;
  };
  metrics: DashboardMetricSet;
  monthlyTrend: Array<{ month: number; stage: string | null; revenue: number | null; netProfit: number | null; cumulativeCashFlow: number | null }>;
  costBreakdown: { caregiverCost: number | null; salesCost: number | null; nurseCost: number | null; fixedCost: number | null };
  issueCount: number;
  dataCompleteness: number;
  projectId: string | null;
  projectIds: string[];
};

export type DashboardAlert = {
  type: string;
  severity: "info" | "warning" | "danger";
  cityId?: string;
  cityName?: string;
  message: string;
  href: string;
};

export type DashboardOverviewResponse = {
  scope: DashboardScope;
  period: DashboardPeriod;
  scenarioRule: "latest";
  includeStale: boolean;
  updatedAt: string;
  summary: {
    eligibleCityCount: number;
    totalCityCount: number;
    targetCustomers: number | null;
    monthlyRevenue: number | null;
    monthlyNetProfit: number | null;
    initialInvestment: number | null;
    cumulativeNetProfit: number | null;
    paybackMedian: number | null;
    paybackDistribution: Array<{ range: string; count: number }>;
    pendingIssueCount: number;
  };
  cities: DashboardCity[];
  trend: Array<{ month: number; stage: string | null; revenue: number | null; netProfit: number | null; cumulativeCashFlow: number | null }>;
  alerts: DashboardAlert[];
  policySummary: { pendingReviewCount: number; cities: Array<Record<string, unknown>>; alerts: DashboardAlert[] };
};

export function buildDashboardQuery(query: DashboardQuery): string {
  const params = new URLSearchParams();
  params.set("scope", query.scope);
  if (query.cityIds.length > 0) params.set("cityIds", query.cityIds.join(","));
  params.set("period", String(query.period));
  params.set("scenario", "latest");
  params.set("includeStale", String(query.includeStale));
  return params.toString();
}

export function getDashboardOverview(
  query: DashboardQuery,
  fetcher: <T>(path: string, init?: RequestInit) => Promise<T> = apiFetch,
): Promise<DashboardOverviewResponse> {
  return fetcher<DashboardOverviewResponse>(`/api/dashboard/overview?${buildDashboardQuery(query)}`);
}

export function formatDashboardNumber(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits }).format(value);
}

export function formatDashboardMoney(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${formatDashboardNumber(value)} 元`;
}

export function formatDashboardDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
}

/** 城市复选框选择 → 视图形态。沿用 PRD 9.2：多城市对比上限 5 个。 */
export const MAX_COMPARE_CITIES = 5;

export function resolveDashboardScope(cityIds: string[]): DashboardScope {
  if (cityIds.length === 0 || cityIds.length > MAX_COMPARE_CITIES) return "global";
  return cityIds.length === 1 ? "city" : "compare";
}

export type DashboardViewMode = "overview" | "single-city" | "multi-city";

export function resolveViewMode(scope: DashboardScope): DashboardViewMode {
  if (scope === "city") return "single-city";
  if (scope === "compare") return "multi-city";
  return "overview";
}

/** 在全体城市中定位某个指标：返回该城市值与全体中位数、最优值的相对关系。 */
export type CityMetricStanding = {
  value: number | null;
  median: number | null;
  best: number | null;
  /** 与中位数比较：positive 表示优于中位数。高优指标的「优」= 更大；回本周期 = 更小。 */
  delta: number | null;
  comparison: "above" | "below" | "equal" | "unknown";
};

export function metricMedian(values: Array<number | null | undefined>): number | null {
  const usable = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (usable.length === 0) return null;
  const sorted = [...usable].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

export function cityMetricStanding(
  cityValue: number | null | undefined,
  allValues: Array<number | null | undefined>,
  direction: "higher-is-better" | "lower-is-better" = "higher-is-better",
): CityMetricStanding {
  const value = typeof cityValue === "number" && Number.isFinite(cityValue) ? cityValue : null;
  const usable = allValues.filter((item): item is number => typeof item === "number" && Number.isFinite(item));
  const median = metricMedian(usable);
  const best = usable.length === 0 ? null : direction === "higher-is-better" ? Math.max(...usable) : Math.min(...usable);
  const delta = value === null || median === null ? null : value - median;
  const comparison: CityMetricStanding["comparison"] =
    value === null || median === null ? "unknown" : value > median ? "above" : value < median ? "below" : "equal";
  return { value, median, best, delta, comparison };
}

export type CostStructureSlice = {
  key: "caregiverCost" | "salesCost" | "nurseCost" | "fixedCost";
  label: string;
  value: number | null;
  ratio: number | null;
};

const COST_LABELS: Record<CostStructureSlice["key"], string> = {
  caregiverCost: "照护师成本",
  salesCost: "销售成本",
  nurseCost: "护士成本",
  fixedCost: "固定成本",
};

export function buildCostStructure(breakdown: {
  caregiverCost: number | null;
  salesCost: number | null;
  nurseCost: number | null;
  fixedCost: number | null;
}): { slices: CostStructureSlice[]; total: number | null } {
  const slices = (Object.keys(COST_LABELS) as Array<CostStructureSlice["key"]>).map((key) => ({
    key,
    label: COST_LABELS[key],
    value: breakdown[key],
    ratio: null as number | null,
  }));
  const total = slices.reduce<number | null>((acc, slice) => {
    if (typeof slice.value !== "number") return acc;
    return (acc ?? 0) + slice.value;
  }, null);
  if (total && total > 0) {
    for (const slice of slices) {
      slice.ratio = typeof slice.value === "number" ? slice.value / total : null;
    }
  }
  return { slices, total };
}

export type DashboardApiError = ApiError;
