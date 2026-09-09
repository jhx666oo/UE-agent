import React from "react";
import Link from "next/link";
import { IconAlertTriangle, IconChevronRight, IconFileAlert, IconRefresh } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import type { DashboardAlert } from "@/lib/dashboard";

const ALERT_LABELS: Record<string, string> = { stale: "待重算", issue: "待确认", policy: "政策资料", missing: "缺少结果" };

export function DashboardAlerts({ alerts }: Readonly<{ alerts: DashboardAlert[] }>) {
  return (
    <Card>
      <CardHeader><CardTitle>政策与风险提醒</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {alerts.length === 0 ? <p className="text-sm text-muted-foreground">当前没有待处理提醒。</p> : alerts.map((alert, index) => (
          <div key={`${alert.type}-${alert.cityId ?? "global"}-${index}`} className="flex items-start gap-3 rounded-md border border-border bg-surface-subtle p-3">
            {alert.type === "policy" ? <IconFileAlert className="mt-0.5 shrink-0 text-info" size={18} stroke={1.75} /> : alert.type === "stale" ? <IconRefresh className="mt-0.5 shrink-0 text-warning" size={18} stroke={1.75} /> : <IconAlertTriangle className="mt-0.5 shrink-0 text-warning" size={18} stroke={1.75} />}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2"><Badge variant={alert.severity === "danger" ? "danger" : alert.severity === "warning" ? "warning" : "info"}>{ALERT_LABELS[alert.type] ?? "提醒"}</Badge><span className="text-xs text-muted-foreground">{alert.cityName ?? "全局"}</span></div>
              <p className="mt-1 text-sm text-foreground">{alert.message}</p>
            </div>
            <Link href={alert.href} className="inline-flex shrink-0 items-center gap-1 text-sm text-info hover:underline" aria-label={`查看${alert.cityName ?? "提醒"}`}>
              查看 <IconChevronRight size={15} stroke={1.75} />
            </Link>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
