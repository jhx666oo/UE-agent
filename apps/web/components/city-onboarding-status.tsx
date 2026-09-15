"use client";

import { useEffect, useMemo, useState } from "react";
import React from "react";
import { IconAlertTriangle, IconCircleCheck, IconLoader2, IconRefresh } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { getCityOnboarding, retryCityOnboarding, type CityOnboardingJob } from "@/lib/api";

const ACTIVE_STATUSES = new Set<CityOnboardingJob["status"]>([
  "queued", "discovering", "sources_ready", "crawling", "extracting",
]);

const STATUS_META: Record<CityOnboardingJob["status"], { label: string; description: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  queued: { label: "准备开始", description: "正在排队启动来源发现。", variant: "neutral" },
  discovering: { label: "寻找来源", description: "正在根据城市名寻找政策和数据来源。", variant: "info" },
  sources_ready: { label: "来源已发现", description: "来源已整理，准备抓取公开原文。", variant: "info" },
  crawling: { label: "抓取中", description: "正在抓取官网原文并保存本地记录。", variant: "info" },
  extracting: { label: "解析中", description: "正在把原文解析为测算参数建议值。", variant: "info" },
  completed: { label: "已完成", description: "来源、原文和灰色建议值已同步。", variant: "success" },
  partial_failed: { label: "部分完成", description: "部分来源暂时失败，仍可继续填写和运行测算。", variant: "warning" },
  failed: { label: "需要重试", description: "自动入场没有完成，仍可继续填写和运行测算。", variant: "danger" },
};

export function CityOnboardingStatus({
  projectId,
  initialJob,
  poll = true,
  onSettled,
}: Readonly<{
  projectId: string;
  initialJob: CityOnboardingJob;
  poll?: boolean;
  onSettled?: () => void;
}>) {
  const [job, setJob] = useState(initialJob);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const meta = STATUS_META[job.status];
  const isActive = ACTIVE_STATUSES.has(job.status);

  useEffect(() => {
    if (!poll || !isActive) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const latest = await getCityOnboarding(projectId);
        if (!cancelled) {
          setJob(latest);
          setError(null);
          if (!ACTIVE_STATUSES.has(latest.status)) onSettled?.();
        }
      } catch (requestError) {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "自动入场状态读取失败");
      }
    };
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [isActive, onSettled, poll, projectId]);

  const summary = useMemo(() => [
    `已发现 ${job.discoveredCount} 个来源`,
    `正式来源 ${job.officialSourceCount} 个`,
    `候选来源 ${job.candidateCount} 个`,
    `已抓取 ${job.crawledCount} 条`,
    `建议值 ${job.suggestionCount} 个`,
  ], [job]);

  async function handleRetry() {
    setRetrying(true);
    setError(null);
    try {
      setJob(await retryCityOnboarding(projectId));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "重新启动自动入场失败");
    } finally {
      setRetrying(false);
    }
  }

  return (
    <Card className={job.status === "partial_failed" || job.status === "failed" ? "border-warning/40" : "border-info/20"}>
      <CardHeader className="flex-row items-start justify-between gap-4 pb-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-full bg-info-subtle p-2 text-info">
            {job.status === "completed" ? <IconCircleCheck size={17} stroke={1.8} /> : job.status === "partial_failed" || job.status === "failed" ? <IconAlertTriangle size={17} stroke={1.8} /> : <IconLoader2 className="animate-spin" size={17} stroke={1.8} />}
          </div>
          <div>
            <CardTitle className="text-base">{job.status === "crawling" ? `正在抓取${job.cityName}` : `${job.cityName}自动入场`}</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">{meta.description}</p>
          </div>
        </div>
        <Badge variant={meta.variant}>{meta.label}</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {summary.map((item) => <span key={item}>{item}</span>)}
        </div>
        {job.errors.length > 0 ? (
          <div className="space-y-1 rounded-md border border-warning/25 bg-warning-subtle px-3 py-2 text-xs text-warning">
            {job.errors.slice(0, 3).map((item) => <p key={item}>{item}</p>)}
          </div>
        ) : null}
        {error ? <p className="text-xs text-danger">{error}</p> : null}
        {job.status === "partial_failed" || job.status === "failed" ? (
          <Button type="button" variant="outline" size="sm" onClick={() => void handleRetry()} disabled={retrying}>
            <IconRefresh size={14} stroke={1.8} />{retrying ? "重试中…" : "重新尝试"}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
