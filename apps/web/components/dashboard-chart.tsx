"use client";

import React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { EmptyState } from "@/components/empty-state";
import { formatDashboardNumber } from "@/lib/dashboard";

type TrendPoint = { month: number; stage: string | null; revenue: number | null; netProfit: number | null; cumulativeCashFlow: number | null };

export function DashboardChart({
  title,
  type,
  data,
}: Readonly<{
  title: string;
  type: "trend" | "comparison" | "scatter";
  data: Array<Record<string, unknown>> | TrendPoint[];
}>) {
  if (data.length === 0) {
    return <EmptyState title={`${title}暂无数据`} description="当前筛选范围没有可展示的有效结果，请先完成城市测算或调整筛选条件。" />;
  }

  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        <div className="h-72 w-full" role="img" aria-label={title}>
          <ResponsiveContainer width="100%" height="100%">
            {type === "trend" ? (
              <LineChart data={data as TrendPoint[]} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="month" tickFormatter={(value) => `${value}月`} />
                <YAxis tickFormatter={(value) => formatDashboardNumber(Number(value))} />
                <Tooltip formatter={(value, name) => [`${formatDashboardNumber(Number(value))} 元`, name === "revenue" ? "收入" : name === "netProfit" ? "净利润" : "累计现金流"]} />
                <Legend formatter={(value) => value === "revenue" ? "收入" : value === "netProfit" ? "净利润" : "累计现金流"} />
                <Line type="monotone" dataKey="revenue" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="netProfit" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="cumulativeCashFlow" stroke="var(--chart-4)" strokeWidth={2} dot={false} />
              </LineChart>
            ) : type === "comparison" ? (
              <BarChart data={data} layout="vertical" margin={{ top: 8, right: 8, left: 40, bottom: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(value) => formatDashboardNumber(Number(value))} />
                <YAxis type="category" dataKey="cityName" width={72} />
                <Tooltip formatter={(value) => `${formatDashboardNumber(Number(value))} 元`} />
                <Legend />
                <Bar dataKey="monthlyRevenue" name="月收入" fill="var(--chart-1)" />
                <Bar dataKey="monthlyNetProfit" name="月净利润" fill="var(--chart-2)" />
              </BarChart>
            ) : (
              <ScatterChart margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="var(--border)" />
                <XAxis type="number" dataKey="targetCustomers" name="目标客户" unit="人" />
                <YAxis type="number" dataKey="paybackMonth" name="回本周期" unit="个月" />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(value, name) => [`${formatDashboardNumber(Number(value))} ${name === "targetCustomers" ? "人" : "个月"}`, name]} />
                <Scatter name="城市" data={data} fill="var(--chart-3)" />
              </ScatterChart>
            )}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
