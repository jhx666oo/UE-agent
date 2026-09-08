"use client";

import React from "react";
import { useMemo, useState } from "react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Badge } from "@ue-agent/ui/components/badge";
import { ApiError, calculateScenario, formatFormulaValue, updateScenario, type ParameterDefinition, type ScenarioRecord, type U1ModelSpec, type U1Result } from "@/lib/api";
import { U1ParameterField } from "@/components/u1-parameter-field";
import { U1ResultPanel } from "@/components/u1-result-panel";

const GROUP_LABELS: Record<string, string> = {
  C: "城市与市场",
  P: "政策与服务",
  S: "站点",
  B: "成本与投资",
  D: "发展阶段",
  E: "效率与风险",
  A: "辅助收入",
  Z: "进入模式",
};

export function groupParameters(parameters: ParameterDefinition[]) {
  const groups = new Map<string, ParameterDefinition[]>();
  for (const parameter of parameters) {
    const group = parameter.id.slice(0, 1);
    groups.set(group, [...(groups.get(group) ?? []), parameter]);
  }
  return ["C", "P", "S", "B", "D", "E", "A", "Z"]
    .filter((group) => groups.has(group))
    .map((group) => ({ id: group, label: GROUP_LABELS[group], parameters: groups.get(group) ?? [] }));
}

export function U1Workbench({ projectId, scenario, spec }: Readonly<{ projectId: string; scenario: ScenarioRecord; spec: U1ModelSpec }>) {
  const [inputs, setInputs] = useState(scenario.inputs);
  const [result, setResult] = useState<U1Result | null>(scenario.result);
  const [busy, setBusy] = useState<"saving" | "calculating" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const groups = useMemo(() => groupParameters(spec.parameters), [spec.parameters]);

  async function saveInputs() {
    setBusy("saving");
    setError(null);
    try {
      await updateScenario(projectId, scenario.id, { inputs });
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "参数保存失败");
    } finally {
      setBusy(null);
    }
  }

  async function calculate() {
    setBusy("calculating");
    setError(null);
    try {
      await updateScenario(projectId, scenario.id, { inputs });
      setResult(await calculateScenario(projectId, scenario.id));
    } catch (calculationError) {
      if (calculationError instanceof ApiError && calculationError.payload && typeof calculationError.payload === "object" && "issues" in calculationError.payload) {
        setResult(calculationError.payload as U1Result);
      }
      setError(calculationError instanceof Error ? calculationError.message : "测算失败");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <div><CardTitle>参数输入</CardTitle><p className="mt-1 text-sm text-muted-foreground">模型版本：{spec.modelVersion} · 公式字段由服务端计算</p></div>
          <Badge variant={result ? "success" : "neutral"}>{result ? "已测算" : "待测算"}</Badge>
        </CardHeader>
        <CardContent className="space-y-6">
          {groups.map((group) => (
            <section key={group.id} className="space-y-4">
              <div className="flex items-center gap-3 border-b border-border pb-2"><h3 className="text-sm font-semibold">{group.label}</h3><span className="text-xs text-muted-foreground">{group.id} 组 · {group.parameters.length} 项</span></div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {group.parameters.map((definition) => {
                  const formulaValue = result?.parameters[definition.id];
                  return <U1ParameterField key={definition.id} definition={definition} value={inputs[definition.id] ?? null} formulaValue={typeof formulaValue === "number" || typeof formulaValue === "string" ? formatFormulaValue({ value: formulaValue, status: "ok", errorCode: null }) : undefined} onChange={(value) => setInputs((current) => ({ ...current, [definition.id]: value }))} />;
                })}
              </div>
            </section>
          ))}
          {error ? <p className="rounded-md border border-danger/20 bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p> : null}
          <div className="flex flex-wrap justify-end gap-3 border-t border-border pt-5">
            <Button variant="outline" onClick={saveInputs} disabled={busy !== null}>{busy === "saving" ? "保存中…" : "保存参数"}</Button>
            <Button onClick={calculate} disabled={busy !== null}>{busy === "calculating" ? "测算中…" : "运行测算"}</Button>
          </div>
        </CardContent>
      </Card>
      {result ? <U1ResultPanel result={result} /> : null}
    </div>
  );
}
