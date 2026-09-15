"use client";

import React, { useEffect, useState } from "react";
import {
  IconAlertTriangle,
  IconCheck,
  IconClipboard,
  IconLoader2,
  IconRefresh,
  IconRobot,
} from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import {
  createPolicyResearchRun,
  getPolicyResearchRun,
  retryPolicyResearchRun,
  type PolicyResearchRun,
  type PolicyResearchRunStatus,
} from "@/lib/policies";

const ACTIVE_STATUSES = new Set<PolicyResearchRunStatus>([
  "queued",
  "researching",
  "fetching",
  "extracting",
]);

const STATUS_META: Record<PolicyResearchRunStatus, { label: string; description: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  queued: { label: "等待 WorkBuddy 执行", description: "任务已排队。请把任务提示交给 WorkBuddy 执行实时检索。", variant: "neutral" },
  researching: { label: "WorkBuddy 检索中", description: "正在根据城市和当前年份寻找权威政策来源。", variant: "info" },
  fetching: { label: "抓取原文中", description: "正在保存政策原文和版本变化记录。", variant: "info" },
  extracting: { label: "解析字段中", description: "正在把原文解析为可复核的灰色建议值。", variant: "info" },
  awaiting_review: { label: "待确认", description: "资料已回传，建议值仍需在城市测算页人工采用。", variant: "warning" },
  completed: { label: "已完成", description: "本轮检索已结束，新增资料和建议值已同步。", variant: "success" },
  partial_failed: { label: "部分完成", description: "部分来源或字段未完成，可重新排队。", variant: "warning" },
  failed: { label: "需要重试", description: "本轮检索没有完成，可重新排队。", variant: "danger" },
};

function RunIcon({ status }: Readonly<{ status: PolicyResearchRunStatus }>) {
  if (status === "completed" || status === "awaiting_review") return <IconCheck size={17} stroke={1.8} />;
  if (status === "failed" || status === "partial_failed") return <IconAlertTriangle size={17} stroke={1.8} />;
  return <IconLoader2 className={ACTIVE_STATUSES.has(status) ? "animate-spin" : ""} size={17} stroke={1.8} />;
}

export function PolicyResearchRunCard({
  cityId,
  cityName,
  initialRun = null,
  onSettled,
}: Readonly<{
  cityId: string;
  cityName: string;
  initialRun?: PolicyResearchRun | null;
  onSettled?: () => void;
}>) {
  const [run, setRun] = useState<PolicyResearchRun | null>(initialRun);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const status = run?.status ?? null;
  const meta = status ? STATUS_META[status] : null;
  const runId = run?.id ?? null;
  const runStatus = run?.status ?? null;

  useEffect(() => {
    if (!runId || !runStatus || !ACTIVE_STATUSES.has(runStatus)) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const latest = await getPolicyResearchRun(runId);
        if (cancelled) return;
        setRun(latest);
        setError(null);
        if (!ACTIVE_STATUSES.has(latest.status)) onSettled?.();
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : "实时政策任务状态读取失败");
        }
      }
    };
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [onSettled, runId, runStatus]);

  async function startResearch() {
    setBusy(true);
    setError(null);
    try {
      setRun(await createPolicyResearchRun({ cityId, trigger: "ui", scope: "all" }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "实时政策任务创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function retryResearch() {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      setRun(await retryPolicyResearchRun(run.id));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "实时政策任务重新排队失败");
    } finally {
      setBusy(false);
    }
  }

  async function copyPrompt() {
    if (!run?.taskPrompt || !navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(run.taskPrompt);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("任务提示复制失败，请手动复制下方文字");
    }
  }

  return (
    <Card className={status === "failed" || status === "partial_failed" ? "border-warning/40" : "border-info/20"}>
      <CardHeader className="flex-row items-start justify-between gap-4 pb-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-full bg-info-subtle p-2 text-info">
            {status ? <RunIcon status={status} /> : <IconRobot size={17} stroke={1.8} />}
          </div>
          <div>
            <CardTitle className="text-base">AI 实时更新政策</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {meta?.description ?? `按${cityName}当前政策和数据公开情况，发起一轮可追溯的实时检索。`}
            </p>
          </div>
        </div>
        {meta ? <Badge variant={meta.variant}>{meta.label}</Badge> : null}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>目标城市：{cityName}</span>
          {run ? <span>检索主题：{run.queryCount} 个</span> : <span>范围：政策、人口、空间</span>}
          {run && run.suggestionCount > 0 ? <span>建议值：{run.suggestionCount} 个</span> : null}
          {run && run.changedSourceCount > 0 ? <span>新版本：{run.changedSourceCount} 条</span> : null}
        </div>

        {run?.status === "queued" && run.taskPrompt ? (
          <div className="space-y-2 rounded-md border border-border bg-surface-subtle p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-medium text-foreground">任务已排队</p>
              <Button type="button" variant="outline" size="sm" onClick={() => void copyPrompt()}>
                <IconClipboard size={14} stroke={1.8} />{copied ? "已复制" : "复制任务提示"}
              </Button>
            </div>
            <p className="whitespace-pre-wrap text-xs leading-5 text-muted-foreground">{run.taskPrompt}</p>
            <p className="text-xs text-muted-foreground">WorkBuddy 完成后会通过回传接口写入来源、原文和灰色建议值。</p>
          </div>
        ) : null}

        {run && (run.status === "failed" || run.status === "partial_failed") && run.errors.length > 0 ? (
          <div className="space-y-1 rounded-md border border-warning/25 bg-warning-subtle px-3 py-2 text-xs text-warning">
            {run.errors.slice(0, 3).map((item) => <p key={item}>{item}</p>)}
          </div>
        ) : null}
        {error ? <p className="text-xs text-danger">{error}</p> : null}

        {!run || run.status === "completed" ? (
          <Button type="button" onClick={() => void startResearch()} disabled={busy}>
            <IconRobot size={15} stroke={1.8} />{busy ? "创建中…" : run ? "再次更新政策" : "AI 实时更新政策"}
          </Button>
        ) : run.status === "failed" || run.status === "partial_failed" ? (
          <Button type="button" variant="outline" onClick={() => void retryResearch()} disabled={busy}>
            <IconRefresh size={15} stroke={1.8} />{busy ? "重新排队中…" : "重新排队"}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
