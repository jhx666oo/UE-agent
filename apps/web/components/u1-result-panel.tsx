"use client";

import React from "react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { MetricCard } from "@/components/metric-card";
import { formatFormulaValue, type FormulaValue, type U1Result } from "@/lib/api";

const HEADLINE_LABELS: Record<string, string> = {
  payback_month: "累计现金流回正月",
  max_cash_deficit: "最大现金缺口",
  platform_monthly_net_profit: "平台期月净利润",
  platform_net_margin: "平台期净利率",
  twenty_four_month_cumulative_net_profit: "24个月累计净利润",
  break_even_customers: "平台期盈亏平衡客户",
  initial_investment: "初始投资总额",
  platform_monthly_revenue: "平台期月收入",
};

const MONTH_COLUMNS: Array<[keyof U1Result["months"][number], string]> = [
  ["month", "月份"],
  ["stage", "阶段"],
  ["signedCustomers", "签约客户"],
  ["totalRevenue", "总收入"],
  ["variableCost", "变动成本"],
  ["fixedCost", "固定成本"],
  ["netProfit", "净利润"],
  ["cumulativeCashFlow", "累计现金流"],
  ["breakEvenCustomers", "盈亏平衡客户"],
];

function isFormulaValue(value: unknown): value is FormulaValue {
  return Boolean(value && typeof value === "object" && "status" in value && "value" in value);
}

function displayValue(value: unknown) {
  return isFormulaValue(value) ? formatFormulaValue(value) : String(value ?? "未计算");
}

export function U1ResultPanel({ result }: Readonly<{ result: U1Result }>) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">测算结果</h2>
          <p className="text-sm text-muted-foreground">模型版本：{result.modelVersion}</p>
        </div>
        <Badge variant={result.status === "ok" ? "success" : "danger"}>{result.status === "ok" ? "已完成" : "不可用"}</Badge>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Object.entries(result.headlineMetrics).map(([key, value]) => (
          <MetricCard key={key} label={HEADLINE_LABELS[key] ?? key} value={formatFormulaValue(value)} />
        ))}
      </div>

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
        <CardHeader><CardTitle>阶段汇总</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground"><th className="px-3 py-2">阶段</th><th className="px-3 py-2">月份</th><th className="px-3 py-2">总收入</th><th className="px-3 py-2">总净利润</th><th className="px-3 py-2">净利率</th></tr></thead>
            <tbody>
              {Object.entries(result.stageSummary).map(([stage, summary]) => (
                <tr key={stage} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-medium">{stage}</td>
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
        <CardHeader><CardTitle>24 个月月度投影</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">{MONTH_COLUMNS.map(([, label]) => <th key={label} className="whitespace-nowrap px-3 py-2">{label}</th>)}</tr></thead>
            <tbody>
              {result.months.map((month) => (
                <tr key={month.month} className="border-b border-border last:border-0">
                  {MONTH_COLUMNS.map(([key]) => <td key={String(key)} className="whitespace-nowrap px-3 py-2 text-right tabular-nums first:text-left">{displayValue(month[key])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
