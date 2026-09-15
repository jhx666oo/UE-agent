"use client";

import React, { useState } from "react";
import Link from "next/link";
import { IconArrowLeft, IconBolt, IconDownload, IconExternalLink, IconPlayerPlay, IconPlus } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Input } from "@ue-agent/ui/components/input";
import { Label } from "@ue-agent/ui/components/label";
import { PageHeader } from "@/components/page-header";
import {
  formatPolicyDate,
  getCrawlArtifactUrl,
  getPolicyExportUrl,
  type CrawlAllSummary,
  type CrawlArtifact,
  type DataSource,
  type PolicyCityDetailResponse,
  type SourceFreshnessReport,
} from "@/lib/policies";

const SOURCE_STATUS: Record<DataSource["status"], { label: string; variant: "success" | "warning" | "danger" }> = {
  active: { label: "正常", variant: "success" },
  paused: { label: "已停用", variant: "warning" },
  error: { label: "最近失败", variant: "danger" },
};

const CHANGE_LABELS: Record<string, string> = {
  first_fetch: "首次抓取",
  unchanged: "无变化",
  new_version: "发现新版本",
};

/** 抓取历史默认只展示最新这么多条 —— 来源一多，几十条历史会把页面撑得很长。 */
const HISTORY_PREVIEW_LIMIT = 20;

export function PolicyCityDetail({
  data,
  sources,
  artifacts,
  onCreateSource,
  onToggleSource,
  onCrawl,
  onCrawlAll,
  freshness,
}: Readonly<{
  data: PolicyCityDetailResponse;
  sources: DataSource[];
  artifacts: CrawlArtifact[];
  onCreateSource?: (input: { name: string; url: string }) => Promise<void>;
  onToggleSource?: (source: DataSource) => Promise<void>;
  onCrawl?: (source: DataSource) => Promise<void>;
  onCrawlAll?: () => Promise<CrawlAllSummary | void>;
  freshness?: SourceFreshnessReport;
}>) {
  const [newName, setNewName] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [crawlingSourceId, setCrawlingSourceId] = useState<string | null>(null);
  const [crawlingAll, setCrawlingAll] = useState(false);
  const [crawlAllSummary, setCrawlAllSummary] = useState<CrawlAllSummary | null>(null);
  const [historyExpanded, setHistoryExpanded] = useState(false);

  async function crawlAll() {
    if (!onCrawlAll) return;
    setCrawlingAll(true);
    setCrawlAllSummary(null);
    try {
      const summary = await onCrawlAll();
      if (summary) setCrawlAllSummary(summary);
    } finally {
      setCrawlingAll(false);
    }
  }

  /** 「全部抓取」只覆盖启用中的来源 —— 停用的会被后端跳过。 */
  const activeSourceCount = sources.filter((source) => source.status !== "paused").length;

  const freshnessBySource = new Map(
    (freshness?.sources ?? []).map((item) => [item.sourceId, item] as const),
  );

  /** 抓取历史按时间倒序（最新在前），默认只渲染最新 30 条。 */
  const orderedArtifacts = [...artifacts].reverse();
  const visibleArtifacts = historyExpanded
    ? orderedArtifacts
    : orderedArtifacts.slice(0, HISTORY_PREVIEW_LIMIT);
  const hiddenArtifactCount = orderedArtifacts.length - visibleArtifacts.length;

  /** 疑似过期 / 长期未变的来源在列表里挂一个警示徽标。 */
  function freshnessBadge(sourceId: string) {
    const item = freshnessBySource.get(sourceId);
    if (!item || item.level === "ok" || item.level === "unknown") return null;
    return (
      <Badge variant="warning">{item.level === "stale" ? "疑似过期" : "长期未变"}</Badge>
    );
  }

  async function submitSource() {
    if (!onCreateSource) return;
    setCreating(true);
    setCreateError(null);
    try {
      await onCreateSource({ name: newName.trim(), url: newUrl.trim() });
      setNewName("");
      setNewUrl("");
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "来源创建失败");
    } finally {
      setCreating(false);
    }
  }

  async function crawl(source: DataSource) {
    if (!onCrawl) return;
    setCrawlingSourceId(source.id);
    try {
      await onCrawl(source);
    } finally {
      setCrawlingSourceId(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="POLICY / CITY"
        title={`${data.cityName}政策资料`}
        description="配置公开官网来源并一键抓取；抓取原文只生成灰色建议值，不会自动覆盖城市参数。"
        actions={
          <Button asChild variant="outline">
            <Link href="/policies"><IconArrowLeft size={16} stroke={1.75} />返回政策总览</Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1.5">
              <CardTitle>官网来源</CardTitle>
              <p className="text-sm text-muted-foreground">只抓取公开页面；本机地址、私有网段和非 HTTP 协议会被拒绝。</p>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <Button asChild size="sm" variant="outline">
                <a href={getPolicyExportUrl({ cityId: data.cityId, dataset: "fields" })}>
                  <IconDownload size={15} stroke={1.75} />导出建议值 CSV
                </a>
              </Button>
              <Button asChild size="sm" variant="outline">
                <a href={getPolicyExportUrl({ cityId: data.cityId, dataset: "artifacts" })}>
                  <IconDownload size={15} stroke={1.75} />导出抓取记录 CSV
                </a>
              </Button>
              <Button asChild size="sm" variant="outline">
                <a href={getPolicyExportUrl({ cityId: data.cityId, format: "json" })}>
                  <IconDownload size={15} stroke={1.75} />导出完整 JSON
                </a>
              </Button>
              <Button
                size="sm"
                onClick={() => void crawlAll()}
                disabled={!onCrawlAll || crawlingAll || activeSourceCount === 0}
              >
                <IconBolt size={15} stroke={1.75} />
                {crawlingAll ? `抓取中…（${activeSourceCount} 个）` : `全部抓取（${activeSourceCount}）`}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {crawlAllSummary ? (
            <div className="space-y-2 rounded-md border border-border bg-surface-subtle p-3">
              <p className="text-sm">
                全部抓取完成：成功 <span className="font-medium">{crawlAllSummary.succeeded}</span> · 失败{" "}
                <span className="font-medium">{crawlAllSummary.failed}</span>
                {crawlAllSummary.skipped > 0 ? ` · 跳过 ${crawlAllSummary.skipped}` : ""} · 未变{" "}
                <span className="font-medium">{crawlAllSummary.unchanged}</span> · 有更新{" "}
                <span className="font-medium">{crawlAllSummary.changed}</span>
                {(crawlAllSummary.browserRequired ?? 0) > 0 ? (
                  <>
                    {" · 需浏览器兜底 "}
                    <span className="font-medium">{crawlAllSummary.browserRequired}</span>
                  </>
                ) : null}
              </p>
              <p className="text-xs text-muted-foreground">
                共 {crawlAllSummary.total} 个来源，{formatPolicyDate(crawlAllSummary.crawledAt)}。
                「有更新」的正文才值得再跑一轮 AI 抽取；「未变」的会直接跳过。
              </p>
              {crawlAllSummary.results.some((item) => item.status !== "success") ? (
                <ul className="space-y-1">
                  {crawlAllSummary.results
                    .filter((item) => item.status !== "success")
                    .slice(0, 6)
                    .map((item) => (
                      <li key={item.sourceId} className="text-xs text-warning">
                        {item.name ?? item.sourceId}：
                        {item.status === "browser_required" ? "需 WorkBuddy 浏览器兜底" : item.message ?? item.status}
                      </li>
                    ))}
                </ul>
              ) : null}
            </div>
          ) : null}
          {freshness ? (
            freshness.counts.stale > 0 || freshness.counts.aging > 0 ? (
              <div className="space-y-2 rounded-md border border-warning/40 bg-warning-subtle p-3">
                <p className="text-sm font-medium text-warning">
                  来源新鲜度体检：
                  {freshness.counts.stale > 0 ? `${freshness.counts.stale} 个疑似过期` : ""}
                  {freshness.counts.stale > 0 && freshness.counts.aging > 0 ? " · " : ""}
                  {freshness.counts.aging > 0 ? `${freshness.counts.aging} 个长期未变` : ""}
                </p>
                <ul className="space-y-1">
                  {freshness.sources
                    .filter((item) => item.level === "stale" || item.level === "aging")
                    .slice(0, 6)
                    .map((item) => (
                      <li key={item.sourceId} className="text-xs text-warning">
                        {item.name ?? item.sourceId}：{item.reason}
                      </li>
                    ))}
                </ul>
                <p className="text-xs text-muted-foreground">
                  年度文档每年换新链接，旧来源不会「变」，只会安静地停在旧版本 ——
                  所以要按「超过 {freshness.staleDays} 天无内容变更 + 名称带年份」来告警。
                </p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                来源新鲜度体检通过：{freshness.counts.total} 个来源均未超过 {freshness.staleDays}{" "}
                天无内容变更。
              </p>
            )
          ) : null}
          {sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">尚未配置官网来源。填写名称和链接后点击新增来源。</p>
          ) : (
            sources.map((source) => {
              const status = SOURCE_STATUS[source.status];
              return (
                <div key={source.id} className="space-y-2 rounded-md border border-border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-sm font-medium">{source.name}</p>
                        <Badge variant={status.variant}>{status.label}</Badge>
                        {source.fallbackAction === "browser_search" ? (
                          <Badge variant="warning">需浏览器通道</Badge>
                        ) : null}
                        {freshnessBadge(source.id)}
                      </div>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {source.url ?? "未配置链接"}
                        {source.lastFetchedAt ? ` · 最近抓取 ${formatPolicyDate(source.lastFetchedAt)}` : " · 从未抓取"}
                        {source.lastHttpStatus ? ` · HTTP ${source.lastHttpStatus}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void onToggleSource?.(source)}
                        disabled={!onToggleSource}
                      >
                        {source.status === "paused" ? "启用" : "停用"}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => void crawl(source)}
                        disabled={!onCrawl || source.status === "paused" || crawlingSourceId === source.id}
                      >
                        <IconPlayerPlay size={15} stroke={1.75} />
                        {crawlingSourceId === source.id ? "抓取中…" : "立即抓取"}
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })
          )}

          <div className="grid gap-3 rounded-md border border-dashed border-border bg-surface-subtle p-4 md:grid-cols-[1fr_2fr_auto] md:items-end">
            <div className="space-y-1.5">
              <Label htmlFor="new-source-name">来源名称</Label>
              <Input id="new-source-name" value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="例如：长沙医保局" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new-source-url">官网链接</Label>
              <Input id="new-source-url" value={newUrl} onChange={(event) => setNewUrl(event.target.value)} placeholder="https://…" />
            </div>
            <Button onClick={() => void submitSource()} disabled={creating || !newName.trim() || !newUrl.trim() || !onCreateSource}>
              <IconPlus size={16} stroke={1.75} />{creating ? "新增中…" : "新增来源"}
            </Button>
            {createError ? <p className="text-xs text-danger md:col-span-3">{createError}</p> : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>抓取历史</CardTitle>
          <p className="text-sm text-muted-foreground">每次抓取保存原文、状态码、内容指纹；失败记录保留，不删除上一次成功结果。</p>
        </CardHeader>
        <CardContent className="space-y-3">
          {artifacts.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无抓取记录。配置来源后点击「立即抓取」。</p>
          ) : (
            <div className="max-h-[520px] space-y-3 overflow-y-auto rounded-xl border border-border p-3">
              {visibleArtifacts.map((artifact) => (
              <div key={artifact.artifactId} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium">{artifact.title ?? "（无标题）"}</p>
                    <Badge variant={artifact.status === "success" ? "success" : "danger"}>
                      {artifact.status === "success" ? "成功" : "失败"}
                    </Badge>
                    {artifact.changeStatus ? (
                      <Badge variant={artifact.changeStatus === "new_version" ? "warning" : "neutral"}>
                        {CHANGE_LABELS[artifact.changeStatus] ?? artifact.changeStatus}
                      </Badge>
                    ) : null}
                    {artifact.fetchMode === "workbuddy_browser" ? (
                      <Badge variant="info">WorkBuddy 浏览器</Badge>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatPolicyDate(artifact.fetchedAt)}
                    {artifact.httpStatus ? ` · HTTP ${artifact.httpStatus}` : ""}
                    {artifact.contentType ? ` · ${artifact.contentType.split(";")[0]}` : ""}
                    {artifact.errorMessage ? ` · ${artifact.errorMessage}` : ""}
                    {artifact.fallbackReason ? ` · 兜底原因：${artifact.fallbackReason}` : ""}
                  </p>
                  {artifact.suggestions && artifact.suggestions.length > 0 ? (
                    <p className="mt-1 text-xs text-info">
                      生成建议值：{artifact.suggestions.map((s) => `${s.fieldId}=${s.value}`).join("，")}
                    </p>
                  ) : null}
                </div>
                {artifact.storedPath ? (
                  <a
                    className="inline-flex items-center gap-1 text-sm text-info hover:underline"
                    href={getCrawlArtifactUrl(artifact.artifactId)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <IconExternalLink size={15} stroke={1.75} />查看原文
                  </a>
                ) : null}
              </div>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              共 {orderedArtifacts.length} 条记录
              {hiddenArtifactCount > 0
                ? `，当前只显示最新 ${HISTORY_PREVIEW_LIMIT} 条`
                : "，已全部显示"}
              ，可在框内独立滚动
            </p>
            {hiddenArtifactCount > 0 || historyExpanded ? (
              <Button size="sm" variant="outline" onClick={() => setHistoryExpanded((prev) => !prev)}>
                {historyExpanded ? "只看最新" : `展开全部（还有 ${hiddenArtifactCount} 条）`}
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>关联城市</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.projects.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无关联城市测算。</p>
          ) : (
            data.projects.map((project) => (
              <div key={project.id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
                <span className="text-sm">{project.name}</span>
                <Button asChild size="sm" variant="ghost">
                  <Link href={`/projects/${project.id}`}>进入城市测算<IconExternalLink size={15} stroke={1.75} /></Link>
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <p className="rounded-md border border-info/30 bg-info-subtle px-3 py-2 text-sm text-info">
        建议值以灰色提示展示在城市测算页，点击「采用建议值」后才写入参数；手工填写会标记为已覆盖并保留建议值来源。
      </p>
    </div>
  );
}
