"use client";

import React from "react";
import { IconAdjustmentsHorizontal } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import {
  MAX_COMPARE_CITIES,
  resolveDashboardScope,
  type DashboardCity,
  type DashboardPeriod,
  type DashboardQuery,
} from "@/lib/dashboard";

const DATA_STATUS_LABELS: Record<DashboardCity["dataStatus"], string> = {
  ready: "已计算",
  stale: "待重算",
  missing: "暂无结果",
  failed: "计算失败",
};

export function DashboardFilters({
  query,
  cities,
  onChange,
}: Readonly<{
  query: DashboardQuery;
  cities: DashboardCity[];
  onChange: (query: DashboardQuery) => void;
}>) {
  const selected = new Set(query.cityIds);
  const overLimit = query.cityIds.length > MAX_COMPARE_CITIES;

  function toggleCity(cityId: string) {
    const next = selected.has(cityId) ? query.cityIds.filter((id) => id !== cityId) : [...query.cityIds, cityId];
    onChange({ ...query, cityIds: next, scope: resolveDashboardScope(next) });
  }

  function clearCities() {
    onChange({ ...query, cityIds: [], scope: "global" });
  }

  function selectAll() {
    const all = cities.map((city) => city.cityId).slice(0, MAX_COMPARE_CITIES);
    onChange({ ...query, cityIds: all, scope: resolveDashboardScope(all) });
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="dashboard-period">统计周期</label>
            <select
              id="dashboard-period"
              className="flex h-10 w-56 rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-focus-ring focus:ring-2 focus:ring-focus-ring/20"
              value={query.period}
              onChange={(event) => onChange({ ...query, period: Number(event.target.value) as DashboardPeriod })}
            >
              <option value="12">12 个月</option>
              <option value="24">24 个月</option>
            </select>
          </div>
          <label className="flex h-10 items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={query.includeStale} onChange={(event) => onChange({ ...query, includeStale: event.target.checked })} />
            保留待重算结果
          </label>
        </div>

        <div className="space-y-2 border-t border-border pt-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <IconAdjustmentsHorizontal size={16} stroke={1.75} className="text-muted-foreground" />
              <span className="text-sm font-medium" id="dashboard-city-group-label">城市视图</span>
              <Badge variant={selected.size === 0 ? "neutral" : selected.size === 1 ? "info" : "success"}>
                {selected.size === 0 ? "全城汇总" : selected.size === 1 ? "单城分析" : `多城对比 ${selected.size}`}
              </Badge>
            </div>
            <div className="flex gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={selectAll} disabled={cities.length === 0}>全选前 5 个</Button>
              <Button type="button" size="sm" variant="ghost" onClick={clearCities} disabled={selected.size === 0}>清除选择</Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            不勾选＝全部已创建城市汇总对比；勾选 1 个＝该城市营收分析；勾选 2–{MAX_COMPARE_CITIES} 个＝多城对比（超出上限按汇总处理）。
          </p>
          {cities.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {selected.size > 0 ? "正在加载城市列表…" : "还没有可选择的城市，请先新增城市并完成一次测算。"}
            </p>
          ) : (
            <div role="group" aria-labelledby="dashboard-city-group-label" className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {cities.map((city) => {
                const checked = selected.has(city.cityId);
                return (
                  <label
                    key={city.cityId}
                    className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 transition-colors ${
                      checked ? "border-primary/40 bg-surface-selected" : "border-border bg-surface hover:bg-surface-subtle"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={checked}
                      disabled={!checked && selected.size >= MAX_COMPARE_CITIES}
                      onChange={() => toggleCity(city.cityId)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-medium">{city.cityName}</span>
                        <span className="text-xs text-muted-foreground">{DATA_STATUS_LABELS[city.dataStatus]}</span>
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                        {city.district ?? "—"}
                        {city.issueCount > 0 ? ` · ${city.issueCount} 项待确认` : ""}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          )}
          {overLimit ? (
            <p className="text-xs text-warning">已选择超过 {MAX_COMPARE_CITIES} 个城市，当前按全城汇总口径展示。请减少选择以便逐城对比。</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
