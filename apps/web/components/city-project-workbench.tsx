"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import { IconCheck, IconCopy, IconDeviceFloppy, IconExternalLink, IconPlayerPlay } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { ApiError, calculateScenario, confirmScenario, createScenario, formatFormulaValue, listScenarioSnapshots, updateScenario, type CalculationSnapshot, type ProjectRecord, type ScenarioRecord, type U1ModelSpec, type U1Result } from "@/lib/api";
import { DashboardChart } from "@/components/dashboard-chart";
import { U1ParameterField } from "@/components/u1-parameter-field";
import { U1ResultPanel } from "@/components/u1-result-panel";
import { groupParameters } from "@/components/u1-workbench";

const STATUS_LABELS: Record<ScenarioRecord["status"], { label: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  draft: { label: "草稿", variant: "neutral" },
  stale: { label: "待重算", variant: "warning" },
  calculating: { label: "计算中", variant: "info" },
  calculated: { label: "已计算", variant: "success" },
  confirmed: { label: "已确认", variant: "success" },
  failed: { label: "计算失败", variant: "danger" },
  blocked: { label: "不可用", variant: "danger" },
};

export function CityProjectWorkbench({
  project,
  scenario,
  spec,
  initialSnapshots = [],
}: Readonly<{
  project: ProjectRecord;
  scenario: ScenarioRecord;
  spec: U1ModelSpec;
  initialSnapshots?: CalculationSnapshot[];
}>) {
  const [inputs, setInputs] = useState(scenario.inputs);
  const [status, setStatus] = useState<ScenarioRecord["status"]>(scenario.status);
  const [result, setResult] = useState<U1Result | null>(scenario.result);
  const [snapshots, setSnapshots] = useState(initialSnapshots);
  const [busy, setBusy] = useState<"saving" | "calculating" | "copying" | "confirming" | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const groups = useMemo(() => groupParameters(spec.parameters), [spec.parameters]);
  const statusMeta = STATUS_LABELS[status] ?? STATUS_LABELS.draft;

  function changeInput(parameterId: string, value: number | string | null) {
    setInputs((current) => ({ ...current, [parameterId]: value }));
    if (status === "calculated" || status === "confirmed") setStatus("stale");
    setFeedback(null);
  }

  async function saveDraft() {
    setBusy("saving");
    setFeedback(null);
    setError(null);
    try {
      const saved = await updateScenario(project.id, scenario.id, { inputs });
      setStatus(saved.status);
      setFeedback("已保存");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "参数保存失败");
    } finally {
      setBusy(null);
    }
  }

  async function runCalculation() {
    setBusy("calculating");
    setStatus("calculating");
    setFeedback(null);
    setError(null);
    try {
      await updateScenario(project.id, scenario.id, { inputs });
      const nextResult = await calculateScenario(project.id, scenario.id);
      setResult(nextResult);
      setStatus("calculated");
      setSnapshots(await listScenarioSnapshots(project.id, scenario.id));
      setFeedback("测算完成，已生成新的结果快照");
    } catch (calculationError) {
      if (calculationError instanceof ApiError && calculationError.payload && typeof calculationError.payload === "object" && "issues" in calculationError.payload) {
        setResult(calculationError.payload as U1Result);
      }
      setStatus("failed");
      setError(calculationError instanceof Error ? calculationError.message : "测算失败");
    } finally {
      setBusy(null);
    }
  }

  async function copyCurrentScenario() {
    setBusy("copying");
    setFeedback(null);
    setError(null);
    try {
      await createScenario(project.id, { name: `${scenario.name} 副本`, inputs });
      setFeedback("场景副本已创建");
    } catch (copyError) {
      setError(copyError instanceof Error ? copyError.message : "场景复制失败");
    } finally {
      setBusy(null);
    }
  }

  async function confirmCurrentScenario() {
    setBusy("confirming");
    setFeedback(null);
    setError(null);
    try {
      const confirmed = await confirmScenario(project.id, scenario.id);
      setStatus(confirmed.status);
      setFeedback("结果已确认");
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "结果确认失败");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"><span>{project.city}</span><span>·</span><span>{project.district ?? "未配置区县"}</span><span>·</span><span>{scenario.name}</span><Badge variant={statusMeta.variant}>{statusMeta.label}</Badge></div>
        <Link className="inline-flex items-center gap-2 text-sm text-info hover:underline" href="/"><IconExternalLink size={16} stroke={1.75} />返回总览</Link>
      </div>
      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-4"><div><CardTitle>场景参数</CardTitle><p className="mt-1 text-sm text-muted-foreground">模型版本：{spec.modelVersion} · 公式字段由服务端计算，参考值不会自动覆盖人工输入。</p></div><Badge variant={statusMeta.variant}>{statusMeta.label}</Badge></CardHeader>
        <CardContent className="space-y-6">
          {groups.map((group) => (
            <details key={group.id} open className="group rounded-md border border-border">
              <summary className="cursor-pointer list-none border-b border-border bg-surface-subtle px-4 py-3 text-sm font-semibold">{group.label}<span className="ml-2 text-xs font-normal text-muted-foreground">{group.parameters.length} 项</span></summary>
              <div className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
                {group.parameters.map((definition) => {
                  const formulaValue = result?.parameters?.[definition.id];
                  return <U1ParameterField key={definition.id} definition={definition} value={inputs[definition.id] ?? null} formulaValue={typeof formulaValue === "number" || typeof formulaValue === "string" ? formatFormulaValue({ value: formulaValue, status: "ok", errorCode: null }) : undefined} onChange={(value) => changeInput(definition.id, value)} />;
                })}
              </div>
            </details>
          ))}
          {status === "stale" ? <p className="rounded-md border border-warning/30 bg-warning-subtle px-3 py-2 text-sm text-warning">参数已修改，当前结果仅供历史查看，需重新运行测算。</p> : null}
          {feedback ? <p className="rounded-md border border-success/30 bg-success-subtle px-3 py-2 text-sm text-success">{feedback}</p> : null}
          {error ? <p className="rounded-md border border-danger/30 bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p> : null}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
            <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => void copyCurrentScenario()} disabled={busy !== null}><IconCopy size={16} stroke={1.75} />{busy === "copying" ? "复制中…" : "复制场景"}</Button><Button variant="ghost" onClick={() => void confirmCurrentScenario()} disabled={busy !== null || status !== "calculated"}><IconCheck size={16} stroke={1.75} />{busy === "confirming" ? "确认中…" : "确认结果"}</Button></div>
            <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => void saveDraft()} disabled={busy !== null}><IconDeviceFloppy size={16} stroke={1.75} />{busy === "saving" ? "保存中…" : "保存草稿"}</Button><Button onClick={() => void runCalculation()} disabled={busy !== null}><IconPlayerPlay size={16} stroke={1.75} />{busy === "calculating" ? "测算中…" : "运行测算"}</Button></div>
          </div>
        </CardContent>
      </Card>
      {result ? <U1ResultPanel result={result} /> : null}
      <Card>
        <CardHeader><CardTitle>历史结果快照</CardTitle><p className="text-sm text-muted-foreground">每次测算产生独立快照，历史结果不会被新输入覆盖。</p></CardHeader>
        <CardContent>
          {snapshots.length === 0 ? <p className="text-sm text-muted-foreground">尚无结果快照。</p> : <div className="space-y-2">{snapshots.map((snapshot) => <div key={snapshot.snapshotId} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"><span className="font-mono text-xs">{snapshot.snapshotId}</span><span className="text-muted-foreground">{new Date(snapshot.calculatedAt).toLocaleString("zh-CN")}</span><Badge variant={snapshot.status === "blocked" ? "danger" : "success"}>{snapshot.status === "blocked" ? "阻断" : snapshot.status === "confirmed" ? "已确认" : "已计算"}</Badge></div>)}</div>}
        </CardContent>
      </Card>
      <DashboardChart title="项目月度趋势" type="trend" data={(result?.months ?? []).map((month) => ({ month: month.month, stage: month.stage, revenue: typeof month.totalRevenue.value === "number" ? month.totalRevenue.value : null, netProfit: typeof month.netProfit.value === "number" ? month.netProfit.value : null, cumulativeCashFlow: typeof month.cumulativeCashFlow.value === "number" ? month.cumulativeCashFlow.value : null }))} />
    </div>
  );
}
