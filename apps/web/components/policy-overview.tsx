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
import {
  formatPolicyDate,
  getPolicyOverview,
  type PolicyCitySummary,
  type PolicyOverviewResponse,
} from "@/lib/policies";

const STATUS_LABELS = {
  active: { label: "来源正常", variant: "success" as const },
  paused: { label: "来源暂停", variant: "warning" as const },
  error: { label: "来源异常", variant: "danger" as const },
  missing: { label: "暂无来源", variant: "neutral" as const },
  partial_failed: { label: "部分失败", variant: "warning" as const },
  fallback_required: { label: "需浏览器通道", variant: "warning" as const },
};

function Metric({ label, value }: Readonly<{ label: string; value: number | string }>) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

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
      setKnownCities((current) =>
        Array.from(new Map([...current, ...nextData.cities].map((city) => [city.cityId, city])).values()),
      );
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
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "政策资料加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [initialData]);

  function changeCity(cityId: string) {
    setSelectedCity(cityId);
    onCityChange?.(cityId);
    if (loadData) void refresh(cityId);
  }

  if (loading && !data) {
    return (
      <div className="space-y-4" aria-label="正在加载政策资料">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }
  if (error && !data) {
    return (
      <div className="space-y-5">
        <PageHeader eyebrow="POLICY" title="政策资料加载失败" description={error} />
        <Card className="border-danger/30">
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <p className="text-sm text-danger">请确认 API 服务已启动。</p>
            <Button variant="outline" onClick={() => void refresh()}>
              <IconRefresh size={16} stroke={1.75} />重试
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="POLICY CENTER"
        title="政策资料"
        description="配置公开官网链接，一键抓取最新原文；系统会把可识别数据生成灰色建议值，采用后才进入城市测算。"
        actions={
          <Button variant="outline" onClick={() => void refresh()} disabled={loading}>
            <IconRefresh size={16} stroke={1.75} />
            {loading ? "刷新中…" : "刷新资料"}
          </Button>
        }
      />

      <div className="flex flex-wrap items-end justify-between gap-4">
        <label className="grid gap-1.5 text-sm font-medium" htmlFor="policy-city-filter">
          城市
          <select
            id="policy-city-filter"
            aria-label="城市"
            value={selectedCity}
            onChange={(event) => changeCity(event.target.value)}
            className="h-9 min-w-52 rounded-md border border-border bg-background px-3 text-sm font-normal text-foreground"
          >
            <option value="">全部城市</option>
            {cities.map((city) => (
              <option key={city.cityId} value={city.cityId}>
                {city.cityName}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          <Badge variant="info">已配置来源 {data.sourceCount}</Badge>
          <Badge variant="success">已抓取记录 {data.crawlCount}</Badge>
          <Badge variant="warning">待采用建议值 {data.suggestionCount}</Badge>
          {data.fallbackRequiredCount > 0 ? (
            <Badge variant="warning">需浏览器兜底 {data.fallbackRequiredCount}</Badge>
          ) : null}
        </div>
      </div>

      {error ? (
        <Card className="border-danger/30">
          <CardContent className="p-4 text-sm text-danger">{error}。当前仍显示最近一次成功加载的数据。</CardContent>
        </Card>
      ) : null}

      {visibleCities.length === 0 ? (
        <EmptyState
          title="暂无政策资料"
          description="先创建城市测算，再配置公开官网链接并点击“立即抓取”；原文和抓取记录会自动保存在本地。"
          actionLabel="进入城市测算"
          actionHref="/projects"
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {visibleCities.map((city) => {
            const sourceStatus = STATUS_LABELS[city.sourceStatus] ?? STATUS_LABELS.missing;
            return (
              <Card key={city.cityId}>
                <CardHeader className="flex-row items-start justify-between gap-3">
                  <div>
                    <CardTitle>{city.cityName}</CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {city.sourceCount} 个官网来源 · {city.crawlCount} 条抓取记录 · 最近抓取 {formatPolicyDate(city.lastFetchedAt)}
                    </p>
                  </div>
                  <Badge variant={sourceStatus.variant}>{sourceStatus.label}</Badge>
                </CardHeader>
                <CardContent className="space-y-4 pt-0">
                  <div className="grid gap-3 sm:grid-cols-5">
                    <Metric label="官网来源" value={`${city.sourceCount} 个`} />
                    <Metric label="正常来源" value={`${city.activeSourceCount} 个`} />
                    <Metric label="需浏览器兜底" value={`${city.fallbackRequiredCount} 个`} />
                    <Metric label="待采用建议值" value={`${city.suggestionCount} 项`} />
                    <Metric label="关联项目" value={`${city.affectedProjectCount} 个`} />
                  </div>
                  <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
                    <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                      <IconFileDescription size={16} stroke={1.75} />原文、指纹和版本记录已保留
                    </span>
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/policies/${city.cityId}`}>
                        查看详情<IconChevronRight size={15} stroke={1.75} />
                      </Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
