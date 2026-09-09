"use client";

import React from "react";
import type { DashboardCity, DashboardPeriod, DashboardQuery, DashboardScope } from "@/lib/dashboard";

export function DashboardFilters({
  query,
  cities,
  onChange,
}: Readonly<{
  query: DashboardQuery;
  cities: DashboardCity[];
  onChange: (query: DashboardQuery) => void;
}>) {
  function update(partial: Partial<DashboardQuery>) {
    onChange({ ...query, ...partial });
  }

  return (
    <div className="grid gap-4 border-b border-border pb-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto] md:items-end">
      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="dashboard-scope">视图</label>
        <select
          id="dashboard-scope"
          className="flex h-10 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-focus-ring focus:ring-2 focus:ring-focus-ring/20"
          value={query.scope}
          onChange={(event) => update({ scope: event.target.value as DashboardScope, cityIds: event.target.value === "global" ? [] : query.cityIds })}
        >
          <option value="global">全部城市</option>
          <option value="city">单个城市</option>
          <option value="compare">多城市对比</option>
        </select>
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="dashboard-city">城市</label>
        <select
          id="dashboard-city"
          multiple={query.scope === "compare"}
          className="flex min-h-10 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-focus-ring focus:ring-2 focus:ring-focus-ring/20"
          value={query.scope === "compare" ? query.cityIds : query.cityIds[0] ?? ""}
          onChange={(event) => {
            const selected = Array.from(event.target.selectedOptions, (option) => option.value);
            update({ cityIds: selected, scope: selected.length > 1 ? "compare" : selected.length === 1 ? "city" : "global" });
          }}
        >
          {query.scope !== "compare" ? <option value="">全部城市</option> : null}
          {cities.map((city) => <option key={city.cityId} value={city.cityId}>{city.cityName}</option>)}
        </select>
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="dashboard-period">周期</label>
        <select
          id="dashboard-period"
          className="flex h-10 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-focus-ring focus:ring-2 focus:ring-focus-ring/20"
          value={query.period}
          onChange={(event) => update({ period: Number(event.target.value) as DashboardPeriod })}
        >
          <option value="12">12 个月</option>
          <option value="24">24 个月</option>
        </select>
      </div>
      <label className="flex h-10 items-center gap-2 text-sm text-muted-foreground">
        <input type="checkbox" checked={query.includeStale} onChange={(event) => update({ includeStale: event.target.checked })} />
        保留待重算结果
      </label>
    </div>
  );
}
