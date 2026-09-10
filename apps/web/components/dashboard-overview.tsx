"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { IconRefresh } from "@tabler/icons-react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { DashboardAlerts } from "@/components/dashboard-alerts";
import { DashboardChart } from "@/components/dashboard-chart";
import { DashboardCityComparison } from "@/components/dashboard-city-comparison";
import { DashboardFilters } from "@/components/dashboard-filters";
import { DashboardMetricGrid } from "@/components/dashboard-metric-grid";
import { getDashboardOverview, type DashboardOverviewResponse, type DashboardQuery } from "@/lib/dashboard";

const DEFAULT_QUERY: DashboardQuery = { scope: "global", cityIds: [], period: 12, includeStale: true };

export function DashboardOverview({
  initialData,
  initialQuery = DEFAULT_QUERY,
  query: controlledQuery,
  onQueryChange,
  loadData,
}: Readonly<{
  initialData?: DashboardOverviewResponse;
  initialQuery?: DashboardQuery;
  /** 受控模式：由父组件（如 nuqs URL 状态）驱动当前筛选条件。 */
  query?: DashboardQuery;
  onQueryChange?: (query: DashboardQuery) => void;
  loadData?: (query: DashboardQuery) => Promise<DashboardOverviewResponse>;
}>) {
  const isControlled = controlledQuery !== undefined;
  const [internalQuery, setInternalQuery] = useState(initialQuery);
  const query = isControlled ? controlledQuery : internalQuery;
  const [data, setData] = useState<DashboardOverviewResponse | undefined>(initialData);
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState<string | null>(null);
  const cities = useMemo(() => data?.cities ?? [], [data?.cities]);

  const fetcher = loadData ?? getDashboardOverview;

  async function refresh(nextQuery: DashboardQuery = query) {
    setLoading(true);
    setError(null);
    try {
      const nextData = await fetcher(nextQuery);
      setData(nextData);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "总览数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  // 首次加载：没有预取数据时，用当前筛选条件拉取一次。
  useEffect(() => {
    if (initialData) return;
    let active = true;
    fetcher(query)
      .then((nextData) => { if (active) setData(nextData); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "总览数据加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
    // 仅在挂载时执行一次；query 变化由 changeQuery / 受控 effect 驱动。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialData]);

  // 受控模式：URL 中的筛选条件变化时重新拉取（PRD 9.2 刷新后保留筛选）。
  const lastQueryRef = useRef<DashboardQuery | null>(isControlled ? null : query);
  useEffect(() => {
    if (!isControlled) return;
    if (lastQueryRef.current === null) {
      lastQueryRef.current = query;
      return; // 挂载那次已由上方 effect 拉取
    }
    if (lastQueryRef.current === query) return;
    lastQueryRef.current = query;
    void refresh(query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, isControlled]);

  function changeQuery(nextQuery: DashboardQuery) {
    if (!isControlled) setInternalQuery(nextQuery);
    onQueryChange?.(nextQuery);
    if (loadData) void refresh(nextQuery);
  }

  if (loading && !data) {
    return <div className="space-y-5" aria-label="正在加载总览"><Skeleton className="h-24 w-full" /><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div><Skeleton className="h-80 w-full" /></div>;
  }

  if (error && !data) {
    return <div className="space-y-5"><PageHeader eyebrow="DASHBOARD" title="总览加载失败" description={error} /><Card className="border-danger/30"><CardContent className="flex flex-wrap items-center justify-between gap-4 p-5"><p className="text-sm text-danger">请确认 API 服务已启动，并检查网络连接。</p><Button variant="outline" onClick={() => void refresh()}><IconRefresh size={16} stroke={1.75} />重试</Button></CardContent></Card></div>;
  }

  if (!data) return null;

  const hasValidCity = data.summary.eligibleCityCount > 0;
  const scopeLabel = data.scope === "global" ? "GLOBAL" : data.scope === "city" ? "CITY" : "COMPARE";
  const summaryText = `${data.summary.eligibleCityCount} 个城市有有效测算结果 · 统计周期 ${data.period} 个月 · 更新时间 ${new Date(data.updatedAt).toLocaleString("zh-CN")}`;
  const alerts = [...data.alerts, ...data.policySummary.alerts.filter((policyAlert) => !data.alerts.some((alert) => alert.type === policyAlert.type && alert.cityId === policyAlert.cityId && alert.message === policyAlert.message))];
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={`DASHBOARD / ${scopeLabel}`}
        title="总览"
        description="按每个城市最近一次有效测算结果汇总，结果绑定场景、模型版本和计算时间。"
        actions={<Button variant="outline" onClick={() => void refresh()} disabled={loading}><IconRefresh size={16} stroke={1.75} />{loading ? "刷新中…" : "刷新数据"}</Button>}
      />
      <DashboardFilters query={query} cities={cities} onChange={changeQuery} />
      {error ? <Card className="border-danger/30"><CardContent className="p-4 text-sm text-danger">{error}。当前仍显示最近一次成功加载的数据。</CardContent></Card> : null}
      <p className="text-sm text-muted-foreground">{summaryText}</p>
      {hasValidCity ? <DashboardMetricGrid summary={data.summary} /> : <EmptyState title="暂无有效测算结果" description="当前筛选范围内还没有成功测算的城市。进入城市测算配置参数并运行测算后，这里会自动汇总结果。" actionLabel="进入城市测算" actionHref="/projects" />}
      <div className="grid gap-5 xl:grid-cols-12">
        <div className="space-y-5 xl:col-span-8"><DashboardChart title="经营趋势" type="trend" data={data.trend} /><DashboardCityComparison cities={data.cities} /></div>
        <div className="space-y-5 xl:col-span-4"><DashboardChart title="月收入与月净利润对比" type="comparison" data={data.cities.map((city) => ({ cityName: city.cityName, monthlyRevenue: city.metrics.monthlyRevenue, monthlyNetProfit: city.metrics.monthlyNetProfit })).filter((city) => city.monthlyRevenue !== null || city.monthlyNetProfit !== null)} /><DashboardAlerts alerts={alerts} /></div>
      </div>
    </div>
  );
}
