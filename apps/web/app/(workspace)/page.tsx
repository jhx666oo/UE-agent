"use client";

import { Suspense } from "react";
import { parseAsArrayOf, parseAsBoolean, parseAsNumberLiteral, parseAsString, parseAsStringEnum, useQueryStates } from "nuqs";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { DashboardOverview } from "@/components/dashboard-overview";
import type { DashboardQuery } from "@/lib/dashboard";

const dashboardQueryParsers = {
  scope: parseAsStringEnum(["global", "city", "compare"]).withDefault("global"),
  cityIds: parseAsArrayOf(parseAsString).withDefault([]),
  period: parseAsNumberLiteral([12, 24]).withDefault(12),
  includeStale: parseAsBoolean.withDefault(true),
};

function DashboardHome() {
  const [filters, setFilters] = useQueryStates(dashboardQueryParsers);
  const query: DashboardQuery = {
    scope: filters.scope,
    cityIds: filters.cityIds,
    period: filters.period,
    includeStale: filters.includeStale,
  };

  function changeQuery(nextQuery: DashboardQuery) {
    void setFilters({
      scope: nextQuery.scope,
      cityIds: nextQuery.cityIds,
      period: nextQuery.period,
      includeStale: nextQuery.includeStale,
    });
  }

  return <DashboardOverview query={query} onQueryChange={changeQuery} />;
}

export default function WorkspaceHomePage() {
  return (
    <Suspense fallback={<div className="space-y-5" aria-label="正在加载总览"><Skeleton className="h-24 w-full" /><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div></div>}>
      <DashboardHome />
    </Suspense>
  );
}
