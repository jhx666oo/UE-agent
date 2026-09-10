"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IconFolderPlus, IconFileDescription, IconTrash } from "@tabler/icons-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@ue-agent/ui/components/alert-dialog";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { deleteProject, listProjects, type ProjectRecord } from "@/lib/api";
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

/**
 * 统计「已产生结果的场景」。列表接口的 scenario 可能带 result 但 calculatedAt 为空，
 * 因此不能只看 calculatedAt，需要同时看 result / 状态，避免低估删除范围（PRD 4.4）。
 */
function countCalculatedScenarios(project: ProjectRecord) {
  return project.scenarios.filter(
    (scenario) => Boolean(scenario.result) || scenario.resultSnapshotId != null || scenario.calculatedAt != null || scenario.status === "calculated" || scenario.status === "confirmed",
  ).length;
}

/** 统计带历史快照的场景数——仅在场景明细可读时使用。 */
export function snapshotCoveredScenarioIds(snapshots: Array<{ scenarioId: string }>): Set<string> {
  return new Set(snapshots.map((snapshot) => snapshot.scenarioId));
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ProjectRecord | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "项目加载失败"))
      .finally(() => setLoading(false));
  }, []);

  async function handleConfirmDelete() {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setDeletingId(target.id);
    try {
      await deleteProject(target.id);
      setProjects((current) => current.filter((project) => project.id !== target.id));
      toast.success(`已删除「${target.name}」`, { description: `${target.city} 的测算场景与快照已一并清理，政策资料保留。` });
      setPendingDelete(null);
    } catch (deleteError) {
      const message = deleteError instanceof Error ? deleteError.message : "删除失败，请稍后重试";
      toast.error("删除失败", { description: message });
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="PROJECTS"
        title="项目"
        description="每个城市测算对象都记录范围、场景、模型版本和复核状态。"
        actions={
          <>
            <Button asChild variant="outline">
              <Link href="/settings">
                <IconFileDescription size={16} stroke={1.8} />
                字段与公式
              </Link>
            </Button>
            <Button asChild>
              <Link href="/projects/new">
                <IconFolderPlus size={16} stroke={1.8} />
                新增城市
              </Link>
            </Button>
          </>
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
        <EmptyState title="还没有城市测算对象" description="新增第一个城市后，可以进入参数配置、场景测算和结果复核。" actionLabel="新增城市" actionHref="/projects/new" />
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
                <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
                  <p className="text-xs text-muted-foreground">更新于 {new Date(project.updatedAt).toLocaleString("zh-CN")}</p>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="text-danger hover:bg-danger/10 hover:text-danger"
                      onClick={() => setPendingDelete(project)}
                      aria-label={`删除 ${project.name}`}
                    >
                      <IconTrash size={16} stroke={1.8} />
                      删除
                    </Button>
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/projects/${project.id}`}>打开城市</Link>
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && deletingId === null) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除「{pendingDelete?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              删除后无法恢复。该城市测算对象及其关联数据将被永久移除，此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          {pendingDelete ? (
            <ul className="space-y-1.5 rounded-md border border-border bg-surface-subtle p-3 text-sm">
              <li className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">城市</span>
                <span className="font-medium">
                  {pendingDelete.city}
                  {pendingDelete.district ? ` · ${pendingDelete.district}` : ""}
                </span>
              </li>
              <li className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">测算场景</span>
                <span className="font-medium tabular-nums">{pendingDelete.scenarios.length} 个</span>
              </li>
              <li className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">已算出结果的场景</span>
                <span className="font-medium tabular-nums">{countCalculatedScenarios(pendingDelete)} 个</span>
              </li>
              <li className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">计算快照与字段值历史</span>
                <span className="font-medium">一并删除</span>
              </li>
              <li className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">政策来源与抓取记录</span>
                <span className="font-medium text-success">保留</span>
              </li>
            </ul>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingId !== null}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                void handleConfirmDelete();
              }}
              disabled={deletingId !== null}
            >
              {deletingId !== null ? "删除中…" : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
