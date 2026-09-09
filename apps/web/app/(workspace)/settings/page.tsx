"use client";

import { useEffect, useState } from "react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { PageHeader } from "@/components/page-header";
import { getModelSpec, type U1ModelSpec } from "@/lib/api";

export default function SettingsPage() {
  const [spec, setSpec] = useState<U1ModelSpec | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    setError(null);
    return getModelSpec()
      .then((nextSpec) => { setSpec(nextSpec); return nextSpec; })
      .catch((requestError) => { setError(requestError instanceof Error ? requestError.message : "参数定义加载失败"); throw requestError; })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let active = true;
    getModelSpec()
      .then((nextSpec) => { if (active) setSpec(nextSpec); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "参数定义加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  if (loading && !spec) return <div className="space-y-4" aria-label="正在加载参数设置"><Skeleton className="h-24 w-full" /><Skeleton className="h-56 w-full" /></div>;
  if (error && !spec) return <div className="space-y-5"><PageHeader eyebrow="SETTINGS" title="参数设置加载失败" description={error} /><Card className="border-danger/30"><CardContent className="flex items-center justify-between gap-4 p-5"><p className="text-sm text-danger">请确认 API 服务已启动。</p><Button variant="outline" onClick={() => void reload().catch(() => undefined)}>重试</Button></CardContent></Card></div>;
  if (!spec) return null;
  return <div className="space-y-6"><PageHeader eyebrow="SETTINGS" title="参数设置" description="查看当前确定性模型版本、参数定义和已知问题。参数值在城市测算场景中维护。" actions={<Button variant="outline" onClick={() => void reload().catch(() => undefined)} disabled={loading}>刷新定义</Button>} /><div className="grid gap-4 sm:grid-cols-3"><Card><CardContent className="p-5"><p className="text-xs text-muted-foreground">模型版本</p><p className="mt-2 font-mono text-sm">{spec.modelVersion}</p></CardContent></Card><Card><CardContent className="p-5"><p className="text-xs text-muted-foreground">参数数量</p><p className="mt-2 text-2xl font-semibold tabular-nums">{spec.parameters.length}</p></CardContent></Card><Card><CardContent className="p-5"><p className="text-xs text-muted-foreground">待确认问题</p><p className="mt-2 text-2xl font-semibold tabular-nums">{spec.issues.length}</p></CardContent></Card></div><Card><CardHeader><CardTitle>参数定义</CardTitle><p className="text-sm text-muted-foreground">这里只读展示字段定义；城市测算页面负责输入、保存和重算。</p></CardHeader><CardContent><div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead className="border-b border-border text-xs text-muted-foreground"><tr><th className="px-3 py-2 font-medium">字段</th><th className="px-3 py-2 font-medium">分组</th><th className="px-3 py-2 font-medium">单位</th><th className="px-3 py-2 font-medium">输入方式</th><th className="px-3 py-2 font-medium">状态</th></tr></thead><tbody className="divide-y divide-border">{spec.parameters.map((parameter) => <tr key={parameter.id}><td className="px-3 py-3"><p className="font-medium">{parameter.name}</p><code className="text-xs text-muted-foreground">{parameter.id} · {parameter.excelCell}</code></td><td className="px-3 py-3 text-muted-foreground">{parameter.stage}</td><td className="px-3 py-3 text-muted-foreground">{parameter.unit || "—"}</td><td className="px-3 py-3 text-muted-foreground">{parameter.inputKind === "formula" ? "公式" : parameter.inputKind === "reference_or_manual" ? "参考/手工" : "手工"}</td><td className="px-3 py-3"><Badge variant={parameter.parityStatus === "parity" ? "success" : "warning"}>{parameter.parityStatus === "parity" ? "已对齐" : "待确认"}</Badge></td></tr>)}</tbody></table></div></CardContent></Card></div>;
}
