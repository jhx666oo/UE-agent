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

export type DashboardApiError = ApiError;
