"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { IconAlertTriangle, IconArrowLeft, IconExternalLink, IconFileText, IconLink } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { MetricCard } from "@/components/metric-card";
import {
  buildCostStructure,
  cityMetricStanding,
  formatDashboardDate,
  formatDashboardMoney,
  formatDashboardNumber,
  type CityMetricStanding,
  type DashboardCity,
} from "@/lib/dashboard";
import {
  buildCityPolicyExtract,
  factStatusLabel,
  formatPolicyDate,
  formatPolicyValue,
  getPolicyCityDetail,
  type CityPolicyExtract,
} from "@/lib/policies";

const COST_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"] as const;

function standingNote(standing: CityMetricStanding, unit: string, direction: "higher" | "lower"): string {
  if (standing.median === null || standing.value === null) return "缺少可对比数据";
  const better = direction === "higher" ? standing.comparison === "above" : standing.comparison === "below";
  const worse = direction === "higher" ? standing.comparison === "below" : standing.comparison === "above";
  const label = better ? "优于全体中位数" : worse ? "低于全体中位数" : "与全体中位数持平";
  return `${label}（中位数 ${formatDashboardNumber(standing.median)}${unit}）`;
}

export function CityFocusPanel({
  city,
  peers,
  period,
  policyHref,
}: Readonly<{
  city: DashboardCity;
  /** 全体已创建城市（用于中位数/最优值对比）。 */
  peers: DashboardCity[];
  period: number;
  policyHref?: string;
}>) {
  const [policy, setPolicy] = useState<CityPolicyExtract | null>(null);
  const [policyLoading, setPolicyLoading] = useState(true);
  const [policyError, setPolicyError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getPolicyCityDetail(city.cityId)
      .then((detail) => {
        if (!active) return;
        setPolicy(buildCityPolicyExtract(detail));
        setPolicyError(null);
      })
      .catch((requestError) => {
        if (!active) return;
        setPolicy(null);
        setPolicyError(requestError instanceof Error ? requestError.message : "城市政策资料加载失败");
      })
      .finally(() => {
        if (active) setPolicyLoading(false);
      });
    return () => {
      active = false;
    };
  }, [city.cityId]);

  const trend = city.monthlyTrend.slice(0, period);
  const cost = useMemo(() => buildCostStructure(city.costBreakdown), [city.costBreakdown]);

  const revenueStanding = cityMetricStanding(city.metrics.monthlyRevenue, peers.map((peer) => peer.metrics.monthlyRevenue));
  const profitStanding = cityMetricStanding(city.metrics.monthlyNetProfit, peers.map((peer) => peer.metrics.monthlyNetProfit));
  const paybackStanding = cityMetricStanding(city.metrics.paybackMonth, peers.map((peer) => peer.metrics.paybackMonth), "lower-is-better");
  const customersStanding = cityMetricStanding(city.metrics.targetCustomers, peers.map((peer) => peer.metrics.targetCustomers));

  const paybackRows = useMemo(() => {
    const buckets = [
      { range: "≤12 个月", match: (value: number) => value <= 12 },
      { range: "13–24 个月", match: (value: number) => value > 12 && value <= 24 },
      { range: ">24 个月", match: (value: number) => value > 24 },
      { range: "未回本", match: () => false },
    ];
    return buckets.map((bucket) => ({
      range: bucket.range,
      count: peers.filter((peer) => {
        const value = peer.metrics.paybackMonth;
        if (value === null) return bucket.range === "未回本";
        return bucket.match(value);
      }).length,
    }));
  }, [peers]);

  const riskRows = useMemo(
    () =>
      [...peers]
        .sort((left, right) => right.issueCount - left.issueCount || left.dataCompleteness - right.dataCompleteness)
        .map((peer) => ({
          cityName: peer.cityName,
          issueCount: peer.issueCount,
          dataCompleteness: peer.dataCompleteness,
          isCurrent: peer.cityId === city.cityId,
        })),
    [peers, city.cityId],
  );

  const costChartData = cost.slices.map((slice) => ({
    name: slice.label,
    value: slice.value,
    ratio: slice.ratio,
  }));

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>{city.cityName}营收分析</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {city.district ?? "—"} · 场景 {city.scenario.name ?? "—"} · 最近测算 {formatDashboardDate(city.scenario.calculatedAt)}
              {city.scenario.modelVersion ? ` · 模型 ${city.scenario.modelVersion}` : ""}
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <Badge variant={city.dataStatus === "ready" ? "success" : city.dataStatus === "stale" ? "warning" : city.dataStatus === "failed" ? "danger" : "neutral"}>
              {city.dataStatus === "ready" ? "已计算" : city.dataStatus === "stale" ? "待重算" : city.dataStatus === "failed" ? "计算失败" : "暂无结果"}
            </Badge>
            <Button asChild size="sm" variant="ghost">
              <Link href={`/projects/${city.projectId ?? ""}`}>进入城市测算<IconExternalLink size={15} stroke={1.75} /></Link>
            </Button>
          </div>
        </CardHeader>
      </Card>

      <section aria-label={`${city.cityName}核心指标`} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="目标客户规模" value={city.metrics.targetCustomers === null ? "—" : `${formatDashboardNumber(city.metrics.targetCustomers)} 人`} note={standingNote(customersStanding, " 人", "higher")} />
        <MetricCard label="平台期月收入" value={formatDashboardMoney(city.metrics.monthlyRevenue)} note={standingNote(revenueStanding, " 元", "higher")} />
        <MetricCard label="平台期月净利润" value={formatDashboardMoney(city.metrics.monthlyNetProfit)} note={standingNote(profitStanding, " 元", "higher")} />
        <MetricCard
          label="回本周期"
          value={city.metrics.paybackMonth === null ? "—" : `${formatDashboardNumber(city.metrics.paybackMonth)} 个月`}
          note={standingNote(paybackStanding, " 个月", "lower")}
        />
      </section>

      <div className="grid gap-5 xl:grid-cols-12">
        <div className="space-y-5 xl:col-span-8">
          <Card>
            <CardHeader>
              <CardTitle>营收与现金流趋势（{period} 个月）</CardTitle>
              <p className="text-sm text-muted-foreground">收入、净利润和累计现金流为单城市口径，非全市汇总。</p>
            </CardHeader>
            <CardContent>
              {trend.length === 0 ? (
                <p className="text-sm text-muted-foreground">该城市暂无月度投影数据，请先完成一次测算。</p>
              ) : (
                <div className="h-72 w-full" role="img" aria-label={`${city.cityName}营收趋势`}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trend} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                      <XAxis dataKey="month" tickFormatter={(value) => `${value}月`} />
                      <YAxis tickFormatter={(value) => formatDashboardNumber(Number(value))} />
                      <Tooltip formatter={(value, name) => [`${formatDashboardNumber(Number(value))} 元`, name === "revenue" ? "收入" : name === "netProfit" ? "净利润" : "累计现金流"]} />
                      <Legend formatter={(value) => (value === "revenue" ? "收入" : value === "netProfit" ? "净利润" : "累计现金流")} />
                      <Line type="monotone" dataKey="revenue" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="netProfit" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="cumulativeCashFlow" stroke="var(--chart-4)" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>与其他城市对比</CardTitle>
              <p className="text-sm text-muted-foreground">数值为该城市相对全体已创建城市的中位数定位。</p>
            </CardHeader>
            <CardContent className="space-y-3">
              {[
                { label: "平台期月收入", standing: revenueStanding, unit: " 元", direction: "higher" as const },
                { label: "平台期月净利润", standing: profitStanding, unit: " 元", direction: "higher" as const },
                { label: "回本周期", standing: paybackStanding, unit: " 个月", direction: "lower" as const },
                { label: "目标客户规模", standing: customersStanding, unit: " 人", direction: "higher" as const },
              ].map((row) => (
                <div key={row.label} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5">
                  <span className="text-sm">{row.label}</span>
                  <div className="flex flex-wrap items-center gap-3 text-sm tabular-nums">
                    <span className="font-medium">{row.standing.value === null ? "—" : `${formatDashboardNumber(row.standing.value)}${row.unit}`}</span>
                    <span className="text-muted-foreground">中位数 {row.standing.median === null ? "—" : `${formatDashboardNumber(row.standing.median)}${row.unit}`}</span>
                    <Badge variant={row.standing.comparison === "unknown" ? "neutral" : (row.direction === "higher" ? row.standing.comparison === "above" : row.standing.comparison === "below") ? "success" : row.standing.comparison === "equal" ? "neutral" : "warning"}>
                      {row.standing.comparison === "unknown" ? "无对比" : row.standing.comparison === "equal" ? "持平" : (row.direction === "higher" ? row.standing.comparison === "above" : row.standing.comparison === "below") ? "优于中位数" : "低于中位数"}
                    </Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5 xl:col-span-4">
          <Card>
            <CardHeader><CardTitle>平台期成本结构</CardTitle></CardHeader>
            <CardContent>
              {cost.total === null ? (
                <p className="text-sm text-muted-foreground">暂无成本数据。</p>
              ) : (
                <>
                  <div className="h-56 w-full" role="img" aria-label={`${city.cityName}成本结构`}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={costChartData} dataKey="value" nameKey="name" innerRadius={44} outerRadius={72} paddingAngle={2}>
                          {costChartData.map((entry, index) => (
                            <Cell key={entry.name} fill={COST_COLORS[index % COST_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(value) => `${formatDashboardNumber(Number(value))} 元`} />
                        <Legend />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <ul className="mt-3 space-y-1.5 text-sm">
                    {cost.slices.map((slice) => (
                      <li key={slice.key} className="flex items-center justify-between gap-3">
                        <span className="text-muted-foreground">{slice.label}</span>
                        <span className="tabular-nums">
                          {formatDashboardMoney(slice.value)}
                          {slice.ratio !== null ? <span className="ml-2 text-xs text-muted-foreground">{(slice.ratio * 100).toFixed(1)}%</span> : null}
                        </span>
                      </li>
                    ))}
                    <li className="flex items-center justify-between gap-3 border-t border-border pt-1.5">
                      <span className="font-medium">合计</span>
                      <span className="font-medium tabular-nums">{formatDashboardMoney(cost.total)}</span>
                    </li>
                  </ul>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>回本周期分布</CardTitle>
              <p className="text-sm text-muted-foreground">全体已创建城市的回本周期分布，用于判断该城市所处水平。</p>
            </CardHeader>
            <CardContent>
              <div className="h-52 w-full" role="img" aria-label="回本周期分布">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={paybackRows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                    <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="range" />
                    <YAxis allowDecimals={false} />
                    <Tooltip formatter={(value) => [`${formatDashboardNumber(Number(value))} 个城市`, "城市数"]} />
                    <Bar dataKey="count" fill="var(--chart-3)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>数据完整度与风险</CardTitle>
          <p className="text-sm text-muted-foreground">按待确认问题数排序；数据完整度来自测算输入快照的填写比例。</p>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full min-w-[560px] text-[13px]">
            <thead className="bg-surface-subtle text-left text-muted-foreground">
              <tr>
                <th className="px-5 py-3 font-medium">城市</th>
                <th className="px-5 py-3 text-right font-medium">待确认问题</th>
                <th className="px-5 py-3 text-right font-medium">数据完整度</th>
              </tr>
            </thead>
            <tbody>
              {riskRows.map((row) => (
                <tr key={row.cityName} className={row.isCurrent ? "border-t border-border bg-surface-selected" : "border-t border-border"}>
                  <td className="px-5 py-3">
                    <span className="font-medium">{row.cityName}</span>
                    {row.isCurrent ? <span className="ml-2 text-xs text-primary">当前</span> : null}
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums">{row.issueCount}</td>
                  <td className="px-5 py-3 text-right tabular-nums">{row.dataCompleteness}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>政策信息提炼</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">该城市政策来源、抓取状态与候选字段审核结果，独立于测算结果展示。</p>
          </div>
          <Button asChild size="sm" variant="outline">
            <Link href={policyHref ?? `/policies/${encodeURIComponent(city.cityId)}`}>
              <IconFileText size={15} stroke={1.75} />政策资料页
            </Link>
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {policyLoading ? (
            <div className="space-y-2" aria-label="正在加载城市政策">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : policyError ? (
            <p className="text-sm text-danger">{policyError}。可打开政策资料页查看完整来源与抓取记录。</p>
          ) : policy ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-md border border-border p-3">
                  <p className="text-xs text-muted-foreground">官网来源</p>
                  <p className="mt-1 text-sm font-medium tabular-nums">{policy.sourceCount} 个<span className="ml-1 text-xs font-normal text-muted-foreground">（正常 {policy.activeSourceCount}）</span></p>
                </div>
                <div className="rounded-md border border-border p-3">
                  <p className="text-xs text-muted-foreground">最近抓取</p>
                  <p className="mt-1 text-sm font-medium">{formatPolicyDate(policy.latestFetchedAt)}</p>
                </div>
                <div className="rounded-md border border-border p-3">
                  <p className="text-xs text-muted-foreground">待审核候选字段</p>
                  <p className="mt-1 text-sm font-medium tabular-nums">{policy.pendingReviewCount} 项</p>
                </div>
                <div className="rounded-md border border-border p-3">
                  <p className="text-xs text-muted-foreground">已采用政策字段</p>
                  <p className="mt-1 text-sm font-medium tabular-nums">{policy.approvedFactCount} 项</p>
                </div>
              </div>

              {!policy.hasData ? (
                <p className="rounded-md border border-border bg-surface-subtle px-3 py-2 text-sm text-muted-foreground">
                  该城市尚未配置政策来源或抓取记录。可在政策资料页添加官网来源后一键抓取。
                </p>
              ) : null}

              {policy.pendingFacts.length > 0 ? (
                <div className="space-y-2">
                  <p className="flex items-center gap-2 text-sm font-medium"><IconAlertTriangle size={15} stroke={1.75} className="text-warning" />待审核候选字段（{policy.pendingFacts.length}）</p>
                  <ul className="space-y-2">
                    {policy.pendingFacts.slice(0, 6).map((fact) => (
                      <li key={fact.id} className="rounded-md border border-warning/30 bg-warning-subtle p-3 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="warning">{factStatusLabel(fact.status)}</Badge>
                          <span className="font-medium">{fact.fieldId ?? "未映射字段"}</span>
                          <span className="tabular-nums">{formatPolicyValue(fact.value)}</span>
                        </div>
                        {fact.quote ? <p className="mt-1.5 text-xs text-muted-foreground">“{fact.quote}”</p> : null}
                        {fact.source ? <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground"><IconLink size={13} stroke={1.75} />{fact.source}</p> : null}
                      </li>
                    ))}
                  </ul>
                  {policy.pendingFacts.length > 6 ? <p className="text-xs text-muted-foreground">还有 {policy.pendingFacts.length - 6} 项未展示，前往政策资料页审核。</p> : null}
                </div>
              ) : null}

              {policy.approvedFacts.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-sm font-medium">已采用政策字段（{policy.approvedFacts.length}）</p>
                  <ul className="grid gap-2 sm:grid-cols-2">
                    {policy.approvedFacts.slice(0, 8).map((fact) => (
                      <li key={fact.id} className="rounded-md border border-border p-3 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="success">{factStatusLabel(fact.status)}</Badge>
                          <span className="font-medium">{fact.fieldId ?? "未映射字段"}</span>
                          <span className="tabular-nums">{formatPolicyValue(fact.value)}</span>
                        </div>
                        {fact.effectiveDate ? <p className="mt-1 text-xs text-muted-foreground">生效日期 {fact.effectiveDate}</p> : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-info/30 bg-info-subtle px-3 py-2 text-sm text-info">
                <span>采用政策建议值后需重算该城市，结果才会体现在总览。</span>
                <Link className="inline-flex items-center gap-1 underline-offset-4 hover:underline" href={`/projects/${city.projectId ?? ""}`}>
                  进入城市测算<IconArrowLeft size={14} stroke={1.75} className="rotate-180" />
                </Link>
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
