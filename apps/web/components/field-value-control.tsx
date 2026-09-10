"use client";

import React from "react";
import { IconChevronDown, IconCircleCheck } from "@tabler/icons-react";
import { Badge } from "@ue-agent/ui/components/badge";
import { Button } from "@ue-agent/ui/components/button";
import { Input } from "@ue-agent/ui/components/input";
import { Label } from "@ue-agent/ui/components/label";
import { cn } from "@ue-agent/ui/lib/cn";
import type { FieldValueView } from "@/lib/api";

const VALUE_STATE_LABELS: Record<FieldValueView["valueState"], { label: string; variant: "neutral" | "info" | "success" | "warning" } | null> = {
  empty: { label: "待采用建议", variant: "neutral" },
  suggestion_ready: { label: "待采用建议", variant: "neutral" },
  accepted: { label: "已采用爬虫数据", variant: "success" },
  overridden: { label: "已手动覆盖", variant: "info" },
  manual: null,
  formula: null,
};

function formatValue(value: number | string | null): string {
  if (value === null) return "";
  if (typeof value === "number") return String(value);
  return value;
}

/**
 * PRD 12.2 / 17.3 三类数据源交互（sourceType 已统一，不再有暗访实地/市场调研）：
 * 内部填写 = 普通可编辑控件（可留空）；自动爬虫 = 输入框 + 灰色建议值 + 采用按钮；
 * 公式自动 = 只读结果框。
 */
export function FieldValueControl({
  field,
  formulaValue,
  onValueChange,
  onAcceptSuggestion,
  suggestionBusy,
}: Readonly<{
  field: FieldValueView;
  formulaValue?: string;
  onValueChange: (value: number | string | null) => void;
  onAcceptSuggestion?: () => void;
  suggestionBusy?: boolean;
}>) {
  const isFormula = field.sourceType === "公式自动";
  const isCrawler = field.sourceType === "自动爬虫";
  // 文本类字段（如 C1 城市名称）必须渲染文本输入框：数字输入框会把文本值当数字处理，
  // 点击上下箭头会把 "长沙" 逐步减成 0 再清空，造成数据丢失。
  const isText = field.valueType === "string";
  const stateMeta = VALUE_STATE_LABELS[field.valueState];
  const hasSuggestion = isCrawler && field.suggestedValue !== null && field.suggestedValue !== undefined;
  const suggestedDisplay = hasSuggestion
    ? `建议值：${formatValue(field.suggestedValue)}${field.unit && field.unit !== "-" ? ` ${field.unit}` : ""}`
    : null;
  const sourceLine = hasSuggestion
    ? `来源：${field.suggestedSource?.sourceName ?? "未知来源"}${field.suggestedAt ? ` · ${new Date(field.suggestedAt).toLocaleDateString("zh-CN")}` : ""}`
    : null;

  const control = isFormula ? (
    <div className="flex items-center gap-2">
      <Input
        id={`field-${field.fieldId}`}
        value={formulaValue ?? formatValue(field.currentValue) ?? ""}
        readOnly
        className="border-success-subtle bg-success-subtle/40 text-foreground"
        aria-readonly="true"
      />
      <Badge variant="success">公式</Badge>
    </div>
  ) : field.options && field.options.length > 0 ? (
    <div className="relative">
      <select
        id={`field-${field.fieldId}`}
        value={field.currentValue === null ? "" : String(field.currentValue)}
        onChange={(event) => {
          const next = event.target.value;
          onValueChange(next === "" ? null : next);
        }}
        className="h-10 w-full appearance-none rounded-md border border-border bg-background px-3 pr-9 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {field.currentValue === null ? <option value="">请选择</option> : null}
        {field.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <IconChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} stroke={1.8} />
    </div>
  ) : isText ? (
    <Input
      id={`field-${field.fieldId}`}
      type="text"
      value={formatValue(field.currentValue)}
      placeholder={field.sourceType === "自动爬虫" && !hasSuggestion ? "暂无爬虫数据，可手动填写" : "请输入"}
      onChange={(event) => {
        const next = event.target.value;
        onValueChange(next === "" ? null : next);
      }}
    />
  ) : (
    <Input
      id={`field-${field.fieldId}`}
      type="number"
      inputMode="decimal"
      value={formatValue(field.currentValue)}
      placeholder={field.sourceType === "自动爬虫" && !hasSuggestion ? "暂无爬虫数据，可手动填写" : ""}
      onChange={(event) => {
        const next = event.target.value;
        if (next === "") {
          onValueChange(null);
        } else {
          const numberValue = Number(next);
          onValueChange(Number.isNaN(numberValue) ? null : numberValue);
        }
      }}
    />
  );

  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <Label htmlFor={`field-${field.fieldId}`} className="leading-snug">
          {field.fieldId} {field.name}
        </Label>
        {stateMeta ? <Badge variant={stateMeta.variant} className="shrink-0">{stateMeta.label}</Badge> : null}
      </div>
      {control}
      {suggestedDisplay ? (
        <div className="space-y-1">
          <p className={cn("text-xs", field.valueState === "suggestion_ready" || field.valueState === "empty" ? "text-muted-foreground" : "text-muted-foreground/70")}>
            {suggestedDisplay}
            {sourceLine ? ` · ${sourceLine}` : ""}
          </p>
          {field.valueState === "suggestion_ready" ? (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onAcceptSuggestion}
                disabled={suggestionBusy}
              >
                <IconCircleCheck size={15} stroke={1.75} />
                {suggestionBusy ? "采用中…" : "采用建议值"}
              </Button>
              {field.suggestedSource?.url ? (
                <a
                  className="inline-flex h-8 items-center rounded-md px-2 text-xs text-info underline-offset-4 hover:underline"
                  href={field.suggestedSource.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  查看来源
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">
        {field.unit === "-" ? "" : `${field.unit} · `}{field.sourceType}
      </p>
    </div>
  );
}
