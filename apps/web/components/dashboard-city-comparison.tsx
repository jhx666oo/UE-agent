import React from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Badge } from "@ue-agent/ui/components/badge";
import { formatDashboardDate, formatDashboardMoney, formatDashboardNumber, type DashboardCity } from "@/lib/dashboard";

const STATUS_LABELS: Record<DashboardCity["dataStatus"], { label: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  ready: { label: "已计算", variant: "success" },
  stale: { label: "待重算", variant: "warning" },
  missing: { label: "暂无结果", variant: "neutral" },
  failed: { label: "计算失败", variant: "danger" },
};

export function DashboardCityComparison({ cities }: Readonly<{ cities: DashboardCity[] }>) {
  return (
    <Card>
      <CardHeader><CardTitle>城市比较</CardTitle></CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full min-w-[860px] text-[13px]">
          <thead className="bg-surface-subtle text-left text-muted-foreground">
            <tr>
              <th className="px-5 py-3 font-medium">城市</th>
              <th className="px-5 py-3 text-right font-medium">目标客户</th>
              <th className="px-5 py-3 text-right font-medium">月收入</th>
              <th className="px-5 py-3 text-right font-medium">月净利润</th>
              <th className="px-5 py-3 text-right font-medium">回本周期</th>
              <th className="px-5 py-3 font-medium">数据状态</th>
              <th className="px-5 py-3 font-medium">最近测算</th>
              <th className="px-5 py-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {cities.map((city) => {
              const status = STATUS_LABELS[city.dataStatus];
              return (
                <tr key={city.cityId} className="border-t border-border">
                  <td className="px-5 py-3"><p className="font-medium">{city.cityName}</p><p className="text-xs text-muted-foreground">{city.district ?? "—"}</p></td>
                  <td className="px-5 py-3 text-right tabular-nums">{city.metrics.targetCustomers === null ? "—" : `${formatDashboardNumber(city.metrics.targetCustomers)} 人`}</td>
                  <td className="px-5 py-3 text-right tabular-nums">{formatDashboardMoney(city.metrics.monthlyRevenue)}</td>
                  <td className="px-5 py-3 text-right tabular-nums">{formatDashboardMoney(city.metrics.monthlyNetProfit)}</td>
                  <td className="px-5 py-3 text-right tabular-nums">{city.metrics.paybackMonth === null ? "—" : `${formatDashboardNumber(city.metrics.paybackMonth)} 个月`}</td>
                  <td className="px-5 py-3"><Badge variant={status.variant}>{status.label}</Badge>{city.issueCount > 0 ? <span className="ml-2 text-xs text-warning">{city.issueCount} 项待确认</span> : null}</td>
                  <td className="px-5 py-3 text-muted-foreground">{formatDashboardDate(city.scenario.calculatedAt)}</td>
                  <td className="px-5 py-3 text-right"><Link className="text-info underline-offset-4 hover:underline" href={`/projects/${city.projectId ?? ""}`}>查看城市</Link></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
