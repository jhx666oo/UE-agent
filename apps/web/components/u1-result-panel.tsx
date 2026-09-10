"use client";

import React, { useMemo } from "react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { MetricCard } from "@/components/metric-card";
import { formatFormulaValue, type FormulaValue, type U1Result } from "@/lib/api";

const HEADLINE_LABELS: Record<string, string> = {
  payback_month: "投资回收期（月）",
  max_cash_deficit: "最大现金缺口",
  startup_max_cash_deficit: "启动期累计最大亏损",
  platform_monthly_net_profit: "平台期月均净利润",
  platform_net_margin: "平台期月均净利率",
  twenty_four_month_cumulative_net_profit: "24个月累计净利润",
  net_break_even_month: "盈亏平衡月份",
  break_even_customers: "平台期盈亏平衡客户数",
  initial_investment: "筹备期总投入",
  startup_total_loss: "启动期总亏损",
  platform_monthly_revenue: "平台期月均收入",
};

// 指标卡的固定展示顺序，与 Excel 控制台“核心指标卡”一致。
const HEADLINE_ORDER: string[] = [
  "payback_month",
  "startup_max_cash_deficit",
  "platform_monthly_net_profit",
  "platform_net_margin",
  "twenty_four_month_cumulative_net_profit",
  "net_break_even_month",
  "break_even_customers",
  "initial_investment",
  "startup_total_loss",
  "platform_monthly_revenue",
];

// 负值指标（亏损类）使用危险色，与 Excel 中红色数字一致。
const LOSS_METRICS = new Set([
  "startup_max_cash_deficit",
  "startup_total_loss",
  "max_cash_deficit",
]);

const STAGE_LABELS: Record<string, string> = {
  "筹备期": "筹备期",
  "启动期": "启动期",
  "平台期": "平台期",
  preparation: "筹备期",
  startup: "启动期",
  platform: "平台期",
};

// 月度投影列，按「收入 → 成本 → 利润 → 现金流」分组，与 Excel 月度投影表顺序一致。
const MONTH_COLUMNS: Array<[keyof U1Result["months"][number], string]> = [
  ["month", "月份"],
  ["stage", "阶段"],
  ["signedCustomers", "签约客户"],
  ["singleCustomerMonthRevenue", "单客月收入"],
  ["longTermCareRevenue", "长护险收入"],
  ["auxiliaryRevenue", "辅助收入"],
  ["totalRevenue", "总收入"],
  ["caregivers", "护理员数"],
  ["caregiverCost", "护理员成本"],
  ["salesCost", "销售成本"],
  ["nurseCost", "护士成本"],
  ["variableCost", "变动成本"],
  ["fixedCost", "固定成本"],
  ["grossProfit", "毛利润"],
  ["netProfit", "净利润"],
  ["grossMargin", "毛利率"],
  ["netMargin", "净利率"],
  ["cumulativeNetProfit", "累计净利润"],
  ["cumulativeCashFlow", "累计现金流"],
  ["breakEvenCustomers", "盈亏平衡客户"],
];

// 阶段行背景，让三段区间在长表里一眼可辨。
const STAGE_ROW_CLASS: Record<string, string> = {
  "筹备期": "bg-surface-subtle",
  "启动期": "bg-info-subtle",
  "平台期": "",
};

function isFormulaValue(value: unknown): value is FormulaValue {
  return Boolean(value && typeof value === "object" && "status" in value && "value" in value);
}

function displayValue(value: unknown) {
  return isFormulaValue(value) ? formatFormulaValue(value) : String(value ?? "未计算");
}

export function U1ResultPanel({ result }: Readonly<{ result: U1Result }>) {
  const headlineEntries = useMemo(() => {
    const metrics = result.headlineMetrics;
    const known = HEADLINE_ORDER.filter((key) => key in metrics);
    const extra = Object.keys(metrics).filter((key) => !HEADLINE_ORDER.includes(key));
    return [...known, ...extra].map((key) => [key, metrics[key]] as const);
  }, [result.headlineMetrics]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">测算结果</h2>
          <p className="text-sm text-muted-foreground">模型版本：{result.modelVersion}</p>
        </div>
        <Badge variant={result.status === "ok" ? "success" : "danger"}>{result.status === "ok" ? "已完成" : "不可用"}</Badge>
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-medium text-foreground">核心指标卡</h3>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {headlineEntries.map(([key, value]) => {
            const formatted = formatFormulaValue(value);
            const isLoss = LOSS_METRICS.has(key) && typeof value.value === "number" && value.value < 0;
            return (
              <MetricCard
                key={key}
                label={HEADLINE_LABELS[key] ?? key}
                value={formatted}
                tone={isLoss ? "danger" : "neutral"}
              />
            );
          })}
        </div>
      </section>

      {result.issues.length > 0 ? (
        <Card className="border-warning/30">
          <CardHeader>
            <CardTitle>待业务确认问题（{result.issues.length}）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {result.issues.map((issue) => (
              <div key={`${issue.code}-${issue.excelCell}`} className="rounded-md border border-warning/20 bg-warning-subtle p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="warning">{issue.code}</Badge>
                  <span className="text-xs text-muted-foreground">{issue.excelCell}</span>
                </div>
                <p className="mt-2 text-sm text-foreground">{issue.message}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>阶段汇总</CardTitle>
          <p className="text-sm text-muted-foreground">基于月度投影聚合，按筹备期 / 启动期 / 平台期三段呈现。</p>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground"><th className="px-3 py-2">阶段</th><th className="px-3 py-2">月份</th><th className="px-3 py-2">总收入</th><th className="px-3 py-2">总净利润</th><th className="px-3 py-2">净利率</th></tr></thead>
            <tbody>
              {Object.entries(result.stageSummary).map(([stage, summary]) => (
                <tr key={stage} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-medium">{STAGE_LABELS[stage] ?? stage}</td>
                  <td className="px-3 py-2">{displayValue(summary.monthCount)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{displayValue(summary.totalRevenue)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{displayValue(summary.totalNetProfit)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{displayValue(summary.netMargin)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>24 个月月度投影</CardTitle>
          <p className="text-sm text-muted-foreground">
            逐月现金流与损益明细，源自控制台参数计算。行背景区分筹备期 / 启动期 / 平台期，回本月份以左侧标记提示。
          </p>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[1680px] text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">{MONTH_COLUMNS.map(([, label]) => <th key={label} className="whitespace-nowrap px-3 py-2">{label}</th>)}</tr></thead>
            <tbody>
              {result.months.map((month) => {
                const isPaybackMonth = month.cashFlowPositiveMonth.value === month.month;
                const stageKey = STAGE_LABELS[month.stage] ?? month.stage;
                return (
                  <tr
                    key={month.month}
                    className={`border-b border-border last:border-0 ${STAGE_ROW_CLASS[stageKey] ?? ""}`}
                  >
                    {MONTH_COLUMNS.map(([key]) => {
                      const isFirstColumn = key === "month";
                      return (
                        <td key={String(key)} className="whitespace-nowrap px-3 py-2 text-right tabular-nums first:text-left">
                          {isFirstColumn && isPaybackMonth ? (
                            <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-success align-middle" aria-label="回本月份" />
                          ) : null}
                          {key === "stage" ? stageKey : displayValue(month[key])}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
