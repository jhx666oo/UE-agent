"use client";

import React, { useState } from "react";
import Link from "next/link";
import { IconArrowLeft, IconCheck, IconExternalLink, IconUpload, IconX } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { PageHeader } from "@/components/page-header";
import { formatPolicyDate, formatPolicyValue, getPolicyDocumentContentUrl, type PolicyCandidateInput, type PolicyCityDetailResponse, type PolicyDocumentStatus, type PolicyFactStatus } from "@/lib/policies";

const DOCUMENT_STATUS: Record<PolicyDocumentStatus, { label: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  uploaded: { label: "已上传", variant: "info" },
  parsing: { label: "解析中", variant: "info" },
  review_pending: { label: "待审核", variant: "warning" },
  approved: { label: "已发布", variant: "success" },
  rejected: { label: "已驳回", variant: "danger" },
};

const FACT_STATUS: Record<PolicyFactStatus, { label: string; variant: "neutral" | "success" | "warning" | "danger" }> = {
  candidate: { label: "候选值", variant: "warning" },
  approved: { label: "已确认", variant: "success" },
  rejected: { label: "已驳回", variant: "danger" },
};

export function PolicyCityDetail({
  data,
  onParse,
  onReview,
}: Readonly<{
  data: PolicyCityDetailResponse;
  onParse?: (documentId: string, candidates: PolicyCandidateInput[]) => void | Promise<void>;
  onReview?: (documentId: string, factId: string, decision: "approve" | "reject") => void | Promise<void>;
}>) {
  const [candidateDrafts, setCandidateDrafts] = useState<Record<string, string>>({});
  const [parsingDocumentId, setParsingDocumentId] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  async function handleParse(documentId: string) {
    setParseError(null);
    try {
      const raw = candidateDrafts[documentId]?.trim() ?? "";
      const candidates = raw ? JSON.parse(raw) as PolicyCandidateInput[] : [];
      if (!Array.isArray(candidates)) throw new Error("候选值必须是 JSON 数组");
      setParsingDocumentId(documentId);
      await onParse?.(documentId, candidates);
      setCandidateDrafts((current) => ({ ...current, [documentId]: "" }));
    } catch (error) {
      setParseError(error instanceof Error ? error.message : "候选值解析失败");
    } finally {
      setParsingDocumentId(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="POLICY / CITY" title={`${data.cityName}政策资料`} description="查看原文、结构化字段、来源与版本。候选字段只作为审核参考，不会自动覆盖项目参数。" actions={<Button asChild variant="outline"><Link href="/policies"><IconArrowLeft size={16} stroke={1.75} />返回政策总览</Link></Button>} />
      <Card><CardHeader><CardTitle>政策文件与来源</CardTitle><p className="text-sm text-muted-foreground">文件指纹和历史版本用于追溯；状态变化不会删除原始文件。</p></CardHeader><CardContent className="space-y-3">{data.documents.length === 0 ? <p className="text-sm text-muted-foreground">尚未上传政策文件。</p> : data.documents.map((document) => { const status = DOCUMENT_STATUS[document.status]; return <div key={document.id} className="space-y-3 rounded-md border border-border p-3"><div className="flex flex-wrap items-center justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-medium">{document.originalName}</p><p className="mt-1 text-xs text-muted-foreground">来源：{document.source} · 上传于 {formatPolicyDate(document.uploadedAt)} · SHA-256 {document.sha256.slice(0, 12)}…</p></div><div className="flex items-center gap-2"><Badge variant={status.variant}>{status.label}</Badge><a className="text-sm text-info hover:underline" href={getPolicyDocumentContentUrl(document.id)} target="_blank" rel="noreferrer">打开原文</a><span className="text-xs text-muted-foreground">{document.mimeType}</span></div></div><div className="rounded-md bg-surface-subtle p-3"><label className="grid gap-1.5 text-xs font-medium" htmlFor={`policy-candidates-${document.id}`}>候选字段 JSON<span className="font-normal text-muted-foreground">留空也可提交解析；解析结果只会进入待审核，不会自动发布。</span><textarea id={`policy-candidates-${document.id}`} className="min-h-20 rounded-md border border-border bg-background px-3 py-2 font-mono text-xs font-normal" value={candidateDrafts[document.id] ?? ""} onChange={(event) => setCandidateDrafts((current) => ({ ...current, [document.id]: event.target.value }))} placeholder={'[{"fieldId":"P2","value":0.85,"unit":"比例","source":"第4条"}]'} /></label><div className="mt-2 flex items-center justify-between gap-3"><Button size="sm" variant="outline" onClick={() => void handleParse(document.id)} disabled={parsingDocumentId === document.id || !onParse}><IconUpload size={15} stroke={1.75} />{parsingDocumentId === document.id ? "解析中…" : "解析候选字段"}</Button>{parseError && parsingDocumentId === null ? <span className="text-xs text-danger">{parseError}</span> : null}</div></div></div>; })}</CardContent></Card>
      <Card><CardHeader><CardTitle>结构化政策字段</CardTitle><p className="text-sm text-muted-foreground">只有“已确认”的字段可以进入政策指标或被项目作为参考值。</p></CardHeader><CardContent className="space-y-3">{data.facts.length === 0 ? <p className="text-sm text-muted-foreground">暂无候选或已确认字段。</p> : data.facts.map((fact) => { const status = FACT_STATUS[fact.status]; return <div key={fact.id} className="flex flex-wrap items-center justify-between gap-4 rounded-md border border-border p-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><code className="text-sm text-foreground">{fact.fieldId}</code><Badge variant={status.variant}>{status.label}</Badge></div><p className="mt-1 text-sm text-foreground">{formatPolicyValue(fact.value)} {fact.unit ?? ""}</p><p className="mt-1 text-xs text-muted-foreground">来源：{fact.source ?? "—"} · 置信度：{fact.confidence === null ? "—" : `${Math.round(fact.confidence * 100)}%`} · 生效：{fact.effectiveDate ?? "—"}</p></div>{fact.status === "candidate" ? <div className="flex shrink-0 gap-2"><Button size="sm" onClick={() => void onReview?.(fact.documentId, fact.id, "approve")}><IconCheck size={15} stroke={1.75} />通过</Button><Button size="sm" variant="outline" onClick={() => void onReview?.(fact.documentId, fact.id, "reject")}><IconX size={15} stroke={1.75} />驳回</Button></div> : null}</div>; })}</CardContent></Card>
      <Card><CardHeader><CardTitle>关联项目</CardTitle></CardHeader><CardContent className="space-y-2">{data.projects.length === 0 ? <p className="text-sm text-muted-foreground">暂无关联城市项目。</p> : data.projects.map((project) => <div key={project.id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2"><span className="text-sm">{project.name}</span><Button asChild size="sm" variant="ghost"><Link href={`/projects/${project.id}`}>进入项目<IconExternalLink size={15} stroke={1.75} /></Link></Button></div>)}</CardContent></Card>
      <p className="rounded-md border border-info/30 bg-info-subtle px-3 py-2 text-sm text-info">政策候选值不会自动覆盖项目参数；请在城市项目页面人工确认参考值后再保存和重算。</p>
    </div>
  );
}
