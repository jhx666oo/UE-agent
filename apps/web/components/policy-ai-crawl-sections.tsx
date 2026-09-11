"use client";

import React, { useState } from "react";
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconClock,
  IconExternalLink,
  IconInbox,
  IconRobot,
  IconX,
} from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import {
  candidateStatusLabel,
  difficultyLabel,
  formatPolicyDate,
  formatPolicyValue,
  submissionStatusLabel,
  type CrawlTargetsResponse,
  type ExtractionSubmissionRecord,
  type SourceCandidate,
} from "@/lib/policies";

/** 空态统一收口，避免三处各写一套。 */
function SectionEmpty({ icon: Icon, message }: Readonly<{ icon: typeof IconInbox; message: string }>) {
  return (
    <div className="flex flex-col items-center gap-2 py-8 text-center">
      <Icon className="size-6 text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

function SectionError({ message, onRetry }: Readonly<{ message: string; onRetry?: () => void }>) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-danger/30 bg-danger-subtle px-4 py-3">
      <p className="text-sm text-danger">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      ) : null}
    </div>
  );
}

function SectionLoading() {
  return (
    <div className="space-y-2 py-4" aria-label="正在加载">
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-12 w-full" />
    </div>
  );
}

/**
 * 区块一：调度状态条。
 * 展示 WorkBuddy 上一轮回传的审计结果与当前城市的增量待填进度。
 */
export function PolicyCrawlStatusSection({
  targets,
  submissions,
  loading,
  error,
  onRetry,
}: Readonly<{
  targets: CrawlTargetsResponse | undefined;
  submissions: ExtractionSubmissionRecord[];
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}>) {
  const latest = submissions[0];
  const totalToFill = (targets?.cities ?? []).reduce(
    (sum, city) => sum + city.sources.reduce((acc, source) => acc + source.fieldsToFill.length, 0),
    0,
  );
  const catalogSize = targets?.fieldCatalog.length ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconRobot className="size-4" aria-hidden />
          AI 抓取调度状态
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? <SectionError message={error} onRetry={onRetry} /> : null}
        {loading && !targets ? (
          <SectionLoading />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-md border border-border p-3">
                <p className="text-xs text-muted-foreground">最近一轮回传</p>
                <p className="mt-1 text-sm font-medium">
                  {latest ? formatPolicyDate(latest.submittedAt) : "尚无记录"}
                </p>
                {latest ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {submissionStatusLabel(latest.resultStatus)} · 接收 {latest.acceptedCount} / 拒绝{" "}
                    {latest.rejectedCount}
                  </p>
                ) : null}
              </div>
              <div className="rounded-md border border-border p-3">
                <p className="text-xs text-muted-foreground">本轮待填字段</p>
                <p className="mt-1 text-sm font-medium">
                  {totalToFill} 个 / 共 {catalogSize} 个自动爬虫字段
                </p>
                <p className="mt-1 text-xs text-muted-foreground">已采用的字段不再重复抽取</p>
              </div>
              <div className="rounded-md border border-border p-3">
                <p className="text-xs text-muted-foreground">禁止估算字段</p>
                <p className="mt-1 text-sm font-medium">
                  {(targets?.neverEstimateFields ?? []).join(" / ") || "—"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">官方无公开数据，抽不到即登记未披露</p>
              </div>
            </div>

            {latest && latest.rejectedCount > 0 ? (
              <div className="rounded-md border border-warning/30 bg-warning-subtle p-3">
                <p className="flex items-center gap-2 text-xs font-medium text-warning">
                  <IconAlertTriangle className="size-4" aria-hidden />
                  上一轮被拒 {latest.rejectedCount} 条
                </p>
                <ul className="mt-2 space-y-1">
                  {latest.rejections.slice(0, 4).map((item, index) => (
                    <li key={`${item.fieldId}-${index}`} className="text-xs text-warning">
                      {item.fieldId ?? "未知字段"}：{item.reason}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
              <IconClock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              定时任务每 3 天 08:00 由 WorkBuddy 唤起；回传结果为灰色建议值，需在城市公式页逐条「采用」后才生效。
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * 区块二：AI 候选来源。
 * 联网检索发现的来源先入此池，人工确认后才转为正式 DataSource。
 */
export function PolicySourceCandidateSection({
  candidates,
  loading,
  error,
  onPromote,
  onReject,
  onRetry,
}: Readonly<{
  candidates: SourceCandidate[];
  loading: boolean;
  error: string | null;
  onPromote?: (candidate: SourceCandidate) => Promise<void>;
  onReject?: (candidate: SourceCandidate) => Promise<void>;
  onRetry?: () => void;
}>) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const pending = candidates.filter((candidate) => candidate.status === "candidate");
  const reviewed = candidates.filter((candidate) => candidate.status !== "candidate");

  async function run(candidate: SourceCandidate, action?: (item: SourceCandidate) => Promise<void>) {
    if (!action) return;
    setBusyId(candidate.id);
    try {
      await action(candidate);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconInbox className="size-4" aria-hidden />
          AI 候选来源
          {pending.length > 0 ? <Badge variant="info">{pending.length} 待确认</Badge> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? <SectionError message={error} onRetry={onRetry} /> : null}
        {loading && candidates.length === 0 ? (
          <SectionLoading />
        ) : pending.length === 0 ? (
          <SectionEmpty icon={IconInbox} message="暂无待确认候选来源。AI 检索到新的权威来源后会出现在这里。" />
        ) : (
          <ul className="space-y-2">
            {pending.map((candidate) => (
              <li key={candidate.id} className="rounded-md border border-border p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{candidate.name ?? candidate.url}</p>
                    <a
                      href={candidate.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                    >
                      <span className="truncate">{candidate.domain ?? candidate.url}</span>
                      <IconExternalLink className="size-3 shrink-0" aria-hidden />
                    </a>
                    {candidate.summary ? (
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{candidate.summary}</p>
                    ) : null}
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {candidate.targetFields.map((field) => (
                        <Badge key={field} variant="neutral">
                          {field}
                        </Badge>
                      ))}
                      {candidate.relevance !== null ? (
                        <span className="text-xs text-muted-foreground">
                          相关度 {Math.round(candidate.relevance * 100)}%
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      size="sm"
                      disabled={busyId === candidate.id}
                      onClick={() => void run(candidate, onPromote)}
                    >
                      转为来源
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyId === candidate.id}
                      onClick={() => void run(candidate, onReject)}
                    >
                      <IconX className="size-3.5" aria-hidden />
                      驳回
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {reviewed.length > 0 ? (
          <details className="rounded-md border border-border">
            <summary className="cursor-pointer px-3 py-2 text-xs text-muted-foreground">
              已处理 {reviewed.length} 条
            </summary>
            <ul className="space-y-1 border-t border-border px-3 py-2">
              {reviewed.map((candidate) => (
                <li key={candidate.id} className="flex items-center justify-between gap-3 text-xs">
                  <span className="truncate text-muted-foreground">{candidate.name ?? candidate.url}</span>
                  <Badge variant={candidate.status === "promoted" ? "success" : "neutral"}>
                    {candidateStatusLabel(candidate.status)}
                  </Badge>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * 区块三：字段抽取结果表。
 * 展示上一轮回传逐字段的接收情况，含原文引用，便于人工核对后采用。
 */
export function PolicyExtractionResultSection({
  submissions,
  catalog,
  loading,
  error,
  onRetry,
}: Readonly<{
  submissions: ExtractionSubmissionRecord[];
  catalog: CrawlTargetsResponse["fieldCatalog"];
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}>) {
  const catalogById = new Map(catalog.map((entry) => [entry.id, entry]));
  // 合并最近几轮，按字段去重取最新一条，避免同字段在表中出现多次。
  const byField = new Map<
    string,
    { value: number | string; confidence: number | null; quote: string | null; submittedAt: string; difficulty?: string }
  >();
  for (const submission of submissions) {
    for (const item of submission.payload?.accepted ?? []) {
      if (byField.has(item.fieldId)) continue;
      byField.set(item.fieldId, {
        value: item.value,
        confidence: item.confidence,
        quote: item.quote,
        submittedAt: submission.submittedAt,
        difficulty: catalogById.get(item.fieldId)?.difficulty,
      });
    }
  }
  const rows = [...byField.entries()];
  const totalRounds = submissions.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconCircleCheck className="size-4" aria-hidden />
          字段抽取结果
          {rows.length > 0 ? <Badge variant="success">{rows.length} 项建议值</Badge> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? <SectionError message={error} onRetry={onRetry} /> : null}
        {loading && submissions.length === 0 ? (
          <SectionLoading />
        ) : rows.length === 0 ? (
          <SectionEmpty
            icon={IconCircleCheck}
            message={`暂无 AI 抽取结果${totalRounds ? `（已运行 ${totalRounds} 轮）` : ""}。`}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">AI 抽取的字段建议值，含原文引用与置信度</caption>
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-3 font-medium">字段</th>
                  <th scope="col" className="py-2 pr-3 font-medium">建议值</th>
                  <th scope="col" className="py-2 pr-3 font-medium">置信度</th>
                  <th scope="col" className="py-2 pr-3 font-medium">原文引用</th>
                  <th scope="col" className="py-2 font-medium">回传时间</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([fieldId, row]) => {
                  const entry = catalogById.get(fieldId);
                  return (
                    <tr key={fieldId} className="border-b border-border/60 align-top last:border-0">
                      <td className="py-2 pr-3">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-medium">{fieldId}</span>
                          <span className="text-muted-foreground">{entry?.name ?? "—"}</span>
                          {row.difficulty ? (
                            <Badge variant="neutral">{difficultyLabel(row.difficulty)}</Badge>
                          ) : null}
                        </div>
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {formatPolicyValue(row.value)}
                        {entry?.unit && entry.unit !== "-" ? (
                          <span className="ml-1 text-xs text-muted-foreground">{entry.unit}</span>
                        ) : null}
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {row.confidence === null ? "—" : `${Math.round(row.confidence * 100)}%`}
                      </td>
                      <td className="max-w-md py-2 pr-3 text-xs text-muted-foreground">
                        {row.quote ? `“${row.quote}”` : "—"}
                      </td>
                      <td className="py-2 whitespace-nowrap text-xs text-muted-foreground">
                        {formatPolicyDate(row.submittedAt)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          建议值不会自动写入参数，需在城市公式页逐条「采用」。数值超出预期区间的条目已在服务端标记警告。
        </p>
      </CardContent>
    </Card>
  );
}
