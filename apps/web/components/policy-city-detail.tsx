"use client";

import React, { useState } from "react";
import Link from "next/link";
import { IconArrowLeft, IconExternalLink, IconPlayerPlay, IconPlus } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Input } from "@ue-agent/ui/components/input";
import { Label } from "@ue-agent/ui/components/label";
import { PageHeader } from "@/components/page-header";
import {
  formatPolicyDate,
  getCrawlArtifactUrl,
  type CrawlArtifact,
  type DataSource,
  type PolicyCityDetailResponse,
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

export function PolicyCityDetail({
  data,
  sources,
  artifacts,
  onCreateSource,
  onToggleSource,
  onCrawl,
}: Readonly<{
  data: PolicyCityDetailResponse;
  sources: DataSource[];
  artifacts: CrawlArtifact[];
  onCreateSource?: (input: { name: string; url: string }) => Promise<void>;
  onToggleSource?: (source: DataSource) => Promise<void>;
  onCrawl?: (source: DataSource) => Promise<void>;
}>) {
  const [newName, setNewName] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [crawlingSourceId, setCrawlingSourceId] = useState<string | null>(null);

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
          <CardTitle>官网来源</CardTitle>
          <p className="text-sm text-muted-foreground">只抓取公开页面；本机地址、私有网段和非 HTTP 协议会被拒绝。</p>
        </CardHeader>
        <CardContent className="space-y-4">
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
            [...artifacts].reverse().map((artifact) => (
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
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatPolicyDate(artifact.fetchedAt)}
                    {artifact.httpStatus ? ` · HTTP ${artifact.httpStatus}` : ""}
                    {artifact.contentType ? ` · ${artifact.contentType.split(";")[0]}` : ""}
                    {artifact.errorMessage ? ` · ${artifact.errorMessage}` : ""}
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
            ))
          )}
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
