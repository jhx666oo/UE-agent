import React from "react";
import { MetricCard } from "@/components/metric-card";
import { formatDashboardMoney, formatDashboardNumber } from "@/lib/dashboard";

export function DashboardMetricGrid({
  summary,
}: Readonly<{
  summary: {
    eligibleCityCount: number;
    targetCustomers: number | null;
    monthlyRevenue: number | null;
    monthlyNetProfit: number | null;
    initialInvestment: number | null;
    paybackMedian: number | null;
    pendingIssueCount: number;
  };
}>) {
  return (
    <section aria-label="核心指标" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <MetricCard label="有效测算城市" value={`${formatDashboardNumber(summary.eligibleCityCount)} 个`} note="按每城市最近有效场景统计" />
      <MetricCard label="目标客户规模" value={summary.targetCustomers === null ? "—" : `${formatDashboardNumber(summary.targetCustomers)} 人`} />
      <MetricCard label="预计月收入" value={formatDashboardMoney(summary.monthlyRevenue)} />
      <MetricCard label="预计月净利润" value={formatDashboardMoney(summary.monthlyNetProfit)} />
      <MetricCard label="总初始投资" value={formatDashboardMoney(summary.initialInvestment)} />
      <MetricCard label="回本周期中位数" value={summary.paybackMedian === null ? "—" : `${formatDashboardNumber(summary.paybackMedian)} 个月`} note={`${formatDashboardNumber(summary.pendingIssueCount)} 个待确认问题`} />
    </section>
  );
}
