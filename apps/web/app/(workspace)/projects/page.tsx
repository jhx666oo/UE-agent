"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IconFolderPlus } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { listProjects, type ProjectRecord } from "@/lib/api";
import { formatDashboardMoney, formatDashboardNumber } from "@/lib/dashboard";

const STATUS_LABELS: Record<string, { label: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  draft: { label: "草稿", variant: "neutral" },
  stale: { label: "待重算", variant: "warning" },
  calculating: { label: "计算中", variant: "info" },
  calculated: { label: "已计算", variant: "success" },
  confirmed: { label: "已确认", variant: "success" },
  failed: { label: "计算失败", variant: "danger" },
  blocked: { label: "不可用", variant: "danger" },
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "项目加载失败"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="PROJECTS"
        title="项目"
        description="每个城市项目都记录范围、场景、模型版本和复核状态。"
        actions={
          <Button asChild>
            <Link href="/projects/new">
              <IconFolderPlus size={16} stroke={1.8} />
              新建项目
            </Link>
          </Button>
        }
      />
      {loading ? (
        <div className="space-y-3" aria-label="正在加载项目">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : error ? (
        <Card className="border-danger/30">
          <CardContent className="p-5 text-sm text-danger">{error}</CardContent>
        </Card>
      ) : projects.length === 0 ? (
        <EmptyState title="还没有城市项目" description="创建第一个城市项目后，可以进入参数配置、场景测算和结果复核。" actionLabel="创建项目" actionHref="/projects/new" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {projects.map((project) => (
            <Card key={project.id}>
              <CardHeader>
                <CardTitle>{project.name}</CardTitle>
                <p className="text-sm text-muted-foreground">{project.city}{project.district ? ` · ${project.district}` : ""}</p>
              </CardHeader>
              <CardContent className="space-y-4 pt-0">
                {(() => {
                  const latest = [...project.scenarios].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))[0];
                  const status = latest ? STATUS_LABELS[latest.status] ?? STATUS_LABELS.draft : STATUS_LABELS.draft;
                  const metrics = latest?.result?.headlineMetrics ?? {};
                  const payback = metrics.payback_month?.value;
                  const profit = metrics.platform_monthly_net_profit?.value;
                  return <div className="grid gap-3 sm:grid-cols-3"><div><p className="text-xs text-muted-foreground">当前场景</p><p className="mt-1 text-sm font-medium">{latest?.name ?? "尚未创建"}</p></div><div><p className="text-xs text-muted-foreground">状态</p><div className="mt-1"><Badge variant={status.variant}>{status.label}</Badge></div></div><div><p className="text-xs text-muted-foreground">最近测算</p><p className="mt-1 text-sm text-muted-foreground">{latest?.calculatedAt ? new Date(latest.calculatedAt).toLocaleString("zh-CN") : "—"}</p></div><div><p className="text-xs text-muted-foreground">回本周期</p><p className="mt-1 text-sm tabular-nums">{typeof payback === "number" ? `${formatDashboardNumber(payback)} 个月` : "—"}</p></div><div><p className="text-xs text-muted-foreground">平台期月净利润</p><p className="mt-1 text-sm tabular-nums">{typeof profit === "number" ? formatDashboardMoney(profit) : "—"}</p></div><div><p className="text-xs text-muted-foreground">场景数量</p><p className="mt-1 text-sm tabular-nums">{project.scenarios.length} 个</p></div></div>;
                })()}
                <div className="flex items-center justify-between gap-4 border-t border-border pt-3"><p className="text-xs text-muted-foreground">更新于 {new Date(project.updatedAt).toLocaleString("zh-CN")}</p><Button asChild size="sm" variant="outline"><Link href={`/projects/${project.id}`}>打开项目</Link></Button></div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
