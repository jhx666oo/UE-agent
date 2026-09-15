"use client";

import React from "react";
import Link from "next/link";
import { IconChevronRight, IconFileText } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { formatDashboardDate } from "@/lib/dashboard";
import type { DashboardPolicySummary } from "@/lib/dashboard";

function Metric({ label, value }: Readonly<{ label: string; value: number }>) {
  return (
    <div className="rounded-md border border-border bg-surface-subtle px-3 py-2.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value} 个</p>
    </div>
  );
}

export function DashboardPolicySummary({ summary }: Readonly<{ summary: DashboardPolicySummary }>) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>政策资料同步</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            官网来源、抓取记录和灰色建议值会同步到这里；采用建议值后再进入城市测算。
          </p>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link href="/policies">
            <IconFileText size={15} stroke={1.75} />查看政策资料<IconChevronRight size={15} stroke={1.75} />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="已配置来源" value={summary.sourceCount} />
          <Metric label="正常来源" value={summary.activeSourceCount} />
          <Metric label="抓取记录" value={summary.crawlCount} />
          <Metric label="待采用建议值" value={summary.suggestionCount} />
          <Metric label="需浏览器兜底" value={summary.fallbackRequiredCount} />
        </div>
        {summary.cities.length === 0 ? (
          <p className="rounded-md border border-border bg-surface-subtle px-3 py-2 text-sm text-muted-foreground">
            还没有城市政策来源。进入政策资料页配置公开官网链接即可开始抓取。
          </p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full min-w-[640px] text-[13px]">
              <thead className="bg-surface-subtle text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-2.5 font-medium">城市</th>
                  <th className="px-3 py-2.5 text-right font-medium">来源</th>
                  <th className="px-3 py-2.5 text-right font-medium">抓取记录</th>
                  <th className="px-3 py-2.5 text-right font-medium">待采用建议值</th>
                  <th className="px-3 py-2.5 text-right font-medium">最近抓取</th>
                </tr>
              </thead>
              <tbody>
                {summary.cities.map((city) => (
                  <tr key={city.cityId} className="border-t border-border">
                    <td className="px-3 py-2.5">
                      <Link className="font-medium hover:underline" href={`/policies/${encodeURIComponent(city.cityId)}`}>
                        {city.cityName}
                      </Link>
                      {city.errorSourceCount > 0 ? <Badge className="ml-2" variant="danger">{city.errorSourceCount} 个异常</Badge> : null}
                      {city.fallbackRequiredCount > 0 ? <Badge className="ml-2" variant="warning">{city.fallbackRequiredCount} 个需浏览器</Badge> : null}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{city.activeSourceCount}/{city.sourceCount}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{city.crawlCount}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{city.suggestionCount}</td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">{formatDashboardDate(city.lastFetchedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
