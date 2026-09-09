"use client";

import React, { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { IconCheck, IconCopy, IconDeviceFloppy, IconExternalLink, IconPlayerPlay, IconRefresh } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import {
  ApiError,
  acceptFieldSuggestion,
  calculateScenario,
  confirmScenario,
  createScenario,
  formatFormulaValue,
  listScenarioSnapshots,
  listScenarioValues,
  patchScenarioValue,
  updateScenario,
  type CalculationSnapshot,
  type FieldValueView,
  type ProjectRecord,
  type ScenarioRecord,
  type ScenarioValuesResponse,
  type U1ModelSpec,
  type U1Result,
} from "@/lib/api";
import { DashboardChart } from "@/components/dashboard-chart";
import { FieldValueControl } from "@/components/field-value-control";
import { U1ResultPanel } from "@/components/u1-result-panel";

const STATUS_LABELS: Record<ScenarioRecord["status"], { label: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  draft: { label: "草稿", variant: "neutral" },
  stale: { label: "待重算", variant: "warning" },
  calculating: { label: "计算中", variant: "info" },
  calculated: { label: "已计算", variant: "success" },
  confirmed: { label: "已确认", variant: "success" },
  failed: { label: "计算失败", variant: "danger" },
  blocked: { label: "不可用", variant: "danger" },
};

const BLOCK_ORDER = [
  "城市与市场",
  "政策准入",
  "站点空间",
  "成本参数",
  "阶段参数",
  "效率与风险",
  "辅助收入",
  "战略情景",
] as const;

export function CityProjectWorkbench({
  project,
  scenario,
  spec,
  initialSnapshots = [],
  initialValues,
}: Readonly<{
  project: ProjectRecord;
  scenario: ScenarioRecord;
  spec: U1ModelSpec;
  initialSnapshots?: CalculationSnapshot[];
  initialValues?: ScenarioValuesResponse;
}>) {
  const [fields, setFields] = useState<Map<string, FieldValueView>>(
    () => new Map((initialValues?.fields ?? []).map((field) => [field.fieldId, field])),
  );
  const [status, setStatus] = useState<ScenarioRecord["status"]>(scenario.status);
  const [result, setResult] = useState<U1Result | null>(scenario.result);
  const [snapshots, setSnapshots] = useState(initialSnapshots);
  const [busy, setBusy] = useState<"saving" | "calculating" | "copying" | "confirming" | "suggesting" | null>(null);
  const [suggestingField, setSuggestingField] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const statusMeta = STATUS_LABELS[status] ?? STATUS_LABELS.draft;

  const groups = useMemo(() => {
    const byBlock = new Map<string, FieldValueView[]>();
    for (const field of fields.values()) {
      byBlock.set(field.block, [...(byBlock.get(field.block) ?? []), field]);
    }
    return BLOCK_ORDER.filter((block) => byBlock.has(block)).map((block) => ({
      id: block,
      fields: byBlock.get(block) ?? [],
    }));
  }, [fields]);

  const refreshValues = useCallback(async () => {
    const values = await listScenarioValues(project.id, scenario.id);
    setFields(new Map(values.fields.map((field) => [field.fieldId, field])));
    return values;
  }, [project.id, scenario.id]);

  function markStale() {
    if (status === "calculated" || status === "confirmed") setStatus("stale");
    setFeedback(null);
  }

  async function changeValue(field: FieldValueView, value: number | string | null) {
    // 乐观更新当前值，失败时回读服务端状态
    setFields((current) => {
      const next = new Map(current);
      next.set(field.fieldId, { ...field, currentValue: value });
      return next;
    });
    markStale();
    try {
      const updated = await patchScenarioValue(project.id, scenario.id, field.fieldId, value);
      setFields((current) => {
        const next = new Map(current);
        next.set(field.fieldId, updated);
        return next;
      });
    } catch (patchError) {
      setError(patchError instanceof Error ? patchError.message : "参数保存失败");
      await refreshValues();
    }
  }

  async function acceptSuggestion(field: FieldValueView) {
    setBusy("suggesting");
    setSuggestingField(field.fieldId);
    setError(null);
    try {
      const updated = await acceptFieldSuggestion(project.id, scenario.id, field.fieldId);
      setFields((current) => {
        const next = new Map(current);
        next.set(field.fieldId, updated);
        return next;
      });
      markStale();
      setFeedback(`已采用 ${field.name} 的建议值，场景标记为待重算`);
    } catch (acceptError) {
      setError(acceptError instanceof Error ? acceptError.message : "采用建议值失败");
    } finally {
      setBusy(null);
      setSuggestingField(null);
    }
  }

  async function saveDraft() {
    setBusy("saving");
    setFeedback(null);
    setError(null);
    try {
      const saved = await updateScenario(project.id, scenario.id, { inputs: {} });
      setStatus(saved.status);
      await refreshValues();
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
      const nextResult = await calculateScenario(project.id, scenario.id);
      setResult(nextResult);
      setStatus("calculated");
      setSnapshots(await listScenarioSnapshots(project.id, scenario.id));
      await refreshValues();
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
      await createScenario(project.id, { name: `${scenario.name} 副本` });
      setFeedback("场景副本已创建，刷新列表后可见");
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

  const suggestionReadyCount = useMemo(
    () => [...fields.values()].filter((field) => field.valueState === "suggestion_ready").length,
    [fields],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>{project.city}</span>
          <span>·</span>
          <span>{project.district ?? "未配置区县"}</span>
          <span>·</span>
          <span>{scenario.name}</span>
          <Badge variant={statusMeta.variant}>{statusMeta.label}</Badge>
        </div>
        <Link className="inline-flex items-center gap-2 text-sm text-info hover:underline" href="/">
          <IconExternalLink size={16} stroke={1.75} />返回总览
        </Link>
      </div>
      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitle>城市测算参数</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              模型版本：{spec.modelVersion} · 灰色建议值不参与计算，采用后才写入参数；公式自动字段只读。
            </p>
          </div>
          <div className="flex items-center gap-2">
            {suggestionReadyCount > 0 ? <Badge variant="warning">{suggestionReadyCount} 个建议值待采用</Badge> : null}
            <Badge variant={statusMeta.variant}>{statusMeta.label}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {groups.map((group) => (
            <details key={group.id} open className="group rounded-md border border-border">
              <summary className="cursor-pointer list-none border-b border-border bg-surface-subtle px-4 py-3 text-sm font-semibold">
                {group.id}
                <span className="ml-2 text-xs font-normal text-muted-foreground">{group.fields.length} 项</span>
              </summary>
              <div className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3">
                {group.fields.map((field) => {
                  const formulaValue = result?.parameters?.[field.fieldId];
                  return (
                    <FieldValueControl
                      key={field.fieldId}
                      field={field}
                      formulaValue={
                        typeof formulaValue === "number" || typeof formulaValue === "string"
                          ? formatFormulaValue({ value: formulaValue, status: "ok", errorCode: null })
                          : undefined
                      }
                      onValueChange={(value) => void changeValue(field, value)}
                      onAcceptSuggestion={() => void acceptSuggestion(field)}
                      suggestionBusy={busy === "suggesting" && suggestingField === field.fieldId}
                    />
                  );
                })}
              </div>
            </details>
          ))}
          {status === "stale" ? (
            <p className="rounded-md border border-warning/30 bg-warning-subtle px-3 py-2 text-sm text-warning">
              参数已修改，当前结果仅供历史查看，需重新运行测算。
            </p>
          ) : null}
          {feedback ? <p className="rounded-md border border-success/30 bg-success-subtle px-3 py-2 text-sm text-success">{feedback}</p> : null}
          {error ? <p className="rounded-md border border-danger/30 bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p> : null}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => void copyCurrentScenario()} disabled={busy !== null}>
                <IconCopy size={16} stroke={1.75} />{busy === "copying" ? "复制中…" : "复制场景"}
              </Button>
              <Button variant="ghost" onClick={() => void confirmCurrentScenario()} disabled={busy !== null || status !== "calculated"}>
                <IconCheck size={16} stroke={1.75} />{busy === "confirming" ? "确认中…" : "确认结果"}
              </Button>
              <Button variant="ghost" onClick={() => void refreshValues()} disabled={busy !== null}>
                <IconRefresh size={16} stroke={1.75} />刷新建议值
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => void saveDraft()} disabled={busy !== null}>
                <IconDeviceFloppy size={16} stroke={1.75} />{busy === "saving" ? "保存中…" : "保存草稿"}
              </Button>
              <Button onClick={() => void runCalculation()} disabled={busy !== null}>
                <IconPlayerPlay size={16} stroke={1.75} />{busy === "calculating" ? "测算中…" : "运行测算"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      {result ? <U1ResultPanel result={result} /> : null}
      <Card>
        <CardHeader>
          <CardTitle>历史结果快照</CardTitle>
          <p className="text-sm text-muted-foreground">每次测算产生独立快照，历史结果不会被新输入覆盖。</p>
        </CardHeader>
        <CardContent>
          {snapshots.length === 0 ? (
            <p className="text-sm text-muted-foreground">尚无结果快照。</p>
          ) : (
            <div className="space-y-2">
              {snapshots.map((snapshot) => (
                <div key={snapshot.snapshotId} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
                  <span className="font-mono text-xs">{snapshot.snapshotId}</span>
                  <span className="text-muted-foreground">{new Date(snapshot.calculatedAt).toLocaleString("zh-CN")}</span>
                  <Badge variant={snapshot.status === "blocked" ? "danger" : "success"}>
                    {snapshot.status === "blocked" ? "阻断" : snapshot.status === "confirmed" ? "已确认" : "已计算"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      <DashboardChart
        title="城市月度趋势"
        type="trend"
        data={(result?.months ?? []).map((month) => ({
          month: month.month,
          stage: month.stage,
          revenue: typeof month.totalRevenue.value === "number" ? month.totalRevenue.value : null,
          netProfit: typeof month.netProfit.value === "number" ? month.netProfit.value : null,
          cumulativeCashFlow: typeof month.cumulativeCashFlow.value === "number" ? month.cumulativeCashFlow.value : null,
        }))}
      />
    </div>
  );
}
