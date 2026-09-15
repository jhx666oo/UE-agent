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
import { formatDashboardCompactNumber, formatDashboardNumber } from "@/lib/dashboard";

type TrendPoint = { month: number; stage: string | null; revenue: number | null; netProfit: number | null; cumulativeCashFlow: number | null };

/** 多城对比时每个城市一条线，用哪个指标 —— 选址决策看净利润最直接。 */
const CITY_COMPARE_METRIC = "netProfit" as const;
const CITY_COMPARE_METRIC_LABEL = "月净利润";
/** 城市线用的色板（tokens.css 里的 --chart-1..5）。 */
const CITY_LINE_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];

export function DashboardChart({
  title,
  type,
  data,
  series,
}: Readonly<{
  title: string;
  type: "trend" | "comparison" | "scatter";
  data: Array<Record<string, unknown>> | TrendPoint[];
  /**
   * 多城对比：按城市分组的序列（≥2 个城市时逐城市画线，图例直接标城市名）。
   * 不传时沿用原来的「单城三指标」画法。
   */
  series?: Array<{ cityId: string; cityName: string; points: TrendPoint[] }>;
}>) {
  const citySeries = series && series.length >= 2 ? series : null;

  // 把 [{cityName, points}] 摊平成 [{month, 岳阳: 净利润, 长沙: 净利润}]，Recharts 才能一城一条线。
  const cityRows = citySeries
    ? [...new Set(citySeries.flatMap((item) => item.points.map((point) => point.month)))]
        .sort((a, b) => a - b)
        .map((month) => {
          const row: Record<string, number | string> = { month };
          for (const item of citySeries) {
            const value = item.points.find((point) => point.month === month)?.[CITY_COMPARE_METRIC];
            if (typeof value === "number") row[item.cityName] = value;
          }
          return row;
        })
    : [];

  if (data.length === 0 && !citySeries) {
    return <EmptyState title={`${title}暂无数据`} description="当前筛选范围没有可展示的有效结果，请先完成城市测算或调整筛选条件。" />;
  }

  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        <div className="h-72 w-full" role="img" aria-label={title}>
          <ResponsiveContainer width="100%" height="100%">
            {type === "trend" && citySeries ? (
              // 多城对比：一条线一个城市 —— 先前的聚合写法把城市加总成一条线，看不出谁是谁。
              <LineChart data={cityRows} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="month" tickFormatter={(value) => `${value}月`} />
                <YAxis tickFormatter={(value) => formatDashboardCompactNumber(Number(value))} />
                <Tooltip
                  labelFormatter={(label) => `第 ${label} 月`}
                  formatter={(value, name) => [
                    `${formatDashboardNumber(Number(value))} 元`,
                    `${String(name)} · ${CITY_COMPARE_METRIC_LABEL}`,
                  ]}
                />
                <Legend iconType="plainline" iconSize={24} wrapperStyle={{ fontSize: 13, paddingTop: 8, lineHeight: "22px" }} />
                {citySeries.map((item, index) => (
                  <Line
                    key={item.cityId}
                    type="monotone"
                    dataKey={item.cityName}
                    name={item.cityName}
                    stroke={CITY_LINE_COLORS[index % CITY_LINE_COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                  />
                ))}
              </LineChart>
            ) : type === "trend" ? (
              // left 留 8：完整数字刻度有 10+ 字符，margin.left=0 时最左侧的刻度会被容器边缘裁掉。
              <LineChart data={data as TrendPoint[]} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="month" tickFormatter={(value) => `${value}月`} />
                {/* 刻度用「亿/万」紧凑写法，完整数字会把轴挤没；tooltip 仍给精确值 */}
                <YAxis tickFormatter={(value) => formatDashboardCompactNumber(Number(value))} />
                <Tooltip
                  labelFormatter={(label) => `第 ${label} 月`}
                  formatter={(value, name) => [`${formatDashboardNumber(Number(value))} 元`, String(name)]}
                />
                {/*
                  三条线里「收入」和「净利润」数值往往非常接近（实测 35.27M vs 34.32M），
                  实线重合在一起就变成「两条线配三个图例」，根本分不清哪条是哪条。
                  因此每条线用**不同的虚实线型**，重合时也能分辨；图例色块同时放大。
                */}
                <Legend
                  iconType="plainline"
                  iconSize={24}
                  wrapperStyle={{ fontSize: 13, paddingTop: 8, lineHeight: "22px" }}
                />
                <Line type="monotone" dataKey="revenue" name="收入" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="netProfit" name="净利润" stroke="var(--chart-2)" strokeWidth={2} strokeDasharray="7 3" dot={false} />
                <Line type="monotone" dataKey="cumulativeCashFlow" name="累计现金流" stroke="var(--chart-4)" strokeWidth={2.5} strokeDasharray="2 3" dot={false} />
              </LineChart>
            ) : type === "comparison" ? (
              // 城市名在 Y 轴，宽度按较长的城市名留够（原来 72 容易被裁）；right 留出最长柱的余量。
              <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(value) => formatDashboardCompactNumber(Number(value))} />
                <YAxis type="category" dataKey="cityName" width={84} />
                <Tooltip
                  labelFormatter={(label) => `城市：${label}`}
                  formatter={(value) => `${formatDashboardNumber(Number(value))} 元`}
                />
                <Legend iconSize={16} wrapperStyle={{ fontSize: 13, paddingTop: 8 }} />
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
