"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { IconChevronRight, IconFileDescription, IconRefresh } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { formatPolicyDate, getPolicyOverview, type PolicyCitySummary, type PolicyOverviewResponse } from "@/lib/policies";

const STATUS_LABELS = {
  active: { label: "来源正常", variant: "success" as const },
  paused: { label: "来源暂停", variant: "warning" as const },
  error: { label: "来源异常", variant: "danger" as const },
  missing: { label: "暂无来源", variant: "neutral" as const },
};

export function PolicyOverview({
  initialData,
  onCityChange,
  loadData,
}: Readonly<{
  initialData?: PolicyOverviewResponse;
  onCityChange?: (cityId: string) => void;
  loadData?: (cityIds: string[]) => Promise<PolicyOverviewResponse>;
}>) {
  const [data, setData] = useState<PolicyOverviewResponse | undefined>(initialData);
  const [knownCities, setKnownCities] = useState<PolicyCitySummary[]>(initialData?.cities ?? []);
  const [selectedCity, setSelectedCity] = useState("");
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState<string | null>(null);
  const cities = useMemo(() => knownCities, [knownCities]);
  const visibleCities = selectedCity ? cities.filter((city) => city.cityId === selectedCity) : cities;

  async function refresh(cityId = selectedCity) {
    setLoading(true);
    setError(null);
    try {
      const nextData = await (loadData ?? getPolicyOverview)(cityId ? [cityId] : []);
      setData(nextData);
      setKnownCities((current) => Array.from(new Map([...current, ...nextData.cities].map((city) => [city.cityId, city])).values()));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "政策资料加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (initialData) return;
    let active = true;
    getPolicyOverview()
      .then((nextData) => {
        if (!active) return;
        setData(nextData);
        setKnownCities(nextData.cities);
      })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "政策资料加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [initialData]);

  function changeCity(cityId: string) {
    setSelectedCity(cityId);
    onCityChange?.(cityId);
    if (loadData) void refresh(cityId);
  }

  if (loading && !data) return <div className="space-y-4" aria-label="正在加载政策资料"><Skeleton className="h-24 w-full" /><Skeleton className="h-56 w-full" /></div>;
  if (error && !data) return <div className="space-y-5"><PageHeader eyebrow="POLICY" title="政策资料加载失败" description={error} /><Card className="border-danger/30"><CardContent className="flex items-center justify-between gap-4 p-5"><p className="text-sm text-danger">请确认 API 服务已启动。</p><Button variant="outline" onClick={() => void refresh()}><IconRefresh size={16} stroke={1.75} />重试</Button></CardContent></Card></div>;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="POLICY CENTER" title="政策资料" description="维护城市政策原文、来源和结构化事实；候选值必须经人工审核后才能作为参考。" actions={<Button variant="outline" onClick={() => void refresh()} disabled={loading}><IconRefresh size={16} stroke={1.75} />{loading ? "刷新中…" : "刷新资料"}</Button>} />
      <div className="flex flex-wrap items-end justify-between gap-4">
        <label className="grid gap-1.5 text-sm font-medium" htmlFor="policy-city-filter">城市<select id="policy-city-filter" aria-label="城市" value={selectedCity} onChange={(event) => changeCity(event.target.value)} className="h-9 min-w-52 rounded-md border border-border bg-background px-3 text-sm font-normal text-foreground"><option value="">全部城市</option>{cities.map((city) => <option key={city.cityId} value={city.cityId}>{city.cityName}</option>)}</select></label>
        <div className="flex flex-wrap gap-2"><Badge variant="warning">待审核 {data.pendingReviewCount}</Badge><Badge variant="success">已确认 {data.approvedFactCount}</Badge></div>
      </div>
      {error ? <Card className="border-danger/30"><CardContent className="p-4 text-sm text-danger">{error}。当前仍显示最近一次成功加载的数据。</CardContent></Card> : null}
      {visibleCities.length === 0 ? <EmptyState title="暂无政策资料" description="上传城市政策 Word、Excel 或 PDF 后，先保留原文，再提交候选字段供人工审核。" actionLabel="进入政策资料" actionHref="/policies" /> : <div className="grid gap-4 lg:grid-cols-2">{visibleCities.map((city) => { const sourceStatus = STATUS_LABELS[city.sourceStatus] ?? STATUS_LABELS.missing; return <Card key={city.cityId}><CardHeader className="flex-row items-start justify-between gap-3"><div><CardTitle>{city.cityName}</CardTitle><p className="mt-1 text-sm text-muted-foreground">{city.documentCount} 份文件 · 最近更新 {formatPolicyDate(city.latestUpdatedAt)}</p></div><Badge variant={sourceStatus.variant}>{sourceStatus.label}</Badge></CardHeader><CardContent className="space-y-4 pt-0"><div className="grid gap-3 sm:grid-cols-4"><div><p className="text-xs text-muted-foreground">待审核</p><p className="mt-1 text-lg font-semibold tabular-nums">{city.pendingReviewCount}</p></div><div><p className="text-xs text-muted-foreground">已确认字段</p><p className="mt-1 text-lg font-semibold tabular-nums">{city.approvedFactCount}</p></div><div><p className="text-xs text-muted-foreground">资料完整度</p><p className="mt-1 text-lg font-semibold tabular-nums">{city.completeness === null ? "—" : `${city.completeness}%`}</p></div><div><p className="text-xs text-muted-foreground">关联项目</p><p className="mt-1 text-lg font-semibold tabular-nums">{city.affectedProjectCount}</p></div></div><div className="flex items-center justify-between gap-3 border-t border-border pt-3"><span className="inline-flex items-center gap-2 text-sm text-muted-foreground"><IconFileDescription size={16} stroke={1.75} />原文和版本记录保留</span><Button asChild size="sm" variant="outline"><Link href={`/policies/${city.cityId}`}>查看详情<IconChevronRight size={15} stroke={1.75} /></Link></Button></div></CardContent></Card>; })}</div>}
    </div>
  );
}
