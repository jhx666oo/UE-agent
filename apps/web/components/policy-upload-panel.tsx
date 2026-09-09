"use client";

import React, { useState } from "react";
import { IconUpload } from "@tabler/icons-react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import type { PolicyDocument } from "@/lib/policies";

export function PolicyUploadPanel({
  cityId,
  onUpload,
}: Readonly<{
  cityId: string;
  onUpload: (file: File, cityId: string) => Promise<PolicyDocument>;
}>) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setFeedback(null);
    setError(null);
    try {
      const uploaded = await onUpload(file, cityId);
      setFeedback(`已上传 ${uploaded.originalName}，当前状态为已上传，等待本地解析。`);
      event.target.value = "";
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "文件上传失败");
    } finally {
      setBusy(false);
    }
  }

  return <Card><CardHeader><CardTitle>上传政策文件</CardTitle><p className="text-sm text-muted-foreground">支持 Word、Excel、PDF。文件保存在本地项目数据目录，不发送到第三方服务。</p></CardHeader><CardContent className="space-y-3"><label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-surface-subtle px-5 py-8 text-center hover:border-primary" htmlFor="policy-file-upload"><IconUpload size={22} stroke={1.75} /><span className="text-sm font-medium">上传政策文件</span><span className="text-xs text-muted-foreground">.doc · .docx · .xls · .xlsx · .pdf</span><input id="policy-file-upload" aria-label="上传政策文件" className="sr-only" type="file" accept=".doc,.docx,.xls,.xlsx,.pdf,application/pdf" onChange={(event) => void handleChange(event)} disabled={busy} /></label>{busy ? <p className="text-sm text-info">上传中…</p> : null}{feedback ? <p className="rounded-md border border-success/30 bg-success-subtle px-3 py-2 text-sm text-success">{feedback}</p> : null}{error ? <div className="flex items-center justify-between gap-3 rounded-md border border-danger/30 bg-danger-subtle px-3 py-2 text-sm text-danger"><span>{error}</span><Button size="sm" variant="outline" onClick={() => setError(null)}>关闭</Button></div> : null}</CardContent></Card>;
}
